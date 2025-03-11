from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import json
from logging import Logger

from src.types.project import ProjectStructure, Service, Table
from src.types.lean_file import LeanStructureFile
from src.utils.apis.langchain_client import _call_openai_completion_async

class TableFormalizer:
    """Formalize tables into Lean 4 structures"""
    
    ROLE_PROMPT = """You are a formal verification expert specializing in translating database schemas into Lean 4 code. You excel at creating precise mathematical representations of data structures while maintaining their relationships and constraints."""

    SYSTEM_PROMPT = """Background:
This software project uses multiple database tables with potential dependencies. You will formalize these tables into Lean 4 code.

Task:
Convert the given table definition into Lean 4 code following these requirements:

1. Follow the exact file structure:
{structure_template}

2. Table Relationships:
   - Include references to dependent tables in the structure
   - Add validation methods for referential integrity
   - Use correct import paths for dependencies

3. Row Structure:
   - Define structure for individual rows
   - Include all columns with appropriate types
   - Example:
     ```lean
     structure UserRow where
       id: Nat
       name: String
       email: String
       age: Option Nat
       deriving Repr
     ```

4. Table Structure:
   - Define main table structure containing rows
   - Example:
     ```lean
     structure UserTable where
       rows: List UserRow
       deriving Repr
     ```

Return your response in three parts:
### Analysis
Step-by-step reasoning of your formalization approach

### Lean Code
```lean
<complete file content following the structure template>
```

### Output
```json
{{
  "imports": "string of import statements and open commands",
  "structure_definition": "string of structure definitions"
}}
```

The fields in the Json don't have the prefix of "-- field name in it". 
Make sure you have "### Output\n```json" in your response so that I can find the Json easily.
"""

    RETRY_PROMPT = """Compilation failed with error:
{error}

Please fix the Lean code while maintaining the same structure:
{structure_template}

Return both the corrected code and parsed fields.
Make sure you have "### Output\n```json" in your response so that I can find the Json easily.
"""

    def __init__(self, model: str = "qwen-max-latest", max_retries: int = 3):
        self.model = model
        self.max_retries = max_retries

    @staticmethod
    def _format_dependencies(project: ProjectStructure, service: Service, 
                           table: Table) -> str:
        """Format dependent tables with their descriptions and Lean code"""
        if table.dependencies.tables:
            lines = ["# Table Dependencies"]
            for dep_name in table.dependencies.tables:
                dep_table = project.get_table(service.name, dep_name)
                if not dep_table:
                    continue
                    
                lines.extend([
                    dep_table.to_markdown(show_fields={"description": True, "lean_structure": True})
                ])
        else:
            lines = []
        return "\n".join(lines)

    @staticmethod
    def _format_input(table: Table) -> str:
        """Format current table description"""
        return table.to_markdown(show_fields={"description": True})

    @staticmethod
    def _format_user_prompt(project: ProjectStructure, service: Service, 
                           table: Table) -> str:
        """Format the complete user prompt"""
        parts = [
            "# Table Formalization",
            f"Service: {service.name}",
            TableFormalizer._format_dependencies(project, service, table),
            "# Current Table",
            TableFormalizer._format_input(table),
            "Make sure you have '### Output\n```json' in your response so that I can find the Json easily."
        ]
        return "\n".join(parts)

    async def formalize_table(self, project: ProjectStructure, service: Service, 
                            table: Table, logger: Logger = None) -> bool:
        """Formalize a single table"""
        if logger:
            logger.debug(f"Formalizing table: {service.name}.{table.name}")
            
        # Initialize Lean file
        lean_file = project.init_table_structure(service.name, table.name)
        if not lean_file:
            if logger:
                logger.error(f"Failed to initialize Lean file for {table.name}")
            return False
            
        # Prepare prompts
        structure_template = LeanStructureFile.get_structure()
        system_prompt = self.SYSTEM_PROMPT.format(structure_template=structure_template)
        user_prompt = self._format_user_prompt(project, service, table)
        
        if logger:
            logger.model_input(f"Role prompt:\n{self.ROLE_PROMPT}")
            
        # Try formalization with retries
        history = []
        error_message = None

        for attempt in range(self.max_retries):
            # Backup current state
            lean_file.backup()
            
            # Call LLM
            prompt = (self.RETRY_PROMPT.format(error=error_message, 
                     structure_template=structure_template) if attempt > 0 
                     else f"{system_prompt}\n\n{user_prompt}")
            
            if logger:
                logger.model_input(f"Prompt:\n{prompt}")
                
            response = await _call_openai_completion_async(
                model=self.model,
                system_prompt=self.ROLE_PROMPT,
                user_prompt=prompt,
                history=history,
                temperature=0.0
            )

            history.extend([
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response if response else "Failed to get LLM response"}
            ])
            
            if logger:
                logger.model_output(f"LLM response:\n{response}")
                
            if not response:
                if logger:
                    logger.error("Failed to get LLM response")
                error_message = "Failed to get LLM response"
                project.restore_lean_file(lean_file)
                continue
                
            # Parse response
            try:
                lean_code = response.split("### Lean Code\n```lean")[-1].split("```")[0].strip()
                json_str = response.split("### Output\n```json")[-1].split("```")[0].strip()
                fields = json.loads(json_str)
            except Exception as e:
                if logger:
                    logger.error(f"Failed to parse LLM response: {e}")
                error_message = str(e)
                project.restore_lean_file(lean_file)
                continue

                            
            # Update Lean file
            project.update_lean_file(lean_file, fields)
            
            # Try compilation
            success, error_message = project.build(parse=True, add_context=True, only_errors=True)
            if success:
                if logger:
                    logger.debug(f"Successfully formalized table: {table.name}")
                return True
                
            # Restore on failure
            project.restore_lean_file(lean_file)
                
        # Clean up on failure
        project.delete_table_structure(service.name, table.name)
        if logger:
            logger.error(f"Failed to formalize table {table.name} after {self.max_retries} attempts")
        
        return False

    async def formalize(self, project: ProjectStructure, logger: Logger = None) -> ProjectStructure:
        """Formalize all tables in the project"""
        if logger:
            logger.info(f"Formalizing tables for project: {project.name}")
            
        # Process each service
        for service in project.services:
            if not service.table_topological_order:
                if logger:
                    logger.warning(f"No topological order for service {service.name}, skipping")
                continue
                
            if logger:
                logger.info(f"Processing service: {service.name}")
                
            # Process tables in topological order
            for table_name in service.table_topological_order:
                table = project.get_table(service.name, table_name)
                if not table:
                    continue
                    
                success = await self.formalize_table(project, service, table, logger)
                if not success:
                    if logger:
                        logger.error(f"Failed to formalize table {table_name}, stopping service {service.name}")
                    break
                    
        return project 