from typing import Dict, List, Optional, Set
import json
import yaml
from src.utils.parse_project.parser import ProjectStructure, ServiceInfo
from src.utils.apis.langchain_client import _call_openai_completion_async
from src.pipeline.formalize.api.types import APIDependencyInfo
from src.pipeline.formalize.api.constants import DB_API_DECLARATIONS
from logging import Logger
from src.pipeline.formalize.table.types import TableFormalizationInfo

class APITableDependencyAnalyzer:
    """Analyze API dependencies on tables"""
    
    SYSTEM_PROMPT = """
You are a software system analyzer focusing on API database dependencies.

Background:
The APIs in this system interact with the database through a standard Database API service. 
You will be provided with:
1. The Database API declarations showing available methods
2. A list of database tables in the service
3. The API implementation to analyze

Task:
Analyze the API implementation to identify which tables it reads from or writes to by:
1. Examining the SQL statements in Database API calls
2. Identifying table names referenced in these SQL statements
3. Matching these names to the provided table list

Return your analysis as a JSON array of table names that this API depends on.
If there are no dependencies, return an empty array.

Wrap your JSON response with ```json and ``` markers.
"""

    def __init__(self, model: str = "deepseek-r1"):
        self.model = model

    def _format_tables_prompt(self, project: ProjectStructure, service_name: str) -> str:
        """Format tables from a specific service as markdown"""
        lines = [f"# Available Tables in Service: {service_name}\n"]
        
        # Find the service
        service = next((s for s in project.services if s.name == service_name), None)
        if not service:
            raise ValueError(f"Service {service_name} not found")
        
        # Add tables from this service only
        for table in service.tables:
            lines.append(project._table_to_markdown(service, table))
                
        return "\n".join(lines)

    def _format_api_prompt(self, project: ProjectStructure, service_name: str, api_name: str) -> str:
        """Format API information as markdown"""
        lines = ["# API Implementation\n"]
        
        # Find the API
        service, api = project._find_api_with_service(api_name, service_name)
        if not service or not api:
            raise ValueError(f"API {api_name} not found in service {service_name}")
            
        lines.append(project._api_to_markdown(service, api))
        
        return "\n".join(lines)

    @staticmethod
    def _validate_table_dependencies(dependencies: List[str], service_name: str, project: ProjectStructure) -> None:
        """Validate that referenced tables exist in the service"""
        # Get table names from this service only
        service = next((s for s in project.services if s.name == service_name), None)
        if not service:
            raise ValueError(f"Service {service_name} not found")
            
        table_names = {table.name for table in service.tables}
        
        for dep in dependencies:
            if dep not in table_names:
                raise ValueError(f"Referenced table {dep} does not exist in service {service_name}")

    async def analyze_api(self,
                         project: ProjectStructure,
                         service_name: str,
                         api_name: str,
                         logger: Logger = None) -> List[str]:
        """Analyze a single API's table dependencies"""
        # Prepare prompts
        tables_prompt = self._format_tables_prompt(project, service_name)
        api_prompt = self._format_api_prompt(project, service_name, api_name)
        
        user_prompt = f"""
# Database API Declarations
```scala
{DB_API_DECLARATIONS}
```

{tables_prompt}

{api_prompt}
"""

        if logger:
            logger.debug(f"Analyzing API: {api_name} in service: {service_name}")
            logger.model_input(f"User prompt:\n{user_prompt}")

        # Call LLM
        response = await _call_openai_completion_async(
            model=self.model,
            system_prompt=self.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.0
        )

        if logger:
            logger.model_output(f"LLM response:\n{response}")

        if not response:
            raise RuntimeError(f"Failed to get response from LLM for API {api_name}")

        # Extract JSON from response
        try:
            json_str = response.split("```json")[-1].split("```")[0].strip()
            dependencies = json.loads(json_str)
        except Exception as e:
            raise ValueError(f"Failed to parse LLM response as JSON for API {api_name}: {e}")

        # Validate dependencies
        self._validate_table_dependencies(dependencies, service_name, project)

        return dependencies

    async def run(self, formalization_info: TableFormalizationInfo, logger: Logger = None) -> APIDependencyInfo:
        """Analyze all APIs' table dependencies"""
        # Initialize result structure
        result = APIDependencyInfo(
            project=formalization_info.project,
            dependencies=formalization_info.dependencies,
            topological_order=formalization_info.topological_order,
            formalized_tables=formalization_info.formalized_tables,
            api_table_dependencies={},
            api_dependencies={},
            api_topological_order=None
        )

        # Analyze each API
        for service in result.project.services:
            for api in service.apis:
                try:
                    dependencies = await self.analyze_api(
                        project=result.project,
                        service_name=service.name,
                        api_name=api.name,
                        logger=logger
                    )
                    result.api_table_dependencies[api.name] = dependencies
                    
                    if logger:
                        logger.debug(f"API {api.name} depends on tables: {dependencies}")
                        
                except Exception as e:
                    if logger:
                        logger.error(f"Failed to analyze API {api.name}: {e}")
                    raise

        return result 