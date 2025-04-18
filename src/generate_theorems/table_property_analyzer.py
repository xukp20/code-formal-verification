from pathlib import Path
from typing import Dict, List, Optional, Set
import json
from logging import Logger
import asyncio

from src.types.project import ProjectStructure, Service, Table, APIFunction, TableProperty, TableTheorem
from src.utils.apis.langchain_client import _call_openai_completion_async

class TablePropertyAnalyzer:
    """Analyze table properties based on API behaviors"""
    
    ROLE_PROMPT = """You are a database property analyzer focusing on identifying invariants maintained by APIs. You excel at understanding how APIs affect database tables and identifying properties that remain true across operations."""

    SYSTEM_PROMPT = """Background:

We are working on a software project that has a few services, each service has a few APIs.
We have already tested each API by generating specific, testable requirements for its input and output.

Now we need to identify what properties/invariants each database table maintains under different sets of APIs.

Task:
Analyze the provided table and API information to:
1. Identify table properties/invariants
2. Determine which APIs maintain each property
3. Focus on properties that hold before and after API operations

Each property should describe:
1. Current table state conditions
2. What remains true after API operations
3. Relationship between input parameters and table state

Specific Requirements:
1. Each property should describe both the current database state and the resulting state after applying the APIs
- Like "If the current table has no duplicate records, then after applying any of these APIs, the table will still have no duplicate records"
2. Group APIs in meaningful ways:
   - APIs that have similar effects on the table (read-only vs. write operations)
   - APIs from the same service that share common behaviors
3. Consider different types of properties:
   - Uniqueness constraints (certain fields must be unique)
   - Record count changes (whether operations add, remove, or preserve record counts)
   - Existence guarantees (whether specific records must exist or not exist)
4. Please don't focus on the response of the API, only on the effect on the table, describing the status of the input table, and the relationship between the input params and the table (exists or not), then describe the status of the table after the API is applied
5. You maybe get a group properties based on the group of APIs, like some of them will increase the record count by 1, some of them will decrease the record count by 1, some of them will preserve the record count, which will give you three properties
6. You may consider the different behaviors of the APIs given the different input related to the table status, like the record is in the table or not, which will give you more properties
    - If you need to consider the different behaviors of APIs, you must be specific about the input conditions (like the name is valid), or directly describe the return type of the API to show the different behaviors (like the API returns "success" or "failure")
    - If the table change depends on the API's different behaviors, you must be give enough conditions to determine which behavior is applied. You cannot just explain "The API is called" without any information to determine which behavior is applied in this case.

Example property:
"If the current table has no duplicate records in field X, then after applying any of these APIs, the table will still have no duplicate records in field X"
"After calling the delete API of the account successfully, the table will not have any record with that account id"

Return your analysis in two parts:
### Analysis
Step-by-step reasoning of property identification

### Output
```json
[
  {
    "property": "string of property description",
    "apis": ["api1", "api2", ...]
  },
  ...
]
```

Important:
- Focus on table state, not API responses
- Be specific about conditions
- Only include APIs that maintain the property
- Verify all APIs exist in the dependency list

Make sure you have "### Output\n```json" in your response so that I can find the Json easily."""

    def __init__(self, model: str = "qwen-max-latest"):
        self.model = model

    @staticmethod
    def _format_api_info(apis: List[APIFunction]) -> str:
        """Format API information as markdown"""
        lines = ["# Dependent APIs"]
        for api in apis:
            lines.extend([
                api.to_markdown({"doc": True, "requirements": True}),
                "\n\n"
            ])
        return "\n".join(lines)

    def _validate_apis(self, apis: List[str], dependent_apis: List[APIFunction]) -> None:
        """Validate that all APIs in the property exist in dependencies"""
        dependent_api_names = {api.name for api in dependent_apis}
        for api_name in apis:
            if api_name not in dependent_api_names:
                raise ValueError(f"Invalid API in property: {api_name}")

    async def analyze_table(self,
                          table: Table,
                          dependent_apis: List[APIFunction],
                          logger: Optional[Logger] = None) -> List[TableProperty]:
        """Analyze properties for a single table"""
        # Format prompts
        api_info = self._format_api_info(dependent_apis)
        user_prompt = f"""# Table Information
{table.to_markdown(show_fields={"description": True})}

{api_info}"""

        if logger:
            logger.model_input(f"Table property analysis prompt for {table.name}:\n{user_prompt}")

        # Call LLM
        response = await _call_openai_completion_async(
            model=self.model,
            system_prompt=self.ROLE_PROMPT,
            user_prompt=self.SYSTEM_PROMPT + "\n\n" + user_prompt,
            temperature=0.0
        )

        if logger:
            logger.model_output(f"Table property analysis response for {table.name}:\n{response}")
            
        # Parse response
        try:
            json_str = response.split("### Output\n```json")[-1].split("```")[0].strip()
            properties_data = json.loads(json_str)
        except Exception as e:
            raise ValueError(f"Failed to parse table property analysis response for {table.name}: {e}")

        # Validate and create properties
        properties = []
        for prop_data in properties_data:
            # Validate APIs
            self._validate_apis(prop_data["apis"], dependent_apis)
            
            # Create property
            property = TableProperty(
                description=prop_data["property"],
                theorems=[
                    TableTheorem(
                        api_name=api_name
                    )
                    for api_name in prop_data["apis"]
                ]
            )
            properties.append(property)

        return properties

    async def _analyze_parallel(self,
                              project: ProjectStructure,
                              logger: Optional[Logger] = None,
                              max_workers: int = 1) -> ProjectStructure:
        """Analyze table properties in parallel"""
        if logger:
            logger.info(f"Analyzing table properties in parallel for project: {project.name}")

        # Create tasks for each table
        tasks = []
        for service in project.services:
            for table in service.tables:
                # Get APIs that depend on this table
                dependent_apis = [
                    api for api in service.apis
                    if table.name in api.dependencies.tables
                ]
                
                if not dependent_apis:
                    if logger:
                        logger.info(f"No APIs depend on table {table.name}, skipping")
                    continue
                
                tasks.append((table, dependent_apis))

        # Create semaphore to limit concurrent tasks
        sem = asyncio.Semaphore(max_workers)

        async def process_table(task):
            table, dependent_apis = task
            if logger:
                logger.info(f"Analyzing properties for table: {table.name}")
            
            try:
                properties = await self.analyze_table(
                    table=table,
                    dependent_apis=dependent_apis,
                    logger=logger
                )
                table.properties = properties
                return True
            except Exception as e:
                if logger:
                    logger.error(f"Failed to analyze table {table.name}: {e}")
                return False

        async def process_with_semaphore(task):
            async with sem:
                return await process_table(task)

        # Process all tables in parallel
        results = await asyncio.gather(*[process_with_semaphore(task) for task in tasks])

        # Check for failures
        if not all(results):
            if logger:
                logger.error("Some tables failed to analyze")

        return project

    async def analyze(self,
                     project: ProjectStructure,
                     logger: Optional[Logger] = None,
                     max_workers: int = 1) -> ProjectStructure:
        """Analyze properties for all tables in the project"""
        if max_workers > 1:
            return await self._analyze_parallel(project, logger, max_workers)

        # Original sequential logic
        if logger:
            logger.info(f"Analyzing table properties for project: {project.name}")

        # Process each service
        for service in project.services:
            if logger:
                logger.info(f"Processing service: {service.name}")
                
            # Process each table
            for table in service.tables:
                if logger:
                    logger.info(f"Analyzing properties for table: {table.name}")
                
                # Get APIs that depend on this table
                dependent_apis = [
                    api for api in service.apis
                    if table.name in api.dependencies.tables
                ]
                
                if not dependent_apis:
                    if logger:
                        logger.info(f"No APIs depend on table {table.name}, skipping")
                    continue
                
                # Analyze table properties
                properties = await self.analyze_table(
                    table=table,
                    dependent_apis=dependent_apis,
                    logger=logger
                )
                
                # Update table
                table.properties = properties
                
                if logger:
                    logger.debug(f"Generated {len(properties)} properties for table: {table.name}")

        return project 