from typing import Dict, List, Optional, Set, Tuple
import json
from src.utils.parse_project.parser import ProjectStructure
from src.utils.apis.langchain_client import _call_openai_completion_async
from src.pipeline.api.types import APIDependencyInfo
from collections import defaultdict, deque
from logging import Logger

class APIAnalyzer:
    """Analyze dependencies between APIs"""
    
    SYSTEM_PROMPT = """
You are a software system analyzer focusing on API dependencies.

Background:
We need to formalize each API implementation into Lean 4. Having completed the database table formalization and API-table dependency analysis, we now need to analyze API-to-API dependencies.

Important Context:
- API calls use the format: <API_name>Message
- API implementations are in: <API_name>MessagePlanner
- We need to identify which APIs from which Services are called within a given API implementation

Task:
Analyze the API implementation to identify other APIs it calls by:
1. Looking for <API_name>Message patterns in the code
2. Matching these to the provided list of available APIs
3. Identifying the Service each called API belongs to

Return your analysis as a JSON array of [Service, API] tuples representing dependencies.
If there are no dependencies, return an empty array.

Example output format:
```json
[["UserAuthService", "Login"], ["ProfileService", "GetProfile"]]
```
"""

    def __init__(self, model: str = "deepseek-r1"):
        self.model = model

    def _format_available_apis_prompt(self, project: ProjectStructure) -> str:
        """Format list of all available APIs by service"""
        lines = ["# Available APIs\n"]
        
        for service in project.services:
            lines.append(f"## {service.name}")
            for api in service.apis:
                lines.append(f"- {api.name}")
            lines.append("")
            
        return "\n".join(lines)

    def _format_api_prompt(self, project: ProjectStructure, service_name: str, api_name: str) -> str:
        """Format current API information"""
        lines = ["# Current API Implementation\n"]
        
        service, api = project._find_api_with_service(api_name)
        if not service or not api:
            raise ValueError(f"API {api_name} not found")
            
        lines.append(project._api_to_markdown(service, api))
        
        return "\n".join(lines)

    def _validate_api_dependencies(self, 
                                 dependencies: List[Tuple[str, str]], 
                                 project: ProjectStructure) -> None:
        """Validate that referenced APIs exist"""
        for service_name, api_name in dependencies:
            service, api = project._find_api_with_service(api_name)
            if not service or service.name != service_name:
                raise ValueError(f"Referenced API not found: {service_name}.{api_name}")

    def _compute_api_topological_sort(self, 
                                    dependencies: Dict[str, List[str]]) -> Optional[List[Tuple[str, str]]]:
        """Compute topological sort of APIs"""
        # Build adjacency list and in-degree count
        graph = defaultdict(list)
        in_degree = defaultdict(int)
        
        for api, deps in dependencies.items():
            for dep in deps:
                graph[dep].append(api)
                in_degree[api] += 1
            if api not in in_degree:
                in_degree[api] = 0
        
        # Perform topological sort
        queue = deque([api for api, degree in in_degree.items() if degree == 0])
        result = []
        
        while queue:
            api = queue.popleft()
            service, api_obj = self.project._find_api_with_service(api)
            result.append((service.name, api))
            
            for dependent in graph[api]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        
        # Check if valid (no cycles)
        if len(result) != len(dependencies):
            return None
            
        return result

    async def analyze_api(self,
                         project: ProjectStructure,
                         service_name: str,
                         api_name: str,
                         logger: Logger = None) -> List[Tuple[str, str]]:
        """Analyze a single API's dependencies on other APIs"""
        # Prepare prompts
        apis_prompt = self._format_available_apis_prompt(project)
        api_prompt = self._format_api_prompt(project, service_name, api_name)
        
        user_prompt = f"{apis_prompt}\n{api_prompt}"

        if logger:
            logger.debug(f"Analyzing API dependencies: {service_name}.{api_name}")
            logger.model_input(f"User prompt:\n{user_prompt}")

        # Call LLM
        response = await _call_openai_completion_async(
            model=self.model,
            system_prompt=self.SYSTEM_PROMPT,
            user_prompt=user_prompt
        )

        if not response:
            raise RuntimeError("Failed to get response from LLM")

        # Extract JSON from response
        try:
            json_str = response.split("```json")[-1].split("```")[0].strip()
            dependencies = json.loads(json_str)
        except Exception as e:
            raise ValueError(f"Failed to parse LLM response as JSON: {e}")

        # Validate dependencies
        self._validate_api_dependencies(dependencies, project)

        return dependencies

    async def run(self, 
                 table_dependency_info: APIDependencyInfo,
                 logger: Logger = None) -> APIDependencyInfo:
        """Analyze all API dependencies"""
        self.project = table_dependency_info.project
        
        # Initialize result
        result = APIDependencyInfo(
            project=table_dependency_info.project,
            dependencies=table_dependency_info.dependencies,
            topological_order=table_dependency_info.topological_order,
            formalized_tables=table_dependency_info.formalized_tables,
            api_table_dependencies=table_dependency_info.api_table_dependencies,
            api_dependencies={},
            api_topological_order=None
        )

        # Analyze each API
        for service in self.project.services:
            for api in service.apis:
                try:
                    dependencies = await self.analyze_api(
                        project=self.project,
                        service_name=service.name,
                        api_name=api.name,
                        logger=logger
                    )
                    
                    # Store dependencies as list of API names
                    result.api_dependencies[api.name] = [
                        f"{dep_service}.{dep_api}" for dep_service, dep_api in dependencies
                    ]
                    
                    if logger:
                        logger.debug(f"API {api.name} depends on: {dependencies}")
                        
                except Exception as e:
                    if logger:
                        logger.error(f"Failed to analyze API {api.name}: {e}")
                    raise

        # Compute topological sort
        result.api_topological_order = self._compute_api_topological_sort(result.api_dependencies)

        return result 