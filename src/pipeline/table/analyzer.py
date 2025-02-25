from typing import Dict, List, Set, Optional
import json
import yaml
from collections import defaultdict, deque
from src.utils.parse_project.parser import ProjectStructure
from src.utils.apis.langchain_client import _call_openai_completion_async
from src.pipeline.table.types import TableDependencyInfo
from logging import Logger

class TableDependencyAnalyzer:
    """Analyze dependencies between tables in a project"""
    
    # System prompt template
    SYSTEM_PROMPT = """
You are a software system analyzer focusing on database table dependencies.

Background:
This software project contains multiple services, each with its own APIs and database tables. You will be provided with descriptions of all database tables, including their service context, table names, and column definitions.

Task:
1. Analyze the dependencies between database tables. A dependency exists when:
   - Table A's column is a foreign key to Table B
   - Table A requires Table B to be created first for implementation
   - Any other logical dependency where Table A must exist before Table B

2. Return your analysis as a JSON dictionary where:
   - Keys are table names
   - Values are lists of table names that the key table depends on
   - Format: {"table_name": ["dependent_table1", "dependent_table2", ...]}

Wrap your JSON response with ```json and ``` markers.
"""
    def __init__(self, model: str = "deepseek-r1"):
        self.model = model

    @staticmethod
    def _validate_table_names(project: ProjectStructure) -> None:
        """Check for duplicate table names across services"""
        table_names = set()
        for service in project.services:
            for table in service.tables:
                if table.name in table_names:
                    raise ValueError(f"Duplicate table name found: {table.name}")
                table_names.add(table.name)

    @staticmethod
    def _format_user_prompt(project: ProjectStructure) -> str:
        """Format the user prompt with table descriptions"""
        lines = ["# Table Descriptions\n"]
        
        # Add all table descriptions
        for service in project.services:
            for table in service.tables:
                lines.append(f"## {table.name}")
                lines.append("```yaml")
                lines.append(yaml.dump(table.description, allow_unicode=True))
                lines.append("```\n")
        
        # Add example output format
        lines.append("# Expected Output Format")
        lines.append("```json")
        example = {table.name: ["<list of tables that this table depends on>"] 
                  for service in project.services 
                  for table in service.tables}
        lines.append(json.dumps(example, indent=2))
        lines.append("```")
        
        return "\n".join(lines)

    @staticmethod
    def _validate_dependencies(dependencies: Dict[str, List[str]], table_names: Set[str]) -> None:
        """Validate that all tables are in the dependencies dict and referenced tables exist"""
        # Check all tables are in dependencies
        if set(dependencies.keys()) != table_names:
            raise ValueError("Not all tables are included in the dependency analysis")
        
        # Check all referenced tables exist
        for deps in dependencies.values():
            for dep in deps:
                if dep not in table_names:
                    raise ValueError(f"Referenced table does not exist: {dep}")

    @staticmethod
    def _compute_topological_sort(dependencies: Dict[str, List[str]]) -> Optional[List[str]]:
        """Compute a topological sort of tables based on dependencies"""
        # Build adjacency list and in-degree count
        graph = defaultdict(list)
        in_degree = defaultdict(int)
        
        for table, deps in dependencies.items():
            for dep in deps:
                graph[dep].append(table)
                in_degree[table] += 1
            if table not in in_degree:
                in_degree[table] = 0
        
        # Perform topological sort
        queue = deque([table for table, degree in in_degree.items() if degree == 0])
        result = []
        
        while queue:
            table = queue.popleft()
            result.append(table)
            
            for dependent in graph[table]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        
        # Check if valid (no cycles)
        if len(result) != len(dependencies):
            return None
            
        return result

    async def run(self, project: ProjectStructure, logger: Logger = None) -> TableDependencyInfo:
        """Analyze table dependencies in the project"""
        # Validate no duplicate table names
        self._validate_table_names(project)
        
        # Get all table names
        table_names = {table.name for service in project.services for table in service.tables}
        
        # Prepare prompts
        user_prompt = self._format_user_prompt(project)
        
        if logger:
            logger.debug(f"Analyzing table dependencies for project: {project.name}")
            logger.debug(f"Table names: {table_names}")
            logger.model_input(f"System prompt:\n{self.SYSTEM_PROMPT}")
            logger.model_input(f"User prompt:\n{user_prompt}")

        # Call LLM
        response = await _call_openai_completion_async(
            model=self.model,
            system_prompt=self.SYSTEM_PROMPT,
            user_prompt=user_prompt
        )

        if logger:
            logger.model_output(f"LLM response:\n{response}")
        
        if not response:
            raise RuntimeError("Failed to get response from LLM")
        
        # Extract JSON from response
        try:
            # find the final ```json and ```
            json_str = response.split("```json")[-1].split("```")[0].strip()
            dependencies = json.loads(json_str)
        except Exception as e:
            raise ValueError(f"Failed to parse LLM response as JSON: {e}")
        
        # Validate dependencies
        self._validate_dependencies(dependencies, table_names)
        
        # Compute topological sort
        topological_order = self._compute_topological_sort(dependencies)
        
        return TableDependencyInfo(
            project=project,
            dependencies=dependencies,
            topological_order=topological_order
        ) 