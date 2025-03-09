from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
from logging import Logger

from src.types.project import ProjectStructure, Service, Table, APIFunction, TableProperty, TableTheorem
from src.types.lean_file import LeanTheoremFile
from src.utils.apis.langchain_client import _call_openai_completion_async

class TableNegativeTheoremGenerator:
    """Generate negative theorems for failed table property proofs"""
    
    ROLE_PROMPT = """You are a theorem conversion expert for Lean 4 code, specializing in transforming unproved table property theorems into their negative forms to show the original statements were incorrect."""

    SYSTEM_PROMPT = """Background:
We need to convert unproved table property theorems into their negative forms to show the original statements were incorrect.

Task:
Convert the given theorem into its negative form following this structure:
{structure_template}

File Structure Requirements:
1. Keep Existing Parts:
   - All imports should remain unchanged
   - Helper functions can be modified if needed
   - Original theorem structure should be maintained

2. Conversion Requirements:
   - Comment should indicate the original statement was incorrect
   - Theorem should prove the negation of the original statement
   - Maintain type correctness and Lean 4 syntax

3. Common Conversion Patterns:
   - Add direct negation: ¬(original_statement)
   - Show contradiction: original_statement → False
   - Provide counterexample: ∃x, ¬P(x)

Return your response in three parts:
### Analysis
Step-by-step reasoning of your conversion strategy

### Lean Code
```lean
<complete file content with negative theorem>
```

### Output
```json
{
  "imports": "string of unchanged import statements",
  "helper_functions": "string of helper functions (modified if needed)",
  "comment": "/- Original statement was incorrect: <original comment> -/",
  "theorem_unproved": "string of negative theorem statement with sorry"
}
```"""

    RETRY_PROMPT = """
Lean theorem file content created from your previous response:
{lean_file}

Compilation failed with error:
{error}

Please fix the negative theorem while maintaining the same structure:
{structure_template}

Make sure to:
1. Address the specific compilation error
2. Maintain logical negation
3. Use correct Lean 4 syntax
4. Keep imports unchanged

Return both the corrected code and parsed fields.
Make sure you have "### Output\n```json" in your response so that I can find the Json easily."""

    def __init__(self, model: str = "qwen-max-latest", max_retries: int = 3):
        self.model = model
        self.max_retries = max_retries

    async def generate_negative_theorem(self,
                                     project: ProjectStructure,
                                     service: Service,
                                     table: Table,
                                     property: TableProperty,
                                     property_id: int,
                                     theorem: TableTheorem,
                                     theorem_id: int,
                                     logger: Optional[Logger] = None) -> bool:
        """Generate negative theorem for a failed proof"""
        if logger:
            logger.info(f"Generating negative theorem for {table.name} property with API {theorem.api_name}")

        # Get original theorem file
        pos_lean_file = theorem.theorem
        neg_lean_file = project.init_table_theorem(service.name, table.name, property_id, theorem_id, negative=True)
        if not pos_lean_file or not neg_lean_file:
            if logger:
                logger.error("No theorem file found")
            return False
            
        # Prepare prompts
        structure_template = LeanTheoremFile.get_structure(proved=False)
        system_prompt = self.SYSTEM_PROMPT.format(structure_template=structure_template)
        user_prompt = f"""
# Current Theorem File
{pos_lean_file.to_markdown()}
"""

        if logger:
            logger.model_input(f"Negative theorem generation prompt:\n{user_prompt}")
            
        # Try conversion with retries
        history = []
        error_message = None
        lean_file_content = None
        for attempt in range(self.max_retries):
            if logger:
                logger.info(f"Attempt {attempt + 1}/{self.max_retries}")

            # Backup current state
            neg_lean_file.backup()

            # Prepare prompt
            prompt = (self.RETRY_PROMPT.format(
                error=error_message,
                lean_file=lean_file_content,
                structure_template=structure_template
            ) if attempt > 0 else system_prompt + "\n\n" + user_prompt)
                
            # Call LLM
            response = await _call_openai_completion_async(
                model=self.model,
                system_prompt=self.ROLE_PROMPT,
                user_prompt=prompt,
                history=history,
                temperature=0.0
            )
            
            if logger:
                logger.model_output(f"Negative theorem generation response:\n{response}")
                
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

            project.update_lean_file(neg_lean_file, fields)
            
            # Try compilation
            success, error_message = project.build(parse=True, add_context=True, only_errors=True)
            lean_file_content = neg_lean_file.to_markdown()

            if success:
                if logger:
                    logger.info(f"Successfully generated negative theorem for {table.name} with API {theorem.api_name}")
                return True
                
            # Restore on failure
            project.restore_lean_file(neg_lean_file)
            history.extend([
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response}
            ])

        # Clean up on failure
        project.delete_table_theorem(service.name, table.name, property_id, theorem_id, negative=True)
        if logger:
            logger.error(f"Failed to generate negative theorem after {self.max_retries} attempts")
        return False

    async def generate(self,
                      project: ProjectStructure,
                      logger: Optional[Logger] = None) -> ProjectStructure:
        """Generate negative theorems for all failed table proofs"""
        if logger:
            logger.info(f"Generating negative table theorems for project: {project.name}")
            
        for service in project.services:
            for table in service.tables:
                if not table.properties:
                    continue
                for property_id, property in enumerate(table.properties):
                    if not property.theorems:
                        continue
                    for theorem_id, theorem in enumerate(property.theorems):
                        # Skip if theorem was proved or already has negative theorem
                        if not theorem.theorem or theorem.theorem.theorem_proved or theorem.theorem_negative:
                            continue
                            
                        await self.generate_negative_theorem(
                            project=project,
                            service=service,
                            table=table,
                            property=property,
                            property_id=property_id,
                            theorem=theorem,
                            theorem_id=theorem_id,
                            logger=logger
                        )

        return project