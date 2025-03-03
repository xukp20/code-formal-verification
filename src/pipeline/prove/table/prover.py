from typing import Dict, List, Optional, Tuple
import json
from pathlib import Path
from logging import Logger

from src.utils.apis.langchain_client import _call_openai_completion_async
from src.utils.parse_project.parser import ProjectStructure
from src.pipeline.prove.api.types import APIProverInfo, ProverProjectStructure
from src.pipeline.prove.table.types import TableProverInfo
from src.utils.lean.build_parser import (
    parse_build_output_to_messages, 
    parse_lean_message_details,
    all_errors_are_unsolved_goals
)

class TableTheoremProver:
    """Prove theorems for formalized Table properties"""
    
    SYSTEM_PROMPT = """
You are a formal verification expert tasked with proving theorems about database table properties in Lean 4.

Background:
We have completed several formalization steps:
1. Database tables are formalized as Lean 4 structures with their operations
2. APIs are formalized as Lean 4 functions with precise input/output types
3. Each API has a set of theorems that have been proved
4. Each table property is related to exactly one API that modifies the table
5. We need to prove how the table property holds when the API is called

When your proof has compilation errors, I will help you by:
1. Finding the longest valid part of your proof
2. Showing you the unsolved goals at that point
3. This helps you understand exactly where the proof went wrong

Your task is to prove a specific theorem about a table property.

Input:
1. The Table's Lean 4 implementation
2. The related API's implementation and proved theorems
3. Complete table theorem file including:
   - Proved theorems (with complete proofs)
   - Unproved theorems (marked with 'sorry')
4. Current import prefix with existing dependencies
5. The specific theorem to prove

Output Format:
1. Analysis section explaining:
   - Theorem's meaning and requirements
   - How the API's behavior affects the table property
   - Proof strategy and key steps
   - Required lemmas or helper functions
   
2. JSON output with:
### Output
```json
{
    "import_prefix": "string",  // Add new necessary imports to the old import prefix
    "proof": "string"          // Complete theorem proof
}
```

Requirements:
1. Lean 4 Syntax:
   - Use correct Lean 4 syntax and tactics
   - Do not use Lean 3 syntax
   - Follow Lean 4 naming conventions
   - Use proper type annotations
   - Example:
    ```lean
    theorem table_theorem : ∀ (input : InputType), PropertyType := by
        intro input
        unfold some_function
        have some_hypothesis : some_property input := by
            ...
        simp [some_hypothesis]
     ```

2. Import Management:
   - Keep all existing imports
   - Add new imports only when needed
   - Use correct import paths
   - You are provided with Mathlib and its dependencies as outside packages in addition to the in project files
   - Example: 
     ```lean
     import Mathlib.Data.List.Basic
     import ProjectName.Database.TableName
     ```
   - Keep existing helper functions in the existing import prefix
   - ! You must make sure that the new import prefix include all the imports and helper functions in the existing import prefix

   3. Proof Style:
   - Keep all theorem content given to you. including the comment before the theorem and the theorem declaration
   - Only replace 'sorry' with the proof
   - Add natural language comments before major steps
   - Use the API's proved theorems when needed

4. Proof Completeness:
   - No 'sorry' allowed anywhere in the proof
   - ! You should keep all the theorem content give to you, only replacing sorry with the proof.

5. Error Handling:
   - If compilation fails, the error will be shown
   - Fix any syntax or type errors
   - Address missing lemmas or theorems

Remember: The final proof must be complete and valid in Lean 4. No parts of the proof can be skipped or marked with 'sorry'.

Hints:
- You can use "unfold" to expand the definition of a function
- You can write a not complete proof at first to see the proof state after the partial proof you provided, 
you will be provided with chances to refine and fix the proof later.
- But remember never use sorry in the proof, if you want to provide part of the proof, just stop at that point without sorry after that.
- You can use "rfl" to leave the unfinished steps with only the comment saying what to do next.
- When asked to fix the proof, you should focus on the first error and keep the correct part of the proof to just rewrite the wrong part.

"""

    def __init__(self, model: str = "deepseek-r1", max_retries: int = 5):
        self.model = model
        self.max_retries = max_retries

    def _format_dependencies_prompt(self,
                                  project: ProverProjectStructure,
                                  table_name: str,
                                  service_name: str,
                                  api_name: str) -> str:
        """Format the dependencies section of the prompt"""
        lines = ["# Dependencies\n"]
        
        # Add related API with its proofs
        service, api = project._find_api_with_service(api_name, service_name)
        if service and api:
            lines.append(f"## Related API: {api_name}")
            lines.append(f"### Implementation")
            lines.append(f"Import Path: {project.get_lean_import_path('api', service_name, api_name)}")
            lines.append(f"```lean\n{api.lean_code}\n```\n")
            if api.lean_test_code:
                lines.append(f"### Theorems (You can use the theorems that have been proved)")
                lines.append(f"Import Path: {project.get_test_lean_import_path('api', service_name, api_name)}")
                lines.append(f"```lean\n{api.lean_test_code}\n```\n")
        
        return "\n".join(lines)
    
    def _format_table_prompt(self,
                           project: ProverProjectStructure,
                           table_name: str,
                           service_name: str,
                           theorem_idx: int,
                           table) -> str:
        """Format the table section of the prompt"""
        theorem = table.lean_theorems[theorem_idx]
        return f"""
# Table Implementation
Import Path: {project.get_lean_import_path('table', service_name, table_name)}
```lean
{table.lean_code}
```

# Theorems File
Import Path: {project.get_test_lean_import_path('table', service_name, table_name)}
```lean
{table.lean_test_code}
```

# Import Prefix
```lean
{table.lean_prefix}
```

# Target Theorem
```lean
{theorem}
```
"""

    async def _try_backward_compile(self,
                                  project: ProverProjectStructure,
                                  service_name: str,
                                  table_name: str,
                                  theorem_idx: int,
                                  proof: str,
                                  logger: Optional[Logger] = None) -> Tuple[Optional[str], Optional[str]]:
        """Try to find the longest valid proof by backtracking
        
        Args:
            project: Project structure
            service_name: Service name
            table_name: Table name
            theorem_idx: Index of current theorem
            proof: Current theorem's proof
            logger: Optional logger
        
        Returns:
            Tuple of (error_message, partial_theorem)
            - If proof is complete: (None, complete_theorem)
            - If has unsolved goals: (first_unsolved_goals, partial_theorem)
            - If all attempts fail: (None, None)
        """
        # Backup original proof
        original_proof = proof
        
        # Split proof into lines
        lines = proof.splitlines()
        
        for i in range(len(lines)-1, -1, -1):
            # Try proof up to this line
            partial_proof = "\n".join(lines[:i+1])
            
            # Set the partial proof and get full code
            project.set_theorem_proof("table", service_name, table_name, theorem_idx, partial_proof)
            full_code = project.concat_test_lean_code("table", service_name, table_name)
            project.set_test_lean("table", service_name, table_name, full_code)
            
            # Try to build
            success, output = project._run_lake_build()
            if success:  # Build succeeded
                # Keep removing lines from the proof until the build fails
                for j in range(i, -1, -1):
                    partial_proof = "\n".join(lines[:j])
                    project.set_theorem_proof("table", service_name, table_name, theorem_idx, partial_proof)
                    full_code = project.concat_test_lean_code("table", service_name, table_name)
                    project.set_test_lean("table", service_name, table_name, full_code)
                    success, output = project._run_lake_build()
                    if not success:
                        partial_proof = "\n".join(lines[:j+1])
                        break

                # Restore original proof before returning
                project.set_theorem_proof("table", service_name, table_name, theorem_idx, original_proof)
                full_code = project.concat_test_lean_code("table", service_name, table_name)
                project.set_test_lean("table", service_name, table_name, full_code)
                return None, partial_proof
                
            # Parse errors
            messages = parse_build_output_to_messages(output)
            if not messages:
                continue
                
            # Check if all errors are unsolved goals
            if all_errors_are_unsolved_goals(messages):
                # Get first unsolved goals error
                details = parse_lean_message_details(messages, only_errors=True)
                if details:
                    unsolved_goals = details[0]["content"]
                    # Restore original proof before returning
                    project.set_theorem_proof("table", service_name, table_name, theorem_idx, original_proof)
                    full_code = project.concat_test_lean_code("table", service_name, table_name)
                    project.set_test_lean("table", service_name, table_name, full_code)
                    return unsolved_goals, partial_proof
        
        # Restore original proof if no valid partial proof found
        project.set_theorem_proof("table", service_name, table_name, theorem_idx, original_proof)
        full_code = project.concat_test_lean_code("table", service_name, table_name)
        project.set_test_lean("table", service_name, table_name, full_code)
        return None, None

    def _format_retry_prompt(self,
                           compilation_error: str,
                           partial_proof: Optional[str] = None,
                           unsolved_goals: Optional[str] = None) -> str:
        """Format the retry prompt with backtracking information"""
        prompt = f"""Compilation failed. Error:
{compilation_error}

"""
        if partial_proof and unsolved_goals:
            prompt += f"""Valid part of the proof:
```lean
{partial_proof}
```

Current unsolved goals:
{unsolved_goals}

"""
        
        prompt += """Please fix the proof.

Hints:
1. If you see "no goals to be solved", the proof may be complete at that point
2. If you see "unknown tactic", check tactic name and required imports
3. If you see "type mismatch", verify argument types carefully
4. If the proving strategy seems wrong, consider alternative approaches
5. Use the unsolved goals to understand exactly what needs to be proved
6. Keep the working parts of the proof and fix the specific step that failed

Please make sure you have '### Output\n```json' in your response."""
        
        return prompt

    async def prove_theorem(self,
                          project: ProverProjectStructure,
                          service_name: str,
                          table_name: str,
                          theorem_idx: int,
                          api_name: str,
                          history: List[Dict[str, str]] = None,
                          logger: Logger = None) -> bool:
        """Prove a single theorem"""
        service, table = project._find_table_with_service(table_name)
        if not service or not table:
            raise ValueError(f"Table {table_name} not found")
            
        if theorem_idx >= len(table.lean_theorems):
            raise ValueError(f"Theorem index {theorem_idx} out of range")

        # Prepare prompts
        deps_prompt = self._format_dependencies_prompt(project, table_name, service_name, api_name)
        table_prompt = self._format_table_prompt(project, table_name, service_name, theorem_idx, table)

        history = history or []
        old_prefix = table.lean_prefix

        compilation_error = None
        partial_proof = None
        unsolved_goals = None
        for attempt in range(self.max_retries):
            if attempt > 0:
                user_prompt = self._format_retry_prompt(compilation_error, partial_proof, unsolved_goals)
            else:
                user_prompt = self.SYSTEM_PROMPT + f"""
{deps_prompt}

{table_prompt}

Use '### Output\n```json' to mark the JSON section.
"""

            if logger:
                logger.debug(f"Proving theorem {theorem_idx} for table {table_name} (attempt {attempt + 1}/{self.max_retries})")
                logger.model_input(user_prompt)

            # Call LLM
            response = await _call_openai_completion_async(
                model=self.model,
                system_prompt="You are a Lean 4 language expert skilled in formal proof writing.",
                user_prompt=user_prompt,
                history=history,
                temperature=0.3
            )

            if logger:
                logger.model_output(response)

            if not response:
                if logger:
                    logger.error("Failed to get model response")
                continue

            # Extract JSON output
            try:
                json_str = response.split("```json")[-1].split("```")[0].strip()
                output = json.loads(json_str)
                new_prefix = output["import_prefix"]
                proof = output["proof"]
            except Exception as e:
                if logger:
                    logger.error(f"Failed to parse output: {e}")
                compilation_error = str(e)
                continue

            # Update project structure
            project.set_test_lean_prefix("table", service_name, table_name, new_prefix)
            project.set_theorem_proof("table", service_name, table_name, theorem_idx, proof)
            full_code = project.concat_test_lean_code("table", service_name, table_name)
            project.set_test_lean("table", service_name, table_name, full_code)

            # Try to build
            success, compilation_error = project.build(parse=True, only_errors=True, add_context=True, only_first=True)
            
            if not success:
                # Try backtracking to find valid partial proof
                unsolved_goals, partial_proof = await self._try_backward_compile(
                    project=project,
                    service_name=service_name,
                    table_name=table_name,
                    theorem_idx=theorem_idx,
                    proof=proof,  # Pass just the current theorem's proof
                    logger=logger
                )
                
                if unsolved_goals is None and partial_proof:
                    # Found complete proof through backtracking
                    project.set_theorem_proof("table", service_name, table_name, theorem_idx, partial_proof)
                    full_code = project.concat_test_lean_code("table", service_name, table_name)
                    project.set_test_lean("table", service_name, table_name, full_code)
                    success, _ = project.build(parse=True, only_errors=True, add_context=True, only_first=True)
                    if success:
                        return True
                    else:
                        if logger:
                            logger.error(f"Partial proof is not complete from backtracking")
                        project.set_theorem_proof("table", service_name, table_name, theorem_idx, proof)
                        full_code = project.concat_test_lean_code("table", service_name, table_name)
                        project.set_test_lean("table", service_name, table_name, full_code)
            else:
                return True

            # Restore old state if not successful
            project.del_theorem_proof("table", service_name, table_name, theorem_idx)
            project.set_test_lean_prefix("table", service_name, table_name, old_prefix)
            full_code = project.concat_test_lean_code("table", service_name, table_name)
            project.set_test_lean("table", service_name, table_name, full_code)

            # Update history with this attempt
            history.extend([
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": response}
            ])

        if logger:
            logger.error(f"Failed to prove theorem {theorem_idx} for table {table_name} after {self.max_retries} attempts")
        
        return False

    async def run(self,
                 prover_info: APIProverInfo,
                 output_path: Path,
                 max_theorem_retries: int = 4,
                 logger: Logger = None) -> TableProverInfo:
        """Prove theorems for all tables in topological order"""
        # Convert APIProverInfo to TableProverInfo
        table_prover_info = TableProverInfo.from_api_prover_info(prover_info)
        
        if not table_prover_info.topological_order:
            raise ValueError("No valid table topological order available")

        for table_name in table_prover_info.topological_order:
            service, table = table_prover_info.project._find_table_with_service(table_name)
            service_name = service.name
            if not service or not table:
                continue
                
            for idx, theorem in enumerate(table.lean_theorems):
                if table.proved_theorems[idx]:  # Skip already proved theorems
                    continue
                
                # Get the related API for this theorem
                api_name = table_prover_info.table_theorem_dependencies[service_name][table_name][idx]
                
                # Outer retry loop for fresh attempts
                for attempt in range(max_theorem_retries):
                    if logger:
                        logger.info(f"Starting fresh attempt {attempt + 1}/{max_theorem_retries} "
                                  f"for theorem {idx} of table {table_name}")
                    
                    success = await self.prove_theorem(
                        project=table_prover_info.project,
                        service_name=service_name,
                        table_name=table_name,
                        theorem_idx=idx,
                        api_name=api_name,
                        logger=logger
                    )
                    
                    if success:
                        if logger:
                            logger.info(f"Successfully proved theorem {idx} of table {table_name} "
                                      f"on attempt {attempt + 1}")
                        break
                    
                    if logger and attempt < max_theorem_retries - 1:
                        logger.warning(f"Failed to prove theorem {idx} of table {table_name} "
                                     f"on attempt {attempt + 1}, starting fresh attempt")
                
                if not success and logger:
                    logger.error(f"Failed to prove theorem {idx} of table {table_name} "
                               f"after {max_theorem_retries} fresh attempts")
                
                # Save progress
                table_prover_info.save(output_path)

        return table_prover_info 