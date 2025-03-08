from typing import Dict, List, Optional, Set, Tuple
import json
import yaml
from pathlib import Path
from src.utils.parse_project.parser import ProjectStructure
from src.utils.apis.langchain_client import _call_openai_completion_async
from src.pipeline.formalize.table.types import TableDependencyInfo, TableFormalizationInfo
from logging import Logger


class TableFormalizer:
    """Formalize tables to Lean 4 code"""
    
    SYSTEM_PROMPT = """
You are a formal verification expert tasked with formalizing database tables into Lean 4 code.

Background:
This software project uses multiple database tables with potential dependencies. You will be provided with:
1. A table description to formalize
2. Its target Lean file path relative to the project root
3. Descriptions and Lean 4 code of tables it depends on

Task:
Convert the given table definition into Lean 4 code following these specific requirements:

1. Import Dependencies
   - Use correct import paths for all dependent tables
   - Import paths should match the project structure
   - All the imports should be in the front of the file
   - You can open the imported namespace to use the types without prefix
   - Example: `import ProjectName.Database.DependentTable`
   - You should define a namespace for current file, and put all the code in the namespace, so that other files can open the namespace to use the types without prefix

2. Table Relationships
   - For foreign key relationships:
     * Include reference to parent table in the table structure other than the rows
     * Add validation methods to ensure referential integrity

3. Row Structure
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

4. Table Structure
   - Define main table structure containing rows
   - Example:
     ```lean
     structure UserTable where
       rows: List UserRow
       deriving Repr
     ```

5. Compilation Requirements
   - Code must compile successfully
   - All types must be properly defined
   - All dependencies must be correctly imported

Return your analysis in this format:
### Analysis
Step-by-step reasoning of your formalization approach

### Lean Code
```lean
<complete file content>
```

Please make sure you have '### Lean Code\n```lean' in your response so that I can find the Lean code easily.
"""

    def __init__(self, model: str = "deepseek-r1", max_retries: int = 3):
        self.model = model
        self.max_retries = max_retries

    def _format_dependencies_prompt(self, 
                                  project: ProjectStructure,
                                  dependencies: List[str]) -> str:
        """Format the prompt section for dependent tables"""
        lines = []
        if dependencies:
            lines.append("# Dependent Tables\n")
            for dep_name in dependencies:
                for service in project.services:
                    for table in service.tables:
                        if table.name == dep_name:
                            lines.append(project._table_to_markdown(service, table))
                            lines.append("\n")
        return "\n".join(lines)

    def _format_current_table_prompt(self,
                                   project: ProjectStructure,
                                   service_name: str,
                                   table_name: str) -> str:
        """Format the prompt section for the current table"""
        lines = ["# Current Table\n"]
        
        # Find the table
        service, table = project._find_table_with_service(table_name)
        if not service or not table:
            raise ValueError(f"Table {table_name} not found")
            
        # Add table description
        lines.append(project._table_to_markdown(service, table))
        
        # Add Lean path
        lines.append("\n### Target Lean Path")
        lines.append(f"`{project.get_lean_import_path('table', service_name, table_name)}`")
        
        return "\n".join(lines)

    async def formalize_table(self,
                            project: ProjectStructure,
                            table_name: str,
                            dependencies: List[str],
                            history: List[Dict[str, str]] = None,
                            logger: Logger = None) -> bool:
        """Formalize a single table"""
        # Find the table's service
        service, table = project._find_table_with_service(table_name)
        if not service or not table:
            raise ValueError(f"Table {table_name} not found")

        # Prepare prompts
        deps_prompt = self._format_dependencies_prompt(project, dependencies)
        table_prompt = self._format_current_table_prompt(project, service.name, table_name)
        user_prompt = f"{deps_prompt}\n{table_prompt}"

        if logger:
            logger.debug(f"Formalizing table: {table_name}")
            logger.debug(f"Dependencies: {dependencies}")
            logger.model_input(f"User prompt:\n{user_prompt}")

        history = history or []
        
        for attempt in range(self.max_retries):
            if attempt > 0:
                user_prompt = f"Compilation failed. Error:\n{compilation_error}\n\nPlease fix the Lean code.\n\nPlease make sure you have '### Lean Code\n```lean' in your response so that I can find the Lean code easily."

            # Call LLM
            response = await _call_openai_completion_async(
                model=self.model,
                system_prompt=self.SYSTEM_PROMPT,
                user_prompt=user_prompt,
                history=history,
                temperature=0.0
            )

            if logger:
                logger.model_output(f"LLM response:\n{response}")

            if not response:
                if logger:
                    logger.error("Failed to get LLM response")
                continue

            # Extract Lean code
            try:
                # find the final ```lean and ```
                lean_code = response.split("### Lean Code\n```lean")[-1].split("```")[0].strip()
            except Exception as e:
                if logger:
                    logger.error(f"Failed to extract Lean code: {e}")
                continue

            # Update project structure
            project.set_lean("table", service.name, table_name, lean_code)

            # Try to build
            success, compilation_error = project.build(parse=True, add_context=True, only_errors=True)
            if success:
                if logger:
                    logger.debug(f"Successfully formalized table: {table_name}")
                return True

            # Remove failed code
            project.del_lean("table", service.name, table_name)

            # Update history
            history.extend([
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": response}
            ])

            if logger:
                logger.warning(f"Attempt {attempt + 1} failed: {compilation_error}")

        if logger:
            logger.error(f"Failed to formalize table {table_name} after {self.max_retries} attempts")
        return False

    async def run(self,
                 dependency_info: TableDependencyInfo,
                 logger: Logger = None) -> TableFormalizationInfo:
        """Formalize all tables in topological order"""
        if not dependency_info.topological_order:
            raise ValueError("No valid topological order available")

        result = TableFormalizationInfo(
            project=dependency_info.project,
            dependencies=dependency_info.dependencies,
            topological_order=dependency_info.topological_order
        )
        
        for table_name in dependency_info.topological_order:
            success = await self.formalize_table(
                project=dependency_info.project,
                table_name=table_name,
                dependencies=dependency_info.dependencies[table_name],
                logger=logger
            )
            
            if success:
                result.add_formalized_table(table_name)
            else:
                break

        return result 
    