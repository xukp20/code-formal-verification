from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import json
from logging import Logger
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.types.project import ProjectStructure, Service, Table, APIFunction
from src.utils.apis.langchain_client import _call_openai_completion_async
from src.formalize.constants import DB_API_DECLARATIONS

class APITableDependencyAnalyzer:
    """Analyze API dependencies on database tables"""
    
    ROLE_PROMPT = """You are a software system analyzer focusing on API database dependencies. You excel at understanding how APIs interact with databases through SQL queries and identifying table dependencies."""

    SYSTEM_PROMPT = """Background:
The APIs in this system interact with the database through a standard Database API service. You will analyze API implementations to identify table dependencies.

Task:
Analyze the API implementation to identify which tables it reads from or writes to by:
1. Examining the SQL statements in Database API calls
2. Identifying table names referenced in these SQL statements
3. Matching these names to the provided table list

Return your analysis in two parts:
### Analysis
Step-by-step reasoning of your dependency analysis

### Output
```json
["table1", "table2", ...]
```

Important:
- Only include tables that are directly accessed through SQL queries
- Tables must exist in the provided table list
- Return an empty array if no tables are accessed
- Order doesn't matter
"""

    def __init__(self, model: str = "qwen-max-latest"):
        self.model = model

    @staticmethod
    def _format_dependencies(tables: List[Table]) -> str:
        """Format available tables as markdown"""
        lines = ["# Available Tables"]
        for table in tables:
            lines.extend([
                table.to_markdown(show_fields={"description": True})
            ])
        return "\n".join(lines)

    @staticmethod
    def _format_input(api: APIFunction) -> str:
        """Format API implementation details"""
        lines = [
            api.to_markdown(show_fields={"planner_code": True, "message_code": True})
        ]
        return "\n".join(lines)

    @staticmethod
    def _format_user_prompt(service: Service, api: APIFunction) -> str:
        """Format the complete user prompt"""
        parts = [
            "# API Table Dependency Analysis",
            f"Service: {service.name}",
            "\n# Database API Interface",
            "```scala",
            DB_API_DECLARATIONS,
            "```",
            "\n# Dependencies",
            APITableDependencyAnalyzer._format_dependencies(service.tables),
            "\n# Input",
            APITableDependencyAnalyzer._format_input(api)
        ]
        return "\n".join(parts)

    @staticmethod
    def _validate_dependencies(dependencies: List[str], service: Service) -> None:
        """Validate that all referenced tables exist in the service"""
        table_names = {table.name for table in service.tables}
        for dep in dependencies:
            if dep not in table_names:
                raise ValueError(f"Referenced table does not exist in service {service.name}: {dep}")

    async def analyze_api(self, project: ProjectStructure, service: Service, 
                         api: APIFunction, logger: Logger = None) -> List[str]:
        """Analyze table dependencies for a single API"""
        if logger:
            logger.debug(f"Analyzing API: {service.name}.{api.name}")
            
        # Prepare prompts
        user_prompt = self._format_user_prompt(service, api)
        
        if logger:
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
            raise RuntimeError(f"Failed to get response from LLM for API {api.name}")
        
        # Extract JSON from response
        try:
            json_str = response.split("```json")[-1].split("```")[0].strip()
            dependencies = json.loads(json_str)
        except Exception as e:
            raise ValueError(f"Failed to parse LLM response as JSON for API {api.name}: {e}")
        
        # Validate dependencies
        self._validate_dependencies(dependencies, service)
        
        return dependencies

    async def _analyze_parallel(self, project: ProjectStructure, logger: Logger = None, max_workers: int = 1) -> ProjectStructure:
        """Analyze table dependencies for all APIs in parallel"""
        if logger:
            logger.info(f"Analyzing API table dependencies in parallel for project: {project.name} with {max_workers} workers")

        # Create tasks for each API
        tasks = []
        for service in project.services:
            if logger:
                logger.info(f"Processing service: {service.name}")
                
            for api in service.apis:
                tasks.append((project, service, api))

        # Process APIs in parallel using ThreadPoolExecutor
        async def process_api(task):
            project, service, api = task
            try:
                dependencies = await self.analyze_api(project, service, api, logger)
                api.dependencies.tables = dependencies
                
                if logger:
                    logger.debug(f"API {api.name} depends on tables: {dependencies}")
                    
            except Exception as e:
                if logger:
                    logger.error(f"Failed to analyze API {api.name}: {e}")
                raise

        # Create semaphore to limit concurrent tasks
        sem = asyncio.Semaphore(max_workers)

        async def process_with_semaphore(task):
            async with sem:
                await process_api(task)

        # Run all tasks
        await asyncio.gather(*[process_with_semaphore(task) for task in tasks])
                    
        return project

    async def analyze(self, project: ProjectStructure, logger: Logger = None, max_workers: int = 1) -> ProjectStructure:
        """Analyze table dependencies for all APIs in the project"""
        if max_workers > 1:
            return await self._analyze_parallel(project, logger, max_workers)
            
        # Original sequential logic
        if logger:
            logger.info(f"Analyzing API table dependencies for project: {project.name}")
            
        # Process each service
        for service in project.services:
            if logger:
                logger.info(f"Processing service: {service.name}")
                
            # Process each API
            for api in service.apis:
                try:
                    dependencies = await self.analyze_api(project, service, api, logger)
                    api.dependencies.tables = dependencies
                    
                    if logger:
                        logger.debug(f"API {api.name} depends on tables: {dependencies}")
                        
                except Exception as e:
                    if logger:
                        logger.error(f"Failed to analyze API {api.name}: {e}")
                    raise
                    
        return project 