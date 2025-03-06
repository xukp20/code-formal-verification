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

Write comprehensive comment before each step, for example:
```lean
-- Step 1: Unfold the definition of performUserLogin
unfold performUserLogin
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
  "theorem_proved": "string of complete theorem with proof, only the theorem part not the comment and other parts"
}}
```

Hints:
- You can use "unfold" to expand the definition of a function
- You can write a not complete proof at first to see the proof state after the partial proof you provided, 
you will be provided with chances to refine and fix the proof later.
- But remember never use sorry in the proof, if you want to provide part of the proof, just stop at that point without sorry after that.
- You can use "rfl" to leave the unfinished steps with only the comment saying what to do next.
- When asked to fix the proof, you should focus on the first error and keep the correct part of the proof to just rewrite the wrong part.

Make sure you have "### Output\n```json" in your response so that I can find the Json easily."""

    RETRY_PROMPT = """Proof attempt failed with error:
{error}

Current proof state:
### Valid part of the proof without any syntax error
```lean
{partial_proof}
```

### Unsolved goals after the valid part
{unsolved_goals}

Please fix the proof while maintaining the same strategy:
{structure_template}

Focus on:
1. Addressing the specific error
2. Following the proof state
3. Using correct tactics
4. Maintaining proof structure

Return the corrected proof in the same format."""

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
                for theorem in table.theorems:
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
        lines.append("# API Theorems")
        for theorem in api.theorems:
            if theorem.theorem and theorem.theorem.theorem_proved:
                lines.extend([
                    theorem.theorem.to_markdown(),
                    "\n"
                ])
        
        # Format example proofs
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
            theorem.backup()
                
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
                continue

            # Update theorem file
            project.update_lean_file(lean_file, {"theorem_proved": fields["theorem_proved"]})
            
            # Try compilation
            # input("Press Enter to continue...")
            success, error_message = project.build(parse=True, add_context=True, only_errors=True)
            
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
                
            # Collect examples
            examples = self._collect_examples(project, self.max_examples)
            if logger:
                logger.info(f"Collected {len(examples)} proof examples")
                
            # Track unproved theorems
            unproved_count = 0
            
            # Try to prove all unproved theorems
            for service in project.services:
                for table in service.tables:
                    for property in table.properties:
                        for id, theorem in enumerate(property.theorems):
                            if not theorem.theorem or theorem.theorem.theorem_proved:
                                continue
                                
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