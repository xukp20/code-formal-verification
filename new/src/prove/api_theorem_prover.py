from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
import json
from logging import Logger
import random

from src.types.project import ProjectStructure, Service, APIFunction, APITheorem
from src.types.lean_file import LeanTheoremFile
from src.utils.apis.langchain_client import _call_openai_completion_async

class APITheoremProver:
    """Prove API theorems in Lean 4"""
    
    ROLE_PROMPT = """You are a formal verification expert tasked with proving theorems about formalized APIs in Lean 4. You excel at constructing rigorous mathematical proofs while maintaining clarity and correctness."""

    SYSTEM_PROMPT = """Background:
We need to prove theorems about API behavior in Lean 4. Each theorem verifies a specific property of an API.

We have completed several formalization steps:
1. Database tables are formalized as Lean 4 structures with their operations
2. APIs are formalized as Lean 4 functions with precise input/output types
3. Each API has a set of theorems describing its required properties


Task:
Complete the proof for the given theorem following this structure:
{structure_template}
There is a "theorem_unproved" field in the input theorem file, you should complete the proof for that theorem and return the complete theorem with proof in the "theorem_proved" field.

When your proof has compilation errors, I will help you by:
1. Finding the longest valid part of your proof
2. Showing you the unsolved goals at that point
3. This helps you understand exactly where the proof went wrong

Input:
1. Dependencies information:
   - Table implementations
   - Dependent APIs
2. The API's Lean 4 implementation
3. The theorem file with this unproved theorem
4. Example proofs


File Structure Requirements:
1. Keep Existing Parts and add necessary content: 
   - Keep all imports and open commands and add new if needed in the proof
    * You are provided with Mathlib and its dependencies as outside packages in addition to the in project files
   - Keep all helper functions and define new if needed in the proof
   - Original theorem statement should be kept
   - Original comments should be kept

2. Proof Requirements:
   - Replace 'sorry' with complete proof
   - Use proper Lean 4 tactics
   - Follow proof state carefully
   - No 'sorry' allowed in final proof

3. Proof Style:
   - Add comments before each of the tactics you use
   - Follow Lean 4 conventions
   - Maintain readable formatting

Write comprehensive comment before each step, for example:
```lean
theorem user_login_success {{phoneNumber : String}} {{password : String}} 
  (old_user_table : UserTable)
  (h_user_exists : queryUserRecord phoneNumber old_user_table)
  (h_password_matches : getStoredPassword phoneNumber old_user_table = some password)
  (h_unique_record : ¬ hasMultipleRecords phoneNumber old_user_table) :
  let (result, new_user_table) := performUserLogin phoneNumber password old_user_table;
  result = LoginResult.Success "登录成功" ∧ new_user_table = old_user_table := 
by
  -- Step 1: Unfold the definition of performUserLogin
  unfold performUserLogin

  -- Step 2: Simplify the first if condition using h_user_exists
  simp [h_user_exists]

  -- Step 3: Analyze the password validation step
  -- Unfold validatePassword to inspect its behavior
  unfold validatePassword

  -- Use h_password_matches to simplify the match expression
  simp [h_password_matches]
```

Return your response in three parts:
### Analysis
Step-by-step reasoning of your proof strategy

### Lean Code
```lean
<complete file content with proof>
```

### Output
```json
{{
  "imports": "string of imports, with addition to the original imports if new imports or open commands are added. If no change, you can ignore this field",
  "helper_functions": "string of helper functions or extra type definitions, with addition to the original helper functions or type definitions if new helper functions or type definitions are added. If no change, you can ignore this field",
  "theorem_proved": "string of complete theorem with proof, only the theorem part not the comment and other parts"
}}
```
- If you want to ignore the imports or helper functions, you should not include that field in the json dict. Don't return empty string for the field because it will be used to update the field to empty string.
- Make sure the fields in the json dict are directly copied from the ### Lean Code part you write, for example the "theorem_proved" field should be the same as the theorem part in the ### Lean Code part, with comments between tactics you use.
"""

    RETRY_PROMPT = """Proof attempt failed with error:
{error}

Current proof state:
### Valid part of the proof without any syntax error
```lean
{partial_proof}
```

### Unsolved goals after the valid part
{unsolved_goals}


Hints:
1. If you see "no goals to be solved", the proof may be complete at that point
2. If you see "unknown tactic", check tactic name and required imports
3. If you see "type mismatch", verify argument types carefully
4. If the proving strategy seems wrong, consider alternative approaches
5. Use the unsolved goals to understand exactly what needs to be proved
6. Keep the working parts of the proof and fix the specific step that failed
7. If you see unknown function, maybe you have deleted some important imports or predefined helper functions that must be used here

Please make sure you have '### Output\n```json' in your response."""

    def __init__(self, model: str = "qwen-max-latest", max_retries: int = 3, 
                 max_examples: int = 5, max_global_attempts: int = 3):
        self.model = model
        self.max_retries = max_retries
        self.max_examples = max_examples
        self.max_global_attempts = max_global_attempts

    def _collect_examples(self, project: ProjectStructure, n: int) -> List[str]:
        """Collect n random proved theorems as examples"""
        proved_theorems = []
        
        for service in project.services:
            for api in service.apis:
                for theorem in api.theorems:
                    if theorem.theorem and theorem.theorem.theorem_proved:
                        proved_theorems.append(theorem.theorem.generate_content())
                        
        # Randomly select n examples
        if len(proved_theorems) > n:
            return random.sample(proved_theorems, n)
        return proved_theorems

    def _format_dependencies(self, service: Service, api: APIFunction, project: ProjectStructure, 
                           examples: List[LeanTheoremFile]) -> str:
        """Format API dependencies and examples as markdown"""
        lines = []
        
        # Format API implementation
        lines.extend([
            "# API Implementation",
            api.to_markdown(show_fields={"lean_function": True})
        ])
        
        # Format dependencies
        if api.dependencies:
            # Format table dependencies
            if api.dependencies.tables:
                lines.append("# Table Dependencies")
                for table_name in api.dependencies.tables:
                    table = project.get_table(service.name, table_name)
                    if table:
                        lines.extend([
                            table.to_markdown(show_fields={"lean_structure": True})
                        ])
            
            # Format API dependencies
            if api.dependencies.apis:
                lines.append("# API Dependencies")
                for dep_api_info in api.dependencies.apis:
                    dep_api = project.get_api(service.name, dep_api_info["name"])
                    if dep_api:
                        lines.extend([
                            dep_api.to_markdown(show_fields={"lean_function": True})
                        ])
        
        # Format examples
        if examples:
            lines.append("# Example Proofs")
            for example in examples:
                lines.extend([
                    example,
                    "\n"
                ])

        return "\n".join(lines)

    async def prove_theorem(self,
                          project: ProjectStructure,
                          service: Service,
                          api: APIFunction,
                          theorem: APITheorem,
                          theorem_id: int,
                          examples: List[LeanTheoremFile],
                          logger: Optional[Logger] = None) -> bool:
        """Prove a single API theorem"""
        if logger:
            logger.info(f"Proving theorem {theorem_id} for API {api.name}")
            
        lean_file = theorem.theorem
        if not lean_file:
            if logger:
                logger.error(f"No theorem file found for API {api.name}")
            return False
        
        # Format dependencies
        dependencies = self._format_dependencies(service, api, project, examples)
        
        # Prepare prompts
        structure_template = LeanTheoremFile.get_structure(proved=True)
        system_prompt = self.SYSTEM_PROMPT.format(structure_template=structure_template)
        user_prompt = f"""
1. Dependencies
{dependencies}

2. Current Theorem to prove
```lean
{lean_file.generate_content()}
```


Note:
- Remember to add comments before each tactic you use so that you will think more carefully before using each tactic.

Hints:
- You can use "unfold" to expand the definition of a function
- You can write a not complete proof at first to see the proof state after the partial proof you provided, 
you will be provided with chances to refine and fix the proof later.
- But remember never use sorry in the proof, if you want to provide part of the proof, just stop at that point without sorry after that.
- You can use "rfl" to leave the unfinished steps with only the comment saying what to do next.
- When asked to fix the proof, you should focus on the first error and keep the correct part of the proof to just rewrite the wrong part.

Make sure you have "### Output\n```json" in your response so that I can find the Json easily.

Please prove the given theorem.
"""

        # Try proving with retries
        history = []
        error_message = None
        partial_proof = None
        unsolved_goals = None

        for attempt in range(self.max_retries):
            if logger:
                logger.info(f"Attempt {attempt + 1}/{self.max_retries}")

            # Backup current state
            lean_file.backup()
                
            # Prepare prompt
            prompt = (self.RETRY_PROMPT.format(
                error=error_message,
                partial_proof=partial_proof if partial_proof else "",
                unsolved_goals=unsolved_goals if unsolved_goals else "",
                structure_template=structure_template
            ) if attempt > 0 else system_prompt + "\n\n" + user_prompt)
                
            if logger:
                logger.model_input(f"Theorem proving prompt:\n{prompt}")
                
            # Call LLM
            response = await _call_openai_completion_async(
                model=self.model,
                system_prompt=self.ROLE_PROMPT,
                user_prompt=prompt,
                history=history,
                temperature=0.0
            )
            
            if logger:
                logger.model_output(f"Theorem proving response:\n{response}")
                
            if not response:
                continue
                
            try:
                # Parse response
                json_str = response.split("```json")[-1].split("```")[0].strip()
                fields = json.loads(json_str)
                assert "theorem_proved" in fields
            except Exception as e:
                if logger:
                    logger.error(f"Failed to process response: {e}")
                error_message = str(e)
                continue

            # Update theorem file
            project.update_lean_file(lean_file, fields)
            
            # Try compilation
            # input("Press Enter to continue...")
            success, error_message = project.build(parse=True, add_context=True, only_errors=True, only_first=True)
            
            if success:
                if logger:
                    logger.info(f"Successfully proved theorem for {api.name}")
                return True
                
            # Try backward build to get proof state
            unsolved_goals, partial_proof = project.backward_build(lean_file)
            # 1. If have partial proof but no error message, then we have find a correct proof
            if partial_proof and not unsolved_goals:
                if logger:
                    logger.info(f"Successfully proved theorem for {api.name}")
                # set the proof state to the partial proof
                project.update_lean_file(lean_file, {"theorem_proved": partial_proof})
                return True
            elif not partial_proof and not unsolved_goals:
                if logger:
                    logger.warning(f"Failed to find valid partial proof for {lean_file.theorem_proved}")
                return False
            
            # Restore on failure
            project.restore_lean_file(lean_file)
            history.extend([
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response}
            ])
                
        return False

    async def prove(self,
                   project: ProjectStructure,
                   logger: Optional[Logger] = None) -> ProjectStructure:
        """Prove all API thekn.orems in the project"""
        if logger:
            logger.info(f"Proving API theorems for project: {project.name}")
            
        for global_attempt in range(self.max_global_attempts):
            if logger:
                logger.info(f"Global attempt {global_attempt + 1}/{self.max_global_attempts}")
                
            # Collect examples
            examples = self._collect_examples(project, self.max_examples)
            if logger:
                logger.info(f"Collected {len(examples)} proof examples")
                
            # Track unproved theorems
            unproved_count = 0
            
            # Try to prove all unproved theorems
            for service in project.services:
                for api in service.apis:
                    for id, theorem in enumerate(api.theorems):
                        if not theorem.theorem or theorem.theorem.theorem_proved:
                            continue
                            
                        success = await self.prove_theorem(
                            project=project,
                            service=service,
                            api=api,
                            theorem=theorem,
                            theorem_id=id,
                            examples=examples,
                            logger=logger
                        )
                        
                        if not success:
                            unproved_count += 1
                            if logger:
                                logger.warning(f"Failed to prove theorem for API: {api.name}")
                                
            # Check if all theorems are proved
            if unproved_count == 0:
                if logger:
                    logger.info("All theorems proved successfully")
                break
                
            if logger:
                logger.info(f"{unproved_count} theorems remain unproved")

        return project 