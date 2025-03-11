from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
import json
from collections import defaultdict, deque
from logging import Logger

from src.types.project import ProjectStructure, Service, Table
from src.utils.apis.langchain_client import _call_openai_completion_async

class TableDependencyAnalyzer:
    """Analyze dependencies between tables in a project"""
    
    ROLE_PROMPT = """You are a software system analyzer focusing on database table dependencies. You excel at understanding relationships between database tables and can identify both explicit foreign key dependencies and implicit logical dependencies."""

    SYSTEM_PROMPT = """Background:
This software project contains multiple services, each with its own APIs and database tables. You will be provided with descriptions of all database tables within a single service.

Task:
1. Analyze the dependencies between database tables within this service. A dependency exists when:
   - Table A's column is a foreign key to Table B
   - Table A requires Table B to be created first for implementation
   - Any other logical dependency where Table A must exist before Table B

2. Return your analysis as a JSON dictionary where:
   - Keys are table names
   - Values are lists of table names that the key table depends on
   - Format: {"table_name": ["dependent_table1", "dependent_table2", ...]}

### Output
```json
{{
  "table_name": ["dependent_table1", "dependent_table2", ...]
}}
```

Important:
- Only include dependencies between tables within the same service
- List all tables in the output, even if they have no dependencies
- For tables with no dependencies, use an empty list []

Make sure you have "### Output\n```json" in your response so that I can find the Json easily."""

    def __init__(self, model: str = "qwen-max-latest"):
        self.model = model

    @staticmethod
    def _format_dependencies(tables: List[Table]) -> str:
        """Format all table descriptions as markdown"""
        lines = []
        for table in tables:
            lines.append(table.to_markdown(show_fields={"description": True}))
        return "\n\n".join(lines)

    @staticmethod
    def _format_input() -> str:
        """Format any additional input information"""
        return ""  # No additional input needed for table dependency analysis

    @staticmethod
    def _format_user_prompt(service: Service) -> str:
        """Format the complete user prompt"""
        parts = [
            "Table Dependency Analysis",
            f"# Service: {service.name}",
            TableDependencyAnalyzer._format_dependencies(service.tables),
            TableDependencyAnalyzer._format_input(),
            "\n# Instructions",
            "1. Analyze the table descriptions above",
            "2. Identify all dependencies between tables",
            "3. Return a JSON object mapping each table to its dependencies",
            "\n# Expected Output Format",
            "```json",
            json.dumps({table.name: ["<list of tables that this table depends on>"] 
                       for table in service.tables}, indent=2),
            "```"
        ]
        return "\n".join(parts)

    @staticmethod
    def _validate_table_names(service: Service) -> None:
        """Check for duplicate table names within a service"""
        table_names = set()
        for table in service.tables:
            if table.name in table_names:
                raise ValueError(f"Duplicate table name found in service {service.name}: {table.name}")
            table_names.add(table.name)

    @staticmethod
    def _validate_dependencies(dependencies: Dict[str, List[str]], table_names: Set[str]) -> None:
        """Validate that all tables are in the dependencies dict and referenced tables exist"""
        # Check all tables are in dependencies
        if set(dependencies.keys()) != table_names:
            missing = table_names - set(dependencies.keys())
            raise ValueError(f"Not all tables are included in the dependency analysis. Missing: {missing}")
        
        # Check all referenced tables exist
        for table, deps in dependencies.items():
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

    async def analyze_service(self, service: Service, logger: Logger = None) -> Dict[str, List[str]]:
        """Analyze table dependencies for a single service"""
        # Skip if no tables
        if not service.tables:
            if logger:
                logger.info(f"No tables in service {service.name}, skipping analysis")
            return {}
            
        # Validate no duplicate table names
        self._validate_table_names(service)
        
        # Get all table names
        table_names = {table.name for table in service.tables}
        
        # Prepare prompts
        user_prompt = self._format_user_prompt(service)
        
        if logger:
            logger.debug(f"Analyzing table dependencies for service: {service.name}")
            logger.debug(f"Table names: {table_names}")
            logger.model_input(f"Role prompt:\n{self.ROLE_PROMPT}")
            logger.model_input(f"System prompt:\n{self.SYSTEM_PROMPT}")
            logger.model_input(f"User prompt:\n{user_prompt}")

        # Call LLM
        response = await _call_openai_completion_async(
            model=self.model,
            system_prompt=self.ROLE_PROMPT,
            user_prompt=f"{self.SYSTEM_PROMPT}\n\n{user_prompt}",
            temperature=0.0
        )

        if logger:
            logger.model_output(f"LLM response:\n{response}")
        
        if not response:
            raise RuntimeError(f"Failed to get response from LLM for service {service.name}")
        
        # Extract JSON from response
        try:
            json_str = response.split("```json")[-1].split("```")[0].strip()
            dependencies = json.loads(json_str)
        except Exception as e:
            raise ValueError(f"Failed to parse LLM response as JSON for service {service.name}: {e}")
        
        # Validate dependencies
        self._validate_dependencies(dependencies, table_names)
        
        return dependencies

    async def analyze(self, project: ProjectStructure, logger: Logger = None) -> ProjectStructure:
        """Analyze table dependencies in the project and update the project structure"""
        if logger:
            logger.info(f"Analyzing table dependencies for project: {project.name}")
        
        # Analyze each service
        for service in project.services:
            if logger:
                logger.info(f"Analyzing service: {service.name}")
            
            # Get dependencies
            dependencies = await self.analyze_service(service, logger)
            
            # Update table dependencies
            for table in service.tables:
                if table.name in dependencies:
                    table.dependencies.tables = dependencies[table.name]
            
            # Compute and store topological order
            service.table_topological_order = self._compute_topological_sort(dependencies)
            
            if not service.table_topological_order and dependencies:
                if logger:
                    logger.warning(f"Could not compute valid topological sort for service {service.name}, possible circular dependencies") 

        return project
