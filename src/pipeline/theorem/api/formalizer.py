from pathlib import Path
from typing import Dict, List, Optional, Any
import json
import asyncio
from logging import Logger
import tempfile
import shutil

from src.utils.apis.langchain_client import _call_openai_completion_async
from src.pipeline.theorem.api.theorem_types import APITheoremGenerationInfo

class APITheoremFormalizer:
    """Formalize API requirements into theorems"""
    
    SYSTEM_PROMPT = """
You are a theorem formalizer for Lean 4 code, specializing in converting API requirements into formal theorems.

Task:
Convert an API requirement description into a formal theorem in Lean 4, based on existing API implementations and theorems.

Background:
1. Code Structure:
   - APIs are implemented as functions in Lean 4
   - Database tables are implemented as structures
   - Each API has its implementation and may depend on other APIs
   - Each table has its structure definition

2. Theorem Context:
   - All dependent APIs already have their theorems formalized
   - All required table structures are defined
   - Each requirement should become one independent theorem
   - Previous theorems for this API (if any) are already in the file

3. Theorem Structure:
   - Each theorem should capture one specific property or behavior
   - Use 'sorry' for all proofs as we only need the theorem statements
   - Reference the actual types from API and table definitions
   - Consider state changes in database tables (old_table vs new_table)

4. Common Patterns:
   - For database operations, consider both success and failure cases
   - For validation checks, include the conditions in theorem assumptions
   - For state changes, specify the relationship between old and new states
   - For error cases, ensure they're properly represented in the theorem

Output Format:
1. Analysis Process:
   - Explain how you interpret the requirement
   - Identify key properties to formalize
   - Note any assumptions or edge cases

2. Code Sections:
### Full Code
```lean
<complete file content including imports and all theorems>
```

### Theorem Code
```lean
<only the new theorem, optioanl comment, then starting from 'theorem' keyword, use sorry for all proofs>
```

Requirements:
1. Theorem Formalization:
   - Use precise Lean 4 syntax
   - Make theorem names descriptive and unique
   - Include all necessary type parameters
   - Specify clear pre and post conditions
   - You should not change the existing theorems, only add the new one, but you can add new imports or other prefixes if needed 

2. Type Safety:
   - Use correct types from API and table definitions
   - Handle all possible return types
   - Consider nullable fields
   - Respect type constraints

3. State Handling:
   - Track database state changes
   - Maintain table invariants

4. Error Cases:
   - Include error conditions
   - Specify error messages
   - Handle all possible failure modes
   - Maintain system consistency

5. Style Guidelines:
   - Use clear variable names
   - Add comments for complex logic
   - Follow Lean 4 naming conventions
   - Maintain consistent indentation

Remember:
- Focus on correctness over complexity
- Make theorems as specific as possible
- Maintain consistency with existing theorems
- Use existing definitions when possible
- Use sorry for all proofs
"""

    def __init__(self, 
                 model: str = "qwen-max-latest",
                 max_retries: int = 5):
        self.model = model
        self.max_retries = max_retries
    
    def _format_dependencies_prompt(self, dependencies: Dict) -> str:
        """Format dependencies into a readable prompt with code blocks"""
        sections = []
        
        # Format APIs
        if dependencies["apis"]:
            sections.append("1. APIs:")
            for api_name, api_data in dependencies["apis"].items():
                sections.append(f"\n{api_name}:")
                sections.append(f"Implementation Import Path: {api_data['code_path']}")
                sections.append("Implementation:")
                sections.append("```lean")
                sections.append(api_data["code"])
                sections.append("```")
                
                if api_data["theorems"]:
                    sections.append(f"Theorems Import Path: {api_data['theorems_path']}")
                    sections.append("Theorems:")
                    sections.append("```lean")
                    sections.append(api_data["theorems"])
                    sections.append("```")
                sections.append("")  # Empty line between APIs
        
        # Format Tables
        if dependencies["tables"]:
            sections.append("2. Tables:")
            for table_name, table_data in dependencies["tables"].items():
                sections.append(f"\n{table_name}:")
                sections.append(f"Definition Import Path: {table_data['code_path']}")
                sections.append("Definition:")
                sections.append("```lean")
                sections.append(table_data["code"])
                sections.append("```")
                
                if table_data.get("theorems"):
                    sections.append(f"Theorems Import Path: {table_data['theorems_path']}")
                    sections.append("Theorems:")
                    sections.append("```lean")
                    sections.append(table_data["theorems"])
                    sections.append("```")
                sections.append("")  # Empty line between tables
        
        return "\n".join(sections)

    async def _formalize_requirement(self,
                                   service_name: str,
                                   api_name: str,
                                   requirement: str,
                                   info: APITheoremGenerationInfo,
                                   logger: Optional[Logger] = None) -> Optional[str]:
        """Formalize a single requirement into a theorem"""
        if logger:
            logger.info(f"Formalizing requirement for {service_name}.{api_name}: {requirement}")
        
        # Prepare context
        context = self._prepare_context(service_name, api_name, requirement, info)
        
        # Initialize history
        history = []
        
        # Format initial prompt
        initial_prompt = self._format_prompt(context)
        current_prompt = initial_prompt
        
        for attempt in range(self.max_retries):
            if logger:
                logger.info(f"Attempt {attempt + 1}/{self.max_retries}")
                logger.model_input(current_prompt)
            
            # Call model
            response = await _call_openai_completion_async(
                system_prompt=self.SYSTEM_PROMPT,
                user_prompt=current_prompt,
                history=history,
                model=self.model
            )
            
            if not response:
                if logger:
                    logger.error("Failed to get model response")
                continue

            if logger:
                logger.model_output(response)
            
            # Extract theorem code
            try:
                full_code = response.split("### Full Code\n```lean")[1].split("```")[0].strip()
                theorem_code = response.split("### Theorem Code\n```lean")[1].split("```")[0].strip()
            except Exception as e:
                if logger:
                    logger.error(f"Failed to parse model response: {e}")
                continue

            if logger:
                logger.model_output(full_code)
                logger.model_output(theorem_code)
            
            # Try to compile
            success, error_message = await self._try_compile(
                service_name=service_name,
                api_name=api_name,
                code=full_code,
                info=info,
                logger=logger
            )

            if logger:
                logger.info(f"Compilation result: success={success}, error_message={error_message}")
            
            if success:
                info.project.add_test_lean_theorem(
                    kind="api",
                    service_name=service_name,
                    name=api_name,
                    theorem=theorem_code
                )
                return full_code, theorem_code
            
            # Update history and create retry prompt
            history.extend([
                {"role": "user", "content": current_prompt},
                {"role": "assistant", "content": response}
            ])
            
            current_prompt = f"""
Compilation failed with error:
{error_message}

Please fix the Lean code. Make sure to:
1. Address the specific compilation error
2. Maintain the same theorem logic
3. Use correct import paths
4. Follow Lean 4 syntax

Please provide your response in the same format:
Analysis of the error and your fixes
### Full Code
```lean
<complete corrected file>
```
### Theorem Code
```lean
<corrected theorem only, use sorry for all proofs>
```

Please make sure you have '### Full Code\n```lean' and '### Theorem Code\n```lean' in your response so that I can find the Lean code easily.
You must not omit any part of the full code, because I will use that to directly cover the old one.
"""
            
            if logger:
                logger.warning(f"Compilation failed (attempt {attempt + 1}): {error_message}")
        
        if logger:
            logger.error(f"Failed to formalize requirement after {self.max_retries} attempts")
        
        # add null to the theorems list
        info.project.add_test_lean_theorem(
            kind="api",
            service_name=service_name,
            name=api_name,
            theorem=None
        )
        return None, None

    def _prepare_context(self, service_name: str, api_name: str, requirement: str, 
                        info: APITheoremGenerationInfo) -> Dict:
        """Prepare context for formalization"""
        # Get API and its dependencies
        api = info.project._find_api(service_name, api_name)
        if not api:
            raise ValueError(f"API {api_name} not found in service {service_name}")
        
        # Prepare context
        context = {
            "api_name": api_name,
            "service_name": service_name,
            "requirement": requirement,
            "api_code": api.lean_code,
            "api_code_path": info.project.get_lean_import_path("api", service_name, api_name),
            "current_theorems": api.lean_test_code or "",
            "current_theorems_path": info.project.get_test_lean_import_path("api", service_name, api_name),
            "dependencies": {
                "apis": {},
                "tables": {}
            }
        }
        
        # Add dependent APIs
        for dep_api_name in info.api_dependencies.get(api_name, []):
            dep_service = None
            for service in info.project.services:
                if any(a.name == dep_api_name for a in service.apis):
                    dep_service = service.name
                    break
            if dep_service:
                dep_api = info.project._find_api(dep_service, dep_api_name)
                if dep_api and dep_api.lean_code:
                    context["dependencies"]["apis"][dep_api_name] = {
                        "code": dep_api.lean_code,
                        "code_path": info.project.get_lean_import_path("api", dep_service, dep_api_name),
                        "theorems": dep_api.lean_test_code,
                        "theorems_path": info.project.get_test_lean_import_path("api", dep_service, dep_api_name)
                    }
        
        # Add dependent tables
        for table_name in info.api_table_dependencies.get(api_name, []):
            table = info.project._find_table(table_name)
            if table and table.lean_code:
                service_name, table = info.project._find_table_with_service(table_name)
                table_name = table.name
                context["dependencies"]["tables"][table_name] = {
                    "code": table.lean_code,
                    "code_path": info.project.get_lean_import_path("table", service_name, table_name),
                }
        
        return context

    def _format_prompt(self, context: Dict) -> str:
        """Format the initial prompt"""
        return f"""
Please formalize the following API requirement into a Lean 4 theorem:

API: {context['service_name']}.{context['api_name']}
Requirement: {context['requirement']}

Current API implementation:
Import path: {context['api_code_path']}
```lean
{context['api_code']}
```

Current theorem file:
Import path: {context['current_theorems_path']}
```lean
{context['current_theorems']}
```

Dependencies:

{self._format_dependencies_prompt(context['dependencies'])}

Please ensure all import statements use the exact paths provided above.
Remember to use sorry for all proofs.

Please make sure you have '### Full Code\n```lean' and '### Theorem Code\n```lean' in your response so that I can find the Lean code easily.
You must not omit any part of the full code, because I will use that to directly cover the old one.
"""

    async def _try_compile(self,
                          service_name: str,
                          api_name: str,
                          code: str,
                          info: APITheoremGenerationInfo,
                          logger: Optional[Logger] = None) -> bool:
        """Try to compile the theorem code"""
        # Check if current theorem code exists
        current_theorem = info.project.get_test_lean("api", service_name, api_name)
        
        try:
            info.project.set_test_lean("api", service_name, api_name, code)
            
            # Try to build
            success, message = info.project.build()

            # input("Press Enter to continue...")
            
            if not success:
                if logger:
                    logger.error(f"Compilation failed: {message}")
                # Restore backup if exists
                if current_theorem:
                    info.project.set_test_lean("api", service_name, api_name, current_theorem)
                else:
                    info.project.del_test_lean("api", service_name, api_name)
            
            return success, message
        except Exception as e:
            if logger:
                logger.error(f"Compilation failed: {e}")
            return False, str(e)

    async def formalize_api_theorem(self,
                           service_name: str,
                           api_name: str,
                           info: APITheoremGenerationInfo,
                           logger: Optional[Logger] = None) -> bool:
        """Formalize all requirements for an API"""
        if logger:
            logger.info(f"Formalizing theorems for {service_name}.{api_name}")
        
        # Check dependencies
        for dep_api in info.api_dependencies.get(api_name, []):
            dep_service = None
            for service in info.project.services:
                if any(a.name == dep_api for a in service.apis):
                    dep_service = service.name
                    break
            if not dep_service or not info.is_api_formalized(dep_service, dep_api):
                if logger:
                    logger.error(f"Dependency {dep_api} not formalized yet")
                return False
        
        # Get requirements - Fix the access path
        requirements = info.api_requirements.get(service_name, {}).get(api_name, {}).requirements
        if not requirements:
            if logger:
                logger.warning(f"No requirements found for {service_name}.{api_name}")
            return True
        
        success = True
        for req_idx, requirement in enumerate(requirements):
            if logger:
                logger.info(f"Processing requirement {req_idx + 1}/{len(requirements)}")
            
            # Try to formalize
            full_code, theorem_code = await self._formalize_requirement(
                service_name=service_name,
                api_name=api_name,
                requirement=requirement,
                info=info,
                logger=logger
            )
            
            if not full_code or not theorem_code:
                success = False

            if logger:
                logger.info(f"Formalization result: success={success}")
                # print the api theorem code and the theorems
                logger.info(f"API theorem code: {info.project.get_test_lean('api', service_name, api_name)}")
                logger.info(f"API theorems: {info.get_api_theorems(service_name, api_name)}")

        if success:
            info.add_formalized_theorem_api(service_name, api_name)
        
        return success

    async def run(self,
                  info: APITheoremGenerationInfo,
                  logger: Optional[Logger] = None) -> APITheoremGenerationInfo:
        """Run the complete formalization process"""
        if logger:
            logger.info("Starting API theorem formalization")
        
        # Process APIs in topological order
        for service_api_group in info.api_topological_order:
            service_name, api_name = service_api_group[0], service_api_group[1]
            
            # Skip if already formalized
            if info.is_api_theorem_formalized(service_name, api_name):
                if logger:
                    logger.info(f"Skipping already formalized API {service_name}.{api_name}")
                continue
            
            # Formalize API
            await self.formalize_api_theorem(service_name, api_name, info, logger)
            
            # Save progress
            info.save()
        
        if logger:
            logger.info("API theorem formalization completed")
        
        return info 