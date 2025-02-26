from pathlib import Path
from typing import Dict, List, Set, Optional
import json
import yaml
from logging import Logger

from src.utils.parse_project.parser import ProjectStructure
from src.utils.apis.langchain_client import _call_openai_completion_async
from src.pipeline.theorem.api.types import APIRequirementGenerationInfo
from src.pipeline.theorem.table.types import TableProperty, TablePropertiesInfo
from src.utils.parse_project.types import TableInfo

class TablePropertiesAnalyzer:
    """Analyze table properties based on API requirements"""
    
    SYSTEM_PROMPT = """
You are a database property analyzer focusing on identifying invariants maintained by APIs.

Task:
Analyze the provided API requirements and determine what properties/invariants each database table maintains under different sets of APIs.

Background:
We have already analyzed each API's functionality and its interactions with database tables. Now we need to identify what properties each table maintains when certain APIs are applied to it.

Output Format:
1. First, write your analysis process
2. Then, output a JSON list between ```json and ``` markers, where each item describes:
   - property: A clear description of the table property/invariant
   - apis: A dictionary mapping service names to lists of API names that maintain this property

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


Examples of properties:
1. "If the current table has no duplicate records, then after applying any of these APIs, the table will still have no duplicate records"

Be specific about the conditions under which each property holds, and be precise about which APIs maintain each property.
"""

    def __init__(self, model: str = "qwen-max-latest"):
        self.model = model
    
    def _find_api_service(self, api_name: str, project: ProjectStructure) -> Optional[str]:
        """Find which service an API belongs to"""
        for service in project.services:
            if any(api.name == api_name for api in service.apis):
                return service.name
        return None

    async def analyze_table_properties(self,
                                     service_name: str,
                                     table_name: str,
                                     table_info: TableInfo,
                                     api_requirements: Dict[str, Dict[str, List[str]]],
                                     dependent_apis: List[str],
                                     project: ProjectStructure,
                                     logger: Optional[Logger] = None) -> List[TableProperty]:
        """Analyze properties for a single table"""
        # Format table info
        table_yaml = yaml.dump(table_info.description, allow_unicode=True)
        
        # Format API requirements that depend on this table
        api_sections = []
        for api_name in dependent_apis:
            api_service = self._find_api_service(api_name, project)
            if api_service and api_name in api_requirements.get(api_service, {}):
                requirements = api_requirements[api_service][api_name]
                api_sections.append(f"## {api_service} -> {api_name}\n" + "\n".join([f"- {req}" for req in requirements]))
        
        api_requirements_text = "\n\n".join(api_sections)
        
        user_prompt = f"""
# Table Information
Table Name: {table_name}
Service: {service_name}

## Schema
```yaml
{table_yaml}
```

# API Requirements (for APIs that use this table)
{api_requirements_text}
"""

        if logger:
            logger.model_input(f"Table properties analysis prompt for {service_name}.{table_name}:\n{user_prompt}")

        # Call LLM
        response = await _call_openai_completion_async(
            model=self.model,
            system_prompt=self.SYSTEM_PROMPT,
            user_prompt=user_prompt
        )

        if logger:
            logger.model_output(f"Table properties analysis response for {service_name}.{table_name}:\n{response}")

        # Parse response
        try:
            json_str = response.split("```json")[-1].split("```")[0].strip()
            properties_data = json.loads(json_str)
            
            # Validate that all APIs in the response exist in the dependencies
            properties = []
            for prop_data in properties_data:
                valid_apis = {}
                for prop_service, prop_apis in prop_data["apis"].items():
                    valid_service_apis = []
                    for api in prop_apis:
                        if api in dependent_apis:
                            valid_service_apis.append(api)
                    if valid_service_apis:
                        valid_apis[prop_service] = valid_service_apis
                
                if valid_apis:  # Only add if there are valid APIs
                    properties.append(TableProperty(
                        property=prop_data["property"],
                        apis=valid_apis
                    ))
            
            return properties
            
        except Exception as e:
            raise ValueError(f"Failed to parse table properties analysis response for {service_name}.{table_name}: {e}")

    async def run(self,
                 requirements_info: APIRequirementGenerationInfo,
                 logger: Optional[Logger] = None) -> TablePropertiesInfo:
        """Analyze properties for all tables in the project"""
        if logger:
            logger.info(f"Analyzing table properties for project: {requirements_info.project.name}")

        # Initialize result structure
        result = TablePropertiesInfo.from_requirements(requirements_info)
        
        # Build a map of which tables are used by which APIs
        table_to_apis: Dict[str, List[str]] = {}  # table_name -> list of api_names
        
        # For each API and its dependent tables
        for api_name, table_names in requirements_info.api_table_dependencies.items():
            for table_name in table_names:
                if table_name not in table_to_apis:
                    table_to_apis[table_name] = []
                table_to_apis[table_name].append(api_name)
        
        # Extract API requirements
        api_requirements: Dict[str, Dict[str, List[str]]] = {}  # service -> api -> requirements
        for service, apis in requirements_info.api_requirements.items():
            api_requirements[service] = {}
            for api_name, api_info in apis.items():
                api_requirements[service][api_name] = api_info.requirements
        
        # Analyze each table
        for service in requirements_info.project.services:
            if logger:
                logger.info(f"Processing service: {service.name}")
            
            service_properties = {}
            for table in service.tables:
                if logger:
                    logger.info(f"Analyzing properties for table: {table.name}")
                
                # Skip tables that no API depends on
                if table.name not in table_to_apis:
                    if logger:
                        logger.info(f"Skipping table {table.name} as no API depends on it")
                    continue
                
                # Get APIs that depend on this table
                dependent_apis = table_to_apis[table.name]
                           
                # Analyze table properties
                properties = await self.analyze_table_properties(
                    service_name=service.name,
                    table_name=table.name,
                    table_info=table,
                    api_requirements=api_requirements,
                    dependent_apis=dependent_apis,
                    project=requirements_info.project,
                    logger=logger
                )
                
                if properties:
                    if service.name not in result.table_properties:
                        result.table_properties[service.name] = {}
                    service_properties[table.name] = properties
            
            if service_properties:
                result.table_properties[service.name] = service_properties

        # Save results
        result.save()
        return result 