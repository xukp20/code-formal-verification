from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
import json
from logging import Logger
import random

from src.types.project import ProjectStructure, Service, Table, APIFunction, TableTheorem
from src.types.lean_file import LeanTheoremFile
from src.utils.apis.langchain_client import _call_openai_completion_async

class TableTheoremProver:
    """Prove table theorems in Lean 4"""
    
    ROLE_PROMPT = """You are a formal verification expert tasked with proving theorems about database table properties in Lean 4. You excel at constructing rigorous mathematical proofs while maintaining clarity and correctness."""

    SYSTEM_PROMPT = """Background:
We need to prove theorems about table properties in Lean 4. Each theorem verifies how an API maintains a specific table invariant.

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
   - Table implementation
   - Related API implementation
   - Related API theorems
2. The theorem file with this unproved theorem
3. Example proofs


File Structure Requirements:
1. Keep Existing Parts:
   - Keep all imports and open commands and add new if needed in the proof
    * You are provided with Mathlib and its dependencies as outside packages in addition to the in project files
   - Keep all helper functions and define new if needed in the proof
   - Original theorem statement should be kept
   - Original comments should be kept

2. Proof Requirements:
   - Replace 'sorry' with complete proof
   - Use proper Lean 4 tactics
   - No 'sorry' allowed in final proof

3. Proof Style:
   - Add comments before each of the tactics you use
   - Follow Lean 4 conventions
   - Maintain readable formatting

4. Common Patterns:
   - Use 'intro' for assumptions
   - Use 'cases' for pattern matching
   - Use 'simp' for simplification
   - Use 'unfold' for expanding definitions of functions

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
  "theorem_proved": "string of complete theorem with proof, only the theorem part not the comment and other parts"
}}
```

Hints:
1. If you see "unknown tactic", check tactic name and required imports
2. If you see "type mismatch", verify argument types carefully
3. If you need to figure out what is the output of a function given the input, you can use `unfold` to expand the definition of the function and then use `simp` to simplify the expression.
4. If you need to analyze a function call with different possible outcomes, use `cases` with the function and input params to divide the proof into different cases.
5. If the proving strategy seems wrong, consider alternative approaches
6. Use the unsolved goals to understand exactly what needs to be proved
7. Keep the working parts of the proof and fix the specific step that failed
8. If you see unknown function, maybe you have deleted some important imports or predefined helper functions that must be used here
9. Remember to add comments before each tactic you use like in the example above

Make sure you have "### Output\n```json" in your response so that I can find the Json easily."""

    STATIC_EXAMPLES = """
```lean
theorem user_login_preserves_unique_phone_numbers
  (phoneNumber : String)
  (password : String)
  (old_user_table : UserTable)
  (h_unique_initially : hasUniquePhoneNumbers old_user_table) :
  let (result, new_user_table) := performUserLogin phoneNumber password old_user_table;
  hasUniquePhoneNumbers new_user_table := 
by
  -- Step 1: Unfold the definition of performUserLogin
  unfold performUserLogin

  -- Step 2: Simplify the if-then-else expression
  simp

  -- Step 3: Analyze the two branches of the if-then-else
  cases queryUserRecord phoneNumber old_user_table <;> simp

  -- Step 4: In both branches, the output table is the same as the input table
  · -- Case 1: User record does not exist
    rw [h_unique_initially]

  · -- Case 2: User record exists
    rw [h_unique_initially]
```


```lean
theorem user_login_preserves_record_count
  (phoneNumber : String)
  (password : String)
  (old_user_table : UserTable)
  (h_exists : old_user_table.rows.any (fun row => row.phone_number == phoneNumber)) :
  let (result, new_user_table) := performUserLogin phoneNumber password old_user_table;
  new_user_table.rows.length = old_user_table.rows.length :=
by
  -- Step 1: Unfold the definition of performUserLogin
  unfold performUserLogin

  -- Step 2: Simplify the if-then-else expression using h_exists
  simp [h_exists]

  -- Step 3: Analyze the output table
  -- In both branches, the output table is the same as the input table
  cases queryUserRecord phoneNumber old_user_table <;> simp
```

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
1. If you see "unknown tactic", check tactic name and required imports
2. If you see "type mismatch", verify argument types carefully
3. If you need to figure out what is the output of a function given the input, you can use `unfold` to expand the definition of the function and then use `simp` to simplify the expression.
4. If you need to analyze a function call with different possible outcomes, use `cases` with the function and input params to divide the proof into different cases.
5. If the proving strategy seems wrong, consider alternative approaches
6. Use the unsolved goals to understand exactly what needs to be proved
7. Keep the working parts of the proof and fix the specific step that failed
8. If you see unknown function, maybe you have deleted some important imports or predefined helper functions that must be used here

Return the corrected proof in the same format.
Please make sure you have '### Output\n```json' in your response."""

    def __init__(self, model: str = "qwen-max-latest", max_retries: int = 3,
                 max_examples: int = 5, max_global_attempts: int = 3):
        self.model = model
        self.max_retries = max_retries
        self.max_examples = max_examples
        self.max_global_attempts = max_global_attempts

    def _collect_examples(self, project: ProjectStructure, n: int) -> List[str]:
        """Collect n random proved table theorems as examples"""
        proved_theorems = []
        
        for service in project.services:
            for table in service.tables:
                if table.properties:
                    for property in table.properties:
                        if property.theorems:
                            for theorem in property.theorems:
                                if theorem.theorem and theorem.theorem.theorem_proved:
                                    proved_theorems.append(theorem.theorem.generate_content())
                        
        # Randomly select n examples
        if len(proved_theorems) > n:
            return random.sample(proved_theorems, n)
        return proved_theorems

    def _format_dependencies(self, service: Service, table: Table, api: APIFunction, project: ProjectStructure,
                             examples: List[LeanTheoremFile]) -> str:
        """Format table dependencies and examples as markdown"""
        lines = []
        
        # Format table implementation
        lines.extend([
            "# Table Implementation",
            table.to_markdown(show_fields={"lean_structure": True})
        ])
        
        # Format API implementation
        lines.extend([
            "# API Implementation",
            api.to_markdown(show_fields={"lean_function": True})
        ])
        
        # Format API theorems
        lines.append("\n\n# API Theorems")
        for theorem in api.theorems:
            if theorem.theorem and theorem.theorem.theorem_proved:
                lines.extend([
                    theorem.theorem.to_markdown(),
                    "\n"
                ])
        
        # Format example proofs
        if examples:
            lines.append("\n\n# Example Proofs")
            for example in examples:
                lines.extend([
                    "```lean",
                    example,
                    "```",
                    "\n"
                ])
        
        return "\n".join(lines)

    async def prove_theorem(self,
                          project: ProjectStructure,
                          service: Service,
                          table: Table,
                          theorem: TableTheorem,
                          theorem_id: int,
                          examples: List[str],
                          logger: Optional[Logger] = None) -> bool:
        """Prove a single table theorem"""
        if logger:
            logger.info(f"Proving theorem {theorem_id} for table {table.name}")
            
        lean_file = theorem.theorem
        if not lean_file:
            if logger:
                logger.error(f"No theorem file found for table {table.name}")

        api = project.get_api(service.name, theorem.api_name)
        if not api:
            if logger:
                logger.error(f"No API found for table {table.name}")
            return False

        dependencies = self._format_dependencies(service, table, api, project, examples)

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
1. If you see "unknown tactic", check tactic name and required imports
2. If you see "type mismatch", verify argument types carefully
3. If you need to figure out what is the output of a function given the input, you can use `unfold` to expand the definition of the function and then use `simp` to simplify the expression.
4. If you need to analyze a function call with different possible outcomes, use `cases` with the function and input params to divide the proof into different cases.
5. If the proving strategy seems wrong, consider alternative approaches
6. Use the unsolved goals to understand exactly what needs to be proved
7. Keep the working parts of the proof and fix the specific step that failed
8. If you see unknown function, maybe you have deleted some important imports or predefined helper functions that must be used here

Example of writing style:
{self.STATIC_EXAMPLES}

Please make sure the fields in the json output are directly copied from the ### Lean Code part you write, for example the "theorem_proved" field should be the same as the theorem part in the ### Lean Code part, with comments between tactics you use.

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
                temperature=0.3
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
                # restore the backup
                project.restore_lean_file(lean_file)
                continue

            # Update theorem file
            project.update_lean_file(lean_file, fields)
            
            # Try compilation
            # input("Press Enter to continue...")
            success, error_message = project.build(parse=True, add_context=True, only_errors=True, only_first=True)
            
            if success:
                if logger:
                    logger.info(f"Successfully proved theorem for table {table.name}")
                return True
                
            # Try backward build to get proof state
            unsolved_goals, partial_proof = project.backward_build(lean_file)
            # 1. If have partial proof but no error message, then we have find a correct proof
            if partial_proof and not unsolved_goals:
                if logger:
                    logger.info(f"Successfully proved theorem for table {table.name}")
                # set the proof state to the partial proof
                project.update_lean_file(lean_file, {"theorem_proved": partial_proof})
                return True
            elif not partial_proof and not unsolved_goals:
                if logger:
                    logger.warning(f"Failed to find valid partial proof for {lean_file.theorem_proved}")
                # restore the backup
                project.restore_lean_file(lean_file)
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
        """Prove all table theorems in the project"""
        if logger:
            logger.info(f"Proving table theorems for project: {project.name}")
            
        for global_attempt in range(self.max_global_attempts):
            if logger:
                logger.info(f"Global attempt {global_attempt + 1}/{self.max_global_attempts}")
                
            # Track unproved theorems
            unproved_count = 0
            
            # Try to prove all unproved theorems
            for service in project.services:
                for table in service.tables:
                    if table.properties:
                        for property in table.properties:
                            if property.theorems:
                                for id, theorem in enumerate(property.theorems):
                                    if not theorem.theorem or theorem.theorem.theorem_proved:
                                        continue
                                    
                                    # Collect fresh examples before each theorem attempt
                                    examples = self._collect_examples(project, self.max_examples)
                                    if logger:
                                        logger.info(f"Collected {len(examples)} proof examples for {table.name} theorem {id}")
                                    
                                    success = await self.prove_theorem(
                                        project=project,
                                        service=service,
                                        table=table,
                                        theorem=theorem,
                                        theorem_id=id,
                                        examples=examples,
                                        logger=logger
                                    )
                                    
                                    if not success:
                                        unproved_count += 1
                                        if logger:
                                            logger.warning(f"Failed to prove theorem for table {table.name}")
                                
            # Check if all theorems are proved
            if unproved_count == 0:
                if logger:
                    logger.info("All theorems proved successfully")
                break
                
            if logger:
                logger.info(f"{unproved_count} theorems remain unproved")

        return project 