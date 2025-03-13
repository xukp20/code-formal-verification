from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import json
from collections import defaultdict, deque
from logging import Logger
import asyncio

from src.types.project import ProjectStructure, Service, APIFunction
from src.utils.apis.langchain_client import _call_openai_completion_async

class APIDependencyAnalyzer:
    """Analyze dependencies between APIs across services"""
    
    ROLE_PROMPT = """You are a software system analyzer focusing on API dependencies. You excel at understanding how APIs interact with each other across different services and identifying dependency relationships."""

    SYSTEM_PROMPT = """Background:
This software project contains multiple services, each with its own APIs. APIs can call other APIs across services.

Task:
Analyze the API implementation to identify which other APIs it calls by:
1. Looking for <API_name>Message patterns in the code
2. Matching these to the provided list of available APIs
3. Identifying the Service each called API belongs to

Return your analysis in two parts:
### Analysis
Step-by-step reasoning of your dependency analysis

### Output
```json
[["ServiceName", "APIName"], ["ServiceName", "APIName"], ...]
```

Important:
- Return service-API pairs for each dependency
- Only include direct API calls
- APIs must exist in the provided API list
- Return an empty array if no APIs are called
- Order doesn't matter
- The current API itself is not a dependency and should not be included in the output

Make sure you have "### Output\n```json" in your response so that I can find the Json easily."""

    def __init__(self, model: str = "qwen-max-latest"):
        self.model = model

    @staticmethod
    def _format_dependencies(project: ProjectStructure) -> str:
        """Format all available APIs as markdown"""
        lines = ["# Available APIs"]
        for service in project.services:
            lines.append(f"\n# Service: {service.name}")
            for api in service.apis:
                lines.append(api.to_markdown(show_fields={"description": False}))
        return "\n".join(lines)

    @staticmethod
    def _format_input(api: APIFunction) -> str:
        """Format API implementation details"""
        return api.to_markdown(show_fields={"planner_code": True, "message_code": True})

    @staticmethod
    def _format_user_prompt(project: ProjectStructure, service: Service, api: APIFunction) -> str:
        """Format the complete user prompt"""
        parts = [
            APIDependencyAnalyzer._format_dependencies(project),
            "\n# Current API",
            APIDependencyAnalyzer._format_input(api)
        ]
        return "\n".join(parts)

    @staticmethod
    def _validate_dependencies(dependencies: List[Tuple[str, str]], project: ProjectStructure) -> None:
        """Validate that all referenced APIs exist"""
        for service_name, api_name in dependencies:
            service = next((s for s in project.services if s.name == service_name), None)
            if not service:
                raise ValueError(f"Referenced service does not exist: {service_name}")
            
            api = next((a for a in service.apis if a.name == api_name), None)
            if not api:
                raise ValueError(f"Referenced API does not exist: {service_name}.{api_name}")

    @staticmethod
    def _compute_topological_sort(dependencies: Dict[str, List[Tuple[str, str]]]) -> Optional[List[Tuple[str, str]]]:
        """Compute topological sort of APIs"""
        # Build adjacency list and in-degree count
        graph = defaultdict(list)
        in_degree = defaultdict(int)
        
        # Track all APIs
        all_apis = set()
        
        for api, deps in dependencies.items():
            all_apis.add(api)
            for service_name, dep_api in deps:
                dep_key = f"{service_name}.{dep_api}"
                all_apis.add(dep_key)
                graph[dep_key].append(api)
                in_degree[api] += 1
                
        # Initialize APIs with no dependencies
        queue = deque([api for api in all_apis if in_degree[api] == 0])
        result = []
        
        # Process queue
        while queue:
            api = queue.popleft()
            service_name, api_name = api.split(".")
            result.append((service_name, api_name))
            
            for dependent in graph[api]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
                    
        # Check for cycles
        if len(result) != len(all_apis):
            return None
            
        return result

    async def analyze_api(self, project: ProjectStructure, service: Service, 
                         api: APIFunction, logger: Logger = None) -> List[Tuple[str, str]]:
        """Analyze dependencies for a single API"""
        if logger:
            logger.debug(f"Analyzing API: {service.name}.{api.name}")
            
        # Prepare prompts
        user_prompt = self._format_user_prompt(project, service, api)
        
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
        self._validate_dependencies(dependencies, project)
        
        return dependencies

    async def _analyze_parallel(self, project: ProjectStructure, logger: Logger = None, max_workers: int = 1) -> ProjectStructure:
        """Analyze API dependencies in parallel"""
        if logger:
            logger.info(f"Analyzing API dependencies in parallel for project: {project.name} with {max_workers} workers")
            
        # Collect all dependencies
        all_dependencies = {}
        
        # Create tasks for each API
        tasks = []
        for service in project.services:
            if logger:
                logger.info(f"Processing service: {service.name}")
                
            for api in service.apis:
                tasks.append((project, service, api))

        # Process APIs in parallel
        async def process_api(task):
            project, service, api = task
            try:
                dependencies = await self.analyze_api(project, service, api, logger)
                api_key = f"{service.name}.{api.name}"
                all_dependencies[api_key] = dependencies
                api.dependencies.apis = dependencies
                
                if logger:
                    logger.debug(f"API {api.name} depends on: {dependencies}")
                    
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
        
        # Compute topological order
        project.api_topological_order = self._compute_topological_sort(all_dependencies)
        
        if not project.api_topological_order and all_dependencies:
            if logger:
                logger.warning("Could not compute valid topological sort, possible circular dependencies")
                    
        return project

    async def analyze(self, project: ProjectStructure, logger: Logger = None, max_workers: int = 1) -> ProjectStructure:
        """Analyze API dependencies and compute topological order"""
        if max_workers > 1:
            return await self._analyze_parallel(project, logger, max_workers)
            
        # Original sequential logic
        if logger:
            logger.info(f"Analyzing API dependencies for project: {project.name}")
            
        # Collect all dependencies
        all_dependencies = {}
        
        # Process each service
        for service in project.services:
            if logger:
                logger.info(f"Processing service: {service.name}")
                
            # Process each API
            for api in service.apis:
                try:
                    dependencies = await self.analyze_api(project, service, api, logger)
                    api_key = f"{service.name}.{api.name}"
                    all_dependencies[api_key] = dependencies
                    api.dependencies.apis = dependencies
                    
                    if logger:
                        logger.debug(f"API {api.name} depends on: {dependencies}")
                        
                except Exception as e:
                    if logger:
                        logger.error(f"Failed to analyze API {api.name}: {e}")
                    raise
                    
        # Compute topological order
        project.api_topological_order = self._compute_topological_sort(all_dependencies)
        
        if not project.api_topological_order and all_dependencies:
            if logger:
                logger.warning("Could not compute valid topological sort, possible circular dependencies")
                    
        return project 