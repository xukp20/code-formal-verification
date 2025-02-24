from typing import Dict, List, Optional, Set, Tuple
import json
import yaml
from pathlib import Path
from src.utils.parse_project.parser import ProjectStructure
from src.utils.apis.langchain_client import _call_openai_completion_async
from src.pipeline.table.types import TableDependencyInfo, TableFormalizationInfo
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
Formalize the current table into Lean 4 code that:
1. Correctly imports dependent tables using proper import paths
2. Represents table relationships (e.g., foreign keys) by maintaining references to dependent tables
3. Includes methods to validate table constraints
4. Compiles successfully with the Lean compiler

Please provide your response in this format:
### Analysis
Step-by-step reasoning of your formalization approach

### Lean Code
```lean
<complete file content>
```
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
            logger.info(f"Formalizing table: {table_name}")
            logger.info(f"Dependencies: {dependencies}")
            logger.info(f"User prompt:\n{user_prompt}")

        history = history or []
        
        for attempt in range(self.max_retries):
            if attempt > 0:
                user_prompt = f"Compilation failed. Error:\n{compilation_error}\n\nPlease fix the Lean code."

            # Call LLM
            response = await _call_openai_completion_async(
                model=self.model,
                system_prompt=self.SYSTEM_PROMPT,
                user_prompt=user_prompt,
                history=history
            )

            if logger:
                logger.info(f"LLM response:\n{response}")

            if not response:
                if logger:
                    logger.error("Failed to get LLM response")
                continue

            # Extract Lean code
            try:
                lean_code = response.split("```lean")[1].split("```")[0].strip()
            except Exception as e:
                if logger:
                    logger.error(f"Failed to extract Lean code: {e}")
                continue

            # Update project structure
            project.set_lean("table", service.name, table_name, lean_code)

            # Try to build
            success, compilation_error = project.build()
            if success:
                if logger:
                    logger.info(f"Successfully formalized table: {table_name}")
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
    