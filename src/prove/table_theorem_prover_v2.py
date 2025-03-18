from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
import json
from logging import Logger
import random
import asyncio

from src.types.project import ProjectStructure, Service, Table, APIFunction, TableTheorem
from src.types.lean_file import LeanTheoremFile
from src.utils.apis.langchain_client import _call_openai_completion_async

class TableTheoremProver:
    """Prove table theorems in Lean 4"""
    
    ROLE_PROMPT = """You are a formal verification expert tasked with proving theorems about database table properties in Lean 4. You excel at constructing rigorous mathematical proofs while maintaining clarity and correctness."""

    SYSTEM_PROMPT = """Background:
We need to prove theorems about table properties in Lean 4. Each theorem verifies how an API maintains a specific table invariant.

Task:
Complete the proof for the given theorem following this structure:
{structure_template}
There is a "theorem_unproved" field in the input theorem file, you should complete the proof for that theorem and return the complete theorem with proof in the "theorem_proved" field.

Input:
1. Dependencies information:
   - Table implementation
   - Related API implementation
   - Related API theorems
2. The theorem file with this unproved theorem
3. Example proofs

File Structure Requirements:
1. Keep Existing Parts:
   - Keep all imports and open commands
   - Keep all helper functions
   - Original theorem statement should be kept
   - Original comments should be kept

2. Proof Requirements:
   - Replace 'sorry' with complete proof
   - Use proper Lean 4 tactics
   - No 'sorry' allowed in final proof

3. Proof Style:
   - Add comments before each tactic
   - Follow Lean 4 conventions
   - Maintain readable formatting

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

    RETRY_SYSTEM_PROMPT = """Background:
We need to prove theorems about table properties in Lean 4. Each theorem verifies how an API maintains a specific table invariant.

Task:
Fix the proof based on the error message and proof state following this structure:
{structure_template}

Input:
1. Dependencies information:
   - Table implementation
   - Related API implementation
   - Related API theorems
2. The current proof attempt
3. Compilation error messages
4. The longest valid part of the proof
5. Unsolved goals at that point

Your task is to fix the proof while:
1. Maintaining the same theorem statement and structure
2. Addressing the specific compilation errors
3. Using the valid partial proof as a guide
4. Completing the remaining goals

File Structure Requirements:
1. Keep Existing Parts:
   - Keep all imports and open commands
   - Keep all helper functions
   - Original theorem statement should be kept
   - Original comments should be kept

2. Proof Requirements:
   - Replace 'sorry' with complete proof
   - Use proper Lean 4 tactics
   - No 'sorry' allowed in final proof

3. Proof Style:
   - Add comments before each tactic
   - Follow Lean 4 conventions
   - Maintain readable formatting

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

    INIT_PROMPT = """
1. Dependencies
{dependencies}

2. Current Theorem to prove
{lean_file}

3. Hints and examples

Hints:
1. If you see "unknown tactic", check tactic name and required imports
2. If you see "type mismatch", verify argument types carefully
3. If you need to figure out what is the output of a function given the input, you can use `unfold` to expand the definition of the function and then use `simp` to simplify the expression.
4. If you need to analyze a function call with different possible outcomes, use `cases` with the function and input params to divide the proof into different cases.
5. If the proving strategy seems wrong, consider alternative approaches
6. Use the unsolved goals to understand exactly what needs to be proved
7. Keep the working parts of the proof and fix the specific step that failed
8. If you see unknown function, maybe you have deleted some important imports or predefined helper functions that must be used here

Here are some examples of how to write proofs:
{static_examples}

Please make sure the fields in the json output are directly copied from the ### Lean Code part you write, for example the "theorem_proved" field should be the same as the theorem part in the ### Lean Code part, with comments between tactics you use.

Important: You are not allowed to change the theorem statement, only add proof. Please make sure the theorem part is exactly the same as the theorem part in the input theorem file, and I will check it for validation.

Make sure you have "### Output\n```json" in your response so that I can find the Json easily.

Please prove the given theorem.
"""

    RETRY_PROMPT = """
1. Dependencies
{dependencies}

2. Current theorem to fix
### Current theorem file content
{lean_file}

### Compilation error
{error}

### Valid part of the proof without any syntax error
```lean
{partial_proof}
```

### Unsolved goals after the valid part
{unsolved_goals}

3. Hints and examples

Hints:
1. If you see "unknown tactic", check tactic name and required imports
2. If you see "type mismatch", verify argument types carefully
3. If you need to figure out what is the output of a function given the input, you can use `unfold` to expand the definition of the function and then use `simp` to simplify the expression.
4. If you need to analyze a function call with different possible outcomes, use `cases` with the function and input params to divide the proof into different cases.
5. If the proving strategy seems wrong, consider alternative approaches
6. Use the unsolved goals to understand exactly what needs to be proved
7. Keep the working parts of the proof and fix the specific step that failed
8. If you see unknown function, maybe you have deleted some important imports or predefined helper functions that must be used here

Here are some examples of how to write proofs:
{static_examples}

{last_post_process_error}

Please make sure the fields in the json output are directly copied from the ### Lean Code part you write, for example the "theorem_proved" field should be the same as the theorem part in the ### Lean Code part, with comments between tactics you use.

Important: You are not allowed to change the theorem statement, only add proof. Please make sure the theorem part is exactly the same as the theorem part in the input theorem file, and I will check it for validation.
Make sure you have "### Output\n```json" in your response so that I can find the Json easily.

Please fix the proof.
"""

    STATIC_EXAMPLES = """
```lean
theorem userLoginPreservesUniquePhoneNumbers
    (phoneNumber : String)
    (password : String)
    (old_user_table : UserTable)
    (h_unique_initially : hasUniquePhoneNumbers old_user_table) :
    let (_, new_user_table) := userLogin phoneNumber password old_user_table;
    hasUniquePhoneNumbers new_user_table := by
  -- Unfold the definition of userLogin to analyze its structure
  unfold userLogin
  
  -- Split the proof based on the result of queryUserRecord
  cases h_query : queryUserRecord phoneNumber old_user_table <;> simp_all
  
  -- Case 1: User record does not exist (queryUserRecord = false)
  -- The table remains unchanged, so apply the initial uniqueness hypothesis
  <;> try { exact h_unique_initially }
  
  -- Case 2: User record exists (queryUserRecord = true)
  -- Further split based on the result of getStoredPassword
  <;> cases h_stored : getStoredPassword phoneNumber old_user_table <;> simp_all
  
  -- Subcase 2.1: No stored password (none)
  -- Subcase 2.2: Stored password found (some storedPassword)
  -- In both subcases, the table remains unchanged, so apply the initial uniqueness hypothesis
  <;> exact h_unique_initially
```
"""

    def __init__(self, model: str = "qwen-max-latest", max_retries: int = 3,
                 max_examples: int = 5, max_global_attempts: int = 3):
        self.model = model
        self.max_retries = max_retries
        self.max_examples = max_examples
        self.max_global_attempts = max_global_attempts

    def _collect_examples(self, project: ProjectStructure, n: int, negative: bool = False) -> List[str]:
        """Collect n random proved table theorems as examples"""
        proved_theorems = []
        
        for service in project.services:
            for table in service.tables:
                if table.properties:
                    for property in table.properties:
                        if property.theorems:
                            for theorem in property.theorems:
                                if negative:
                                    # Collect proved negative theorems
                                    if theorem.theorem_negative and theorem.theorem_negative.theorem_proved:
                                        proved_theorems.append(theorem.theorem_negative.generate_content())
                                else:
                                    # Collect proved positive theorems
                                    if theorem.theorem and theorem.theorem.theorem_proved:
                                        proved_theorems.append(theorem.theorem.generate_content())
                        
        # Randomly select n examples
        if len(proved_theorems) > n:
            return random.sample(proved_theorems, n)

        # For negative theorems, if not enough proved theorems, then use positive theorems
        if negative and len(proved_theorems) < n:
            for service in project.services:
                for table in service.tables:
                    if table.properties:
                        for property in table.properties:
                            if property.theorems:
                                for theorem in property.theorems:
                                    if theorem.theorem and theorem.theorem.theorem_proved:
                                        proved_theorems.append(theorem.theorem.generate_content())
                                        if len(proved_theorems) >= n:
                                            return proved_theorems
                                        
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
    
    def _post_process_response(self, fields: Dict[str, str], lean_file: LeanTheoremFile, logger: Optional[Logger] = None) -> Optional[str]:
        """Check for illegal content in the response
        
        Args:
            fields: Parsed fields from LLM response
            lean_file: Original theorem file to check against
            logger: Optional logger
            
        Returns:
            Error message if illegal content found, None otherwise
        """
        # Check for sorry in proved theorem
        if "theorem_proved" in fields:
            if "sorry" in fields["theorem_proved"].lower():
                if logger:
                    logger.warning("Found sorry in proved theorem")
                return "Last round returned a theorem proof with sorry inside. Please complete the proof without using sorry."

        # Check theorem statement matches
        if "theorem_proved" in fields and lean_file.theorem_unproved:
            # Extract theorem statement (everything before :=)
            original_stmt = lean_file.theorem_unproved.split(":=")[0].strip()
            proved_stmt = fields["theorem_proved"].split(":=")[0].strip()
            
            if original_stmt != proved_stmt:
                if logger:
                    logger.warning("Theorem statement mismatch")
                    logger.debug(f"Original: {original_stmt}")
                    logger.debug(f"Proved: {proved_stmt}")
                return "Last round modified the theorem statement. Please keep the original theorem statement exactly the same and only add the proof."
                
        return None

    async def prove_theorem(self,
                          project: ProjectStructure,
                          service: Service,
                          table: Table,
                          theorem: TableTheorem,
                          property_id: int,
                          theorem_id: int,
                          examples: List[str],
                          negative: bool = False,
                          logger: Optional[Logger] = None) -> bool:
        """Prove a single table theorem"""
        if logger:
            theorem_type = "negative" if negative else "positive"
            logger.info(f"Proving {theorem_type} theorem {theorem_id} for table {table.name}")
            
        # Select appropriate theorem file
        lean_file = theorem.theorem_negative if negative else theorem.theorem
        if not lean_file:
            if logger:
                logger.error(f"No theorem file found for table {table.name}")
            return False

        api = project.get_api(service.name, theorem.api_name)
        if not api:
            if logger:
                logger.error(f"No API found for table {table.name}")
            return False

        dependencies = self._format_dependencies(service, table, api, project, examples)
        
        # Prepare prompts
        structure_template = LeanTheoremFile.get_structure(proved=True)
        initial_system_prompt = self.SYSTEM_PROMPT.format(structure_template=structure_template)
        initial_user_prompt = self.INIT_PROMPT.format(
            dependencies=dependencies,
            lean_file=lean_file.to_markdown(),
            static_examples=self.STATIC_EXAMPLES
        )

        # Try proving with retries
        lean_file_content = None
        error_message = None
        partial_proof = None
        unsolved_goals = None
        last_post_process_error = ""  # Initialize post process error message

        for attempt in range(self.max_retries):
            if logger:
                logger.info(f"Attempt {attempt + 1}/{self.max_retries}")

            # Backup current state
            lean_file.backup()
                
            # Prepare prompt based on attempt number
            if attempt == 0:
                current_system_prompt = initial_system_prompt
                current_user_prompt = initial_user_prompt
            else:
                current_system_prompt = self.RETRY_SYSTEM_PROMPT.format(structure_template=structure_template)
                current_user_prompt = self.RETRY_PROMPT.format(
                    dependencies=dependencies,
                    lean_file=lean_file_content,
                    error=error_message,
                    partial_proof=partial_proof if partial_proof else "",
                    unsolved_goals=unsolved_goals if unsolved_goals else "",
                    static_examples=self.STATIC_EXAMPLES,
                    last_post_process_error=last_post_process_error  # Add error message to prompt
                )
                
            if logger:
                logger.model_input(f"System prompt:\n{current_system_prompt}")
                logger.model_input(f"User prompt:\n{current_user_prompt}")
                
            # Call LLM
            response = await _call_openai_completion_async(
                model=self.model,
                system_prompt=self.ROLE_PROMPT,
                user_prompt=f"{current_system_prompt}\n\n{current_user_prompt}",
                history=[],  # Empty history for each attempt
                temperature=0.0,
            )
            
            if logger:
                logger.model_output(f"Theorem proving response:\n{response}")
                
            if not response:
                await project.acquire_lock()
                project.restore_lean_file(lean_file)
                project.release_lock()
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
                last_post_process_error = ""  # Reset post process error
                await project.acquire_lock()
                project.restore_lean_file(lean_file)
                project.release_lock()
                continue

            # Post-process response
            await project.acquire_lock()
            try:
                post_process_error = self._post_process_response(fields, lean_file, logger)
                if post_process_error:
                    if logger:
                        logger.warning(f"Post-processing failed: {post_process_error}")
                    last_post_process_error = post_process_error  # Set error message for next attempt
                    project.restore_lean_file(lean_file)
                    project.release_lock()
                    continue

                last_post_process_error = ""  # Reset post process error if no issues found

                # Update theorem file
                project.update_lean_file(lean_file, fields)
                
                # Try compilation
                success, error_message = project.build(parse=True, add_context=True, only_errors=True, only_first=True)
                lean_file_content = lean_file.to_markdown()
                if success:
                    if logger:
                        logger.info(f"Successfully proved theorem for table {table.name}")
                    project.release_lock()
                    return True
                    
                # Try backward build to get proof state
                unsolved_goals, partial_proof = project.backward_build(lean_file)
                # If have partial proof but no error message, then we have found a correct proof
                if partial_proof and not unsolved_goals:
                    if logger:
                        logger.info(f"Successfully proved theorem for table {table.name}")
                    # set the proof state to the partial proof
                    project.update_lean_file(lean_file, {"theorem_proved": partial_proof})
                    project.release_lock()
                    return True
                elif not partial_proof and not unsolved_goals:
                    if logger:
                        logger.warning(f"Failed to find valid partial proof for {lean_file.theorem_proved}")
                    # restore the backup
                    # project.restore_lean_file(lean_file)
                    # return False
                    unsolved_goals = "Unknown"
                    partial_proof = "None of the tactics worked"
                
                # Restore on failure
                project.restore_lean_file(lean_file)
            finally:
                project.release_lock()
                
        return False 
    
    async def _prove_parallel(self,
                            project: ProjectStructure,
                            negative: bool = False,
                            logger: Optional[Logger] = None,
                            max_workers: int = 1) -> ProjectStructure:
        """Prove table theorems in parallel with dynamic examples"""
        if logger:
            theorem_type = "negative" if negative else "positive"
            logger.info(f"Proving table {theorem_type} theorems in parallel for project: {project.name}")

        for global_attempt in range(self.max_global_attempts):
            if logger:
                logger.info(f"Global attempt {global_attempt + 1}/{self.max_global_attempts}")

            # Initialize tracking structures
            theorem_queue: List[Tuple[Service, Table, TableTheorem, int, int]] = []
            unproved_count = 0

            # Collect all theorems that need proving
            for service in project.services:
                for table in service.tables:
                    if not table.properties:
                        continue
                    for property_id, property in enumerate(table.properties):
                        if not property.theorems:
                            continue
                        for theorem_id, theorem in enumerate(property.theorems):
                            # Check if theorem needs proving
                            if negative:
                                if not theorem.theorem_negative or theorem.theorem_negative.theorem_proved:
                                    continue
                            else:
                                if not theorem.theorem or theorem.theorem.theorem_proved:
                                    continue
                            
                            theorem_queue.append((service, table, theorem, property_id, theorem_id))
                            unproved_count += 1

            if unproved_count == 0:
                if logger:
                    logger.info("All theorems already proved")
                break

            if logger:
                logger.info(f"{unproved_count} theorems remain unproved")

            # Create semaphore to limit concurrent tasks
            sem = asyncio.Semaphore(max_workers)

            async def process_theorem(service: Service, table: Table, 
                                    theorem: TableTheorem, property_id: int,
                                    theorem_id: int, examples: List[LeanTheoremFile]) -> None:
                """Process a single theorem"""
                if logger:
                    logger.info(f"Processing theorem {theorem_id} for table: {table.name}")
                
                await self.prove_theorem(
                    project=project,
                    service=service,
                    table=table,
                    theorem=theorem,
                    property_id=property_id,
                    theorem_id=theorem_id,
                    examples=examples,
                    negative=negative,
                    logger=logger
                )

            async def process_with_semaphore(task_tuple: Tuple, examples: List[LeanTheoremFile]):
                service, table, theorem, property_id, theorem_id = task_tuple
                async with sem:
                    await process_theorem(service, table, theorem, property_id, theorem_id, examples)

            # Process theorems in batches
            while theorem_queue:
                # Collect fresh examples for this batch
                examples = self._collect_examples(project, self.max_examples, negative=negative)
                if logger:
                    logger.info(f"Collected {len(examples)} proof examples for next batch")

                # Create tasks for next batch of theorems
                tasks = []
                while len(tasks) < max_workers and theorem_queue:
                    task_tuple = theorem_queue.pop(0)
                    tasks.append(process_with_semaphore(task_tuple, examples))

                # Process batch of theorems
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

                if logger:
                    logger.info(f"Completed batch of {len(tasks)} theorems. {len(theorem_queue)} remaining")

            # Check if all theorems are proved after this attempt
            unproved_count = 0
            for service in project.services:
                for table in service.tables:
                    if not table.properties:
                        continue
                    for property in table.properties:
                        if not property.theorems:
                            continue
                        for theorem in property.theorems:
                            if negative:
                                if theorem.theorem_negative and not theorem.theorem_negative.theorem_proved:
                                    unproved_count += 1
                            else:
                                if theorem.theorem and not theorem.theorem.theorem_proved:
                                    unproved_count += 1

            if unproved_count == 0:
                if logger:
                    logger.info("All theorems proved successfully")
                break
            
            if logger:
                logger.info(f"{unproved_count} theorems remain unproved after attempt {global_attempt + 1}")

        return project

    async def prove(self,
                   project: ProjectStructure,
                   negative: bool = False,
                   logger: Optional[Logger] = None,
                   max_workers: int = 1) -> ProjectStructure:
        """Prove all table theorems in the project"""
        if logger:
            theorem_type = "negative" if negative else "positive"
            logger.info(f"Proving table {theorem_type} theorems for project: {project.name}")

        if max_workers > 1:
            return await self._prove_parallel(project, negative, logger, max_workers)

        # Original sequential logic
        for global_attempt in range(self.max_global_attempts):
            if logger:
                logger.info(f"Global attempt {global_attempt + 1}/{self.max_global_attempts}")
            
            # Track unproved theorems
            unproved_count = 0
            
            # Try to prove all unproved theorems
            for service in project.services:
                for table in service.tables:
                    if not table.properties:
                        continue
                    for property_id, property in enumerate(table.properties):
                        if not property.theorems:
                            continue
                        for theorem_id, theorem in enumerate(property.theorems):
                            # Check appropriate theorem based on negative flag
                            if negative:
                                if not theorem.theorem_negative or theorem.theorem_negative.theorem_proved:
                                    continue
                            else:
                                if not theorem.theorem or theorem.theorem.theorem_proved:
                                    continue
                            
                            # Collect fresh examples before each theorem attempt
                            examples = self._collect_examples(project, self.max_examples, negative=negative)
                            if logger:
                                logger.info(f"Collected {len(examples)} proof examples for {table.name} theorem {theorem_id}")
                            
                            success = await self.prove_theorem(
                                project=project,
                                service=service,
                                table=table,
                                theorem=theorem,
                                property_id=property_id,
                                theorem_id=theorem_id,
                                examples=examples,
                                negative=negative,
                                logger=logger
                            )
                            
                            if not success:
                                unproved_count += 1
                                if logger:
                                    theorem_type = "negative" if negative else "positive"
                                    logger.warning(f"Failed to prove {theorem_type} theorem for table: {table.name}")
                                
            # Check if all theorems are proved
            if unproved_count == 0:
                if logger:
                    logger.info("All theorems proved successfully")
                break
                
            if logger:
                logger.info(f"{unproved_count} theorems remain unproved")

        return project 