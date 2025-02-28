from typing import Dict, List, Optional, Tuple
import json
from pathlib import Path
from logging import Logger

from src.utils.apis.langchain_client import _call_openai_completion_async
from src.utils.parse_project.parser import ProjectStructure
from src.pipeline.prove.api.types import APIProverInfo, ProverProjectStructure

class APIProver:
    """Prove theorems for formalized APIs"""
    
    SYSTEM_PROMPT = """
You are a formal verification expert tasked with proving theorems about formalized APIs in Lean 4.

Background:
We have completed several formalization steps:
1. Database tables are formalized as Lean 4 structures with their operations
2. APIs are formalized as Lean 4 functions with precise input/output types
3. Each API has a set of theorems describing its required properties
4. Dependencies are ordered topologically, and theorems for dependent APIs are already proved

Your task is to prove a specific theorem about an API's behavior.

Input:
1. The API's Lean 4 implementation
2. Complete theorem file including:
   - Proved theorems (with complete proofs)
   - Unproved theorems (marked with 'sorry')
3. Current import prefix with existing dependencies
4. Dependencies information:
   - Table implementations and their properties
   - Dependent APIs and their proved theorems
5. The specific theorem to prove

Output Format:
1. Analysis section explaining:
   - Theorem's meaning and requirements
   - Proof strategy and key steps
   - Required lemmas or helper functions
   - A draft proof of full import prefix and the theorem to help you extract the json later
   
2. JSON output with:
### Output
```json
{
    "import_prefix": "string",  // Additional imports needed
    "proof": "string"          // Complete theorem proof
}
```

Requirements:
1. Lean 4 Syntax:
   - Use correct Lean 4 syntax and tactics
   - Do not use Lean 3 syntax
   - Follow Lean 4 naming conventions
   - Use proper type annotations

2. Import Management:
   - Keep all existing imports
   - Add new imports only when needed
   - Use correct import paths for:
     * Mathlib components
     * Project-specific modules
     * Dependent APIs and tables
   - Example: 
     ```lean
     import Mathlib.Data.List.Basic
     import ProjectName.Database.TableName
     ```

3. Proof Style:
   - Add natural language comments before major steps
   - Explain complex tactics or reasoning
   - Use clear and meaningful variable names
   - Structure proof in logical sections
   - Example:
     ```lean
     theorem api_property : ∀ (input : InputType), PropertyType := by
       -- First handle the input validation
       intro input
       cases input with
       | valid => ...
       | invalid => ...
     ```

4. Proof Completeness:
   - No 'sorry' allowed anywhere in the proof
   - Prove all cases and conditions
   - Handle all edge cases
   - Complete each proof branch
   - Use available theorems from dependencies
   - Ensure all proof steps are valid
   - Continue until 'theorem proved' is shown
   - Only use tactics in the standard library, do not use other dependencies like Mathlib

5. Error Handling:
   - If compilation fails, the error will be shown
   - Fix any syntax or type errors
   - Address missing lemmas or theorems
   - Ensure proper scoping of variables
   - Verify tactic state at each step

Remember: The proof must be complete and valid in Lean 4. No parts of the proof can be skipped or marked with 'sorry'.

Hints:
- You can use unfold to expand the definition of a function
- You can write a not complete proof at first to see the proof state after the partial proof you provided, 
you will be provided with chances to refine and fix the proof later.
But remember never use sorry in the proof, if you want to provide part of the proof, just stop at that point without sorry after that.
- When asked to fix the proof, you should focus on the first error and keep the correct part of the proof to just rewrite the wrong part.
"""

    def __init__(self, model: str = "deepseek-r1", max_retries: int = 5):
        self.model = model
        self.max_retries = max_retries

    def _format_dependencies_prompt(self,
                                  project: ProverProjectStructure,
                                  api_name: str,
                                  table_deps: List[str],
                                  api_deps: List[str]) -> str:
        """Format the dependencies section of the prompt"""
        lines = ["# Dependencies\n"]
        
        # Add table dependencies
        if table_deps:
            lines.append("## Table Dependencies")
            for table_name in table_deps:
                service, table = project._find_table_with_service(table_name)
                if service and table:
                    lines.append(f"### Table {table_name}")
                    lines.append(f"Import Path: {project.get_lean_import_path('table', service, table_name)}")
                    lines.append(f"```lean\n{table.lean_code}\n```\n")
        
        # Add API dependencies with their proofs
        if api_deps:
            lines.append("## API Dependencies")
            for dep_api in api_deps:
                service, api = project._find_api_with_service(dep_api)
                if service and api:
                    lines.append(f"### API {dep_api}")
                    lines.append(f"#### Implementation")
                    lines.append(f"Import Path: {project.get_lean_import_path('api', service, dep_api)}")
                    lines.append(f"```lean\n{api.lean_code}\n```\n")
                    if api.lean_test_code:
                        lines.append(f"#### Theorems File")
                        lines.append(f"Import Path: {project.get_test_lean_import_path('api', service, dep_api)}")
                        lines.append(f"```lean\n{api.lean_test_code}\n```\n")
        
        return "\n".join(lines)
    
    def _format_api_prompt(self,
                          project: ProverProjectStructure,
                          api_name: str,
                          service_name: str,
                          theorem_idx: int,
                          api) -> str:
        """Format the API section of the prompt"""
        # put API implementation, test code, import prefix, and the current theorem to prove
        theorem = api.lean_theorems[theorem_idx]
        return f"""
# API Implementation
Import Path: {project.get_lean_import_path('api', service_name, api_name)}
```lean
{api.lean_code}
```

# Theorems File
Import Path: {project.get_test_lean_import_path('api', service_name, api_name)}
```lean
{api.lean_test_code}
```

# Import Prefix
```lean
{api.lean_prefix}
```

# Target Theorem
```lean
{theorem}
```
"""

    async def prove_theorem(self,
                          project: ProverProjectStructure,
                          service_name: str,
                          api_name: str,
                          theorem_idx: int,
                          table_deps: List[str],
                          api_deps: List[str],
                          history: List[Dict[str, str]] = None,
                          logger: Logger = None) -> bool:
        """Prove a single theorem"""
        service, api = project._find_api_with_service(api_name, service_name=service_name)
        if not service or not api:
            raise ValueError(f"API {api_name} not found")
            
        if theorem_idx >= len(api.lean_theorems):
            raise ValueError(f"Theorem index {theorem_idx} out of range")

        # Prepare prompts
        deps_prompt = self._format_dependencies_prompt(project, api_name, table_deps, api_deps)
        api_prompt = self._format_api_prompt(project, api_name, service_name, theorem_idx, api)
        
        user_prompt = f"""
{deps_prompt}

{api_prompt}

Use '### Output\n```json' to mark the JSON section.
"""

        history = history or []
        old_prefix = api.lean_prefix

        for attempt in range(self.max_retries):
            if attempt > 0:
                user_prompt = f"Compilation failed. Error:\n{compilation_error}\n\nPlease fix the proof.\n\nPlease make sure you have '### Output\n```json' in your response."

            if logger:
                logger.debug(f"Proving theorem {theorem_idx} for API {api_name} (attempt {attempt + 1}/{self.max_retries})")
                logger.model_input(f"User prompt: {user_prompt}")

            # Call LLM
            response = await _call_openai_completion_async(
                model=self.model,
                system_prompt=self.SYSTEM_PROMPT,
                user_prompt=user_prompt,
                history=history,
                temperature=0.0
            )

            if logger:
                logger.model_output(f"Response: {response}")

            if not response:
                if logger:
                    logger.error("Failed to get model response")
                continue

            # Extract JSON output
            try:
                json_str = response.split("### Output\n```json")[-1].split("```")[0].strip()
                output = json.loads(json_str)
                new_prefix = output["import_prefix"]
                proof = output["proof"]
            except Exception as e:
                if logger:
                    logger.error(f"Failed to parse output: {e}")
                compilation_error = str(e)
                continue

            # Update project structure
            project.set_test_lean_prefix("api", service_name, api_name, new_prefix)
            project.set_theorem_proof("api", service_name, api_name, theorem_idx, proof)
            full_code = project.concat_test_lean_code("api", service_name, api_name)
            # update file
            project.set_test_lean("api", service_name, api_name, full_code)

            # Try to build
            input("Press Enter to continue...")
            success, compilation_error = project.build(parse=True, only_errors=True, add_context=True, only_first=True)
            if success:
                if logger:
                    logger.debug(f"Successfully proved theorem {theorem_idx} for API: {api_name}")
                return True

            # Restore old state
            project.del_theorem_proof("api", service_name, api_name, theorem_idx)
            project.set_test_lean_prefix("api", service_name, api_name, old_prefix)
            full_code = project.concat_test_lean_code("api", service_name, api_name)
            project.set_test_lean("api", service_name, api_name, full_code)

            # Update history
            history.extend([
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": response}
            ])

            # Retry prompt
            user_prompt = f"Compilation failed. Error:\n{compilation_error}\n\nPlease fix the proof.\n\nPlease make sure you have '### Output\n```json' in your response."

        if logger:
            logger.error(f"Failed to prove theorem {theorem_idx} for API {api_name} after {self.max_retries} attempts")
        
        return False

    async def run(self,
                 prover_info: APIProverInfo,
                 output_path: Path,
                 logger: Logger = None) -> APIProverInfo:
        """Prove theorems for all APIs in topological order"""
        if not prover_info.api_topological_order:
            raise ValueError("No valid API topological order available")

        for service_name, api_name in prover_info.api_topological_order:
            service, api = prover_info.project._find_api_with_service(api_name, service_name)
            if not service or not api:
                continue
                
            for idx, theorem in enumerate(api.lean_theorems):
                if api.proved_theorems[idx]:  # Skip already proved theorems
                    continue
                    
                success = await self.prove_theorem(
                    project=prover_info.project,
                    service_name=service_name,
                    api_name=api_name,
                    theorem_idx=idx,
                    table_deps=prover_info.api_table_dependencies.get(api_name, []),
                    api_deps=prover_info.api_dependencies.get(api_name, []),
                    logger=logger
                )
                
            prover_info.save(output_path)

        return prover_info 