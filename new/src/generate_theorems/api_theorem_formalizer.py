from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
from logging import Logger

from src.types.project import ProjectStructure, Service, APIFunction, APITheorem
from src.types.lean_file import LeanTheoremFile
from src.utils.apis.langchain_client import _call_openai_completion_async

class APITheoremFormalizer:
    """Formalize API theorems into Lean 4 code"""
    
    ROLE_PROMPT = """You are a theorem formalizer for Lean 4 code, specializing in converting API requirements into formal theorems. You excel at creating precise mathematical representations of API behaviors while maintaining semantic correctness."""

    SYSTEM_PROMPT = """Background:
We need to formalize API requirements into Lean 4 theorems that verify API behavior.

Code Structure:
- APIs are implemented as Lean 4 functions
- Database tables are Lean 4 structures
- Each theorem verifies one specific requirement
- Use 'sorry' for all proofs

Task:
Convert an API requirement into a formal Lean 4 theorem following this structure:
{structure_template}

File Structure Requirements:
1. Imports Section:
   - Import all required APIs and tables from dependencies
   - Use correct import paths based on project structure
   - Example:
     ```lean
     import Project.Service.API
     import Project.Service.Table
     ```

2. Helper Functions:
   - In the theorem, you should avoid using the helper functions defined in the API file you need to verify, as they are not proved yet.
   - So you need to define any helper functions needed for the theorem in the theorem file.
   - Only when you are sure the helper function from the API file that you want to use is easy and clear enough so that it is correct and need no more proof, you can import and use it.
   - Keep functions small and focused
   - Example:
     ```lean
     def isValidState (table : Table) : Bool := ...
     def checkCondition (input : Type) : Bool := ...
     ```

3. Comment:
   - Use the original requirement text
   - Format as a Lean comment
   - Example:
     ```lean
     /- If the user exists, the operation should fail and return an error -/
     ```

4. Theorem:
   - Name should reflect the property being verified
   - Include all necessary parameters
   - Use 'sorry' for the proof
   - Example:
     ```lean
     theorem userExistsFailure
       (id : Nat) (old_table : UserTable) :
       isUserExists id old_table →
       let (result, new_table) := addUser id "name" old_table
       result = Error "User exists" ∧ new_table = old_table := by
         sorry
     ```

Hints:
1. State Management:
   - Track database state changes
   - Consider old vs new states
   - Handle all possible outcomes
2. Style:
   - Use clear variable names
   - Add helpful comments
   - Follow Lean 4 conventions
   - Maintain consistent formatting
3. Common Patterns:
   - For validation checks, include the conditions in theorem assumptions
   - For state changes, specify the relationship between old and new states
   - For error cases, ensure they're properly represented in the theorem


Return your response in three parts:
### Analysis
Step-by-step reasoning of your formalization process

### Lean Code
```lean
<complete file content following the structure template>
```

### Output  
```json
{{
  "imports": "string of import statements",
  "helper_functions": "string of helper function definitions",
  "comment": "string of original requirement as comment, write as a Lean comment",
  "theorem_unproved": "string of theorem statement with sorry"
}}
```

Important:
- Follow file structure exactly
- Include all necessary imports
- Define required helper functions
- Use original requirement as comment
- Make theorem specific and precise
- Use sorry for proofs


Make sure you have "### Output\n```json" in your response so that I can find the Json easily."""

    RETRY_PROMPT = """Compilation failed with error:
{error}

Please fix the Lean code while maintaining the same structure:
{structure_template}

Make sure to:
1. Address the specific compilation error
2. Maintain the same theorem logic
3. Use correct import paths
4. Follow Lean 4 syntax

Return both the corrected code and parsed fields.
Make sure you have "### Output\n```json" in your response so that I can find the Json easily."""

    def __init__(self, model: str = "qwen-max-latest", max_retries: int = 3):
        self.model = model
        self.max_retries = max_retries

    @staticmethod
    def _format_dependencies(api: APIFunction, project: ProjectStructure) -> str:
        """Format API dependencies as markdown"""
        lines = []
        
        # Format API dependencies
        if api.dependencies.apis:
            lines.append("# Dependent APIs")
            for dep_service_name, dep_api_name in api.dependencies.apis:
                dep_api = project.get_api(dep_service_name, dep_api_name)
                if dep_api:
                    lines.extend([
                        f"\n## {dep_service_name}.{dep_api_name}",
                        dep_api.to_markdown(show_fields={"lean_function": True})
                    ])
                    
        # Format table dependencies
        if api.dependencies.tables:
            lines.append("\n# Dependent Tables")
            for table_name in api.dependencies.tables:
                for service in project.services:
                    table = project.get_table(service.name, table_name)
                    if table:
                        lines.extend([
                            table.to_markdown(show_fields={"lean_structure": True})
                        ])
                        break
                        
        return "\n".join(lines)

    async def formalize_theorem(self,
                              project: ProjectStructure,
                              service: Service,
                              api: APIFunction,
                              theorem: APITheorem,
                              theorem_id: int,
                              logger: Optional[Logger] = None) -> bool:
        """Formalize a single API theorem"""
        if logger:
            logger.info(f"Formalizing theorem for {service.name}.{api.name}: {theorem.description}")

        # Initialize empty theorem file
        lean_file = project.init_api_theorem(service.name, api.name, theorem_id)
            
        # Format dependencies
        dependencies = self._format_dependencies(api, project)
        
        # Prepare prompts
        structure_template = LeanTheoremFile.get_structure(proved=False)
        system_prompt = self.SYSTEM_PROMPT.format(structure_template=structure_template)
        user_prompt = f"""
# Dependencies
{dependencies}

# API Information
Service: {service.name}

{api.to_markdown(show_fields={"lean_function": True})}

# Requirement to Formalize
{theorem.description}
"""

        if logger:
            logger.model_input(f"Theorem formalization prompt:\n{user_prompt}")
            
        # Try formalization with retries
        history = []
        error_message = None

        for attempt in range(self.max_retries):
            if logger:
                logger.info(f"Attempt {attempt + 1}/{self.max_retries}")

            # Backup current state
            lean_file.backup()
                
            # Prepare prompt
            prompt = (self.RETRY_PROMPT.format(
                error=error_message, 
                structure_template=structure_template
            ) if attempt > 0 else system_prompt + "\n\n" + user_prompt)
                
            if logger:
                logger.model_input(f"Theorem formalization prompt:\n{prompt}")
            # Call LLM
            response = await _call_openai_completion_async(
                model=self.model,
                system_prompt=self.ROLE_PROMPT,
                user_prompt=prompt,
                history=history,
                temperature=0.0
            )
            
            if logger:
                logger.model_output(f"Theorem formalization response:\n{response}")
                
            if not response:
                continue
                
            try:
                # Parse response
                json_str = response.split("```json")[-1].split("```")[0].strip()
                fields = json.loads(json_str)
            except Exception as e:
                if logger:
                    logger.error(f"Failed to process response: {e}")
                continue

            # Update theorem file
            project.update_lean_file(lean_file, fields)
            
            # Try compilation
            success, error = project.build(parse=True, add_context=True, only_errors=True)
            
            if success:
                if logger:
                    logger.info(f"Successfully formalized theorem for {api.name}")
                return True
                
            # Restore on failure
            project.restore_lean_file(lean_file)
            error_message = error
            history.extend([
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response}
            ])
                
        # Clean up on failure
        project.delete_api_theorem(service.name, api.name, theorem_id)
        if logger:
            logger.error(f"Failed to formalize theorem after {self.max_retries} attempts")
        return False

    async def formalize(self,
                       project: ProjectStructure,
                       logger: Optional[Logger] = None) -> ProjectStructure:
        """Formalize all API theorems in the project"""
        if logger:
            logger.info(f"Formalizing API theorems for project: {project.name}")
            
        for service in project.services:
            if logger:
                logger.info(f"Processing service: {service.name}")
                
            for api in service.apis:
                if logger:
                    logger.info(f"Processing API: {api.name}")
                    
                if not api.theorems:
                    if logger:
                        logger.warning(f"No theorems to formalize for API: {api.name}")
                    continue
                    
                for id, theorem in enumerate(api.theorems):
                    success = await self.formalize_theorem(
                        project=project,
                        service=service,
                        api=api,
                        theorem=theorem,
                        theorem_id=id,
                        logger=logger
                    )
                    
                    if not success:
                        if logger:
                            logger.error(f"Failed to formalize theorem for API: {api.name}")
                        break

        return project 