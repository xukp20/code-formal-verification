from pathlib import Path
from typing import Dict, List, Optional
from logging import Logger
import asyncio

from src.types.project import ProjectStructure, APITheorem
from src.generate_theorems.api_doc_splitter import APIDocSplitter
from src.generate_theorems.requirement_generator import RequirementGenerator

class APIRequirementGenerator:
    """Generate API requirements and theorems from documentation"""

    def __init__(self, model: str = "qwen-max-latest"):
        self.model = model
        self.doc_splitter = APIDocSplitter(model)
        self.requirement_generator = RequirementGenerator(model)

    async def _generate_parallel(self,
                               project: ProjectStructure,
                               doc_path: Path,
                               logger: Optional[Logger] = None,
                               max_workers: int = 1) -> ProjectStructure:
        """Generate requirements in parallel for all APIs"""
        if logger:
            logger.info(f"Generating API requirements in parallel for project: {project.name}")
            logger.info(f"Reading documentation from: {doc_path}")

        # Split API documentation (sequential)
        api_docs = await self.doc_splitter.split_docs(project, doc_path, logger)

        # Create tasks for each API
        tasks = []
        for service in project.services:
            service_docs = api_docs.get(service.name, {})
            for api in service.apis:
                tasks.append((service, api, service_docs.get(api.name)))

        # Create semaphore to limit concurrent tasks
        sem = asyncio.Semaphore(max_workers)

        async def process_api(task):
            service, api, api_doc = task
            if not api_doc:
                if logger:
                    logger.error(f"Documentation not found for API {api.name} in service {service.name}")
                raise ValueError(f"Documentation not found for API {api.name} in service {service.name}")

            if logger:
                logger.info(f"Generating requirements for API: {api.name}")

            # Generate requirements
            requirements = await self.requirement_generator.generate_requirements(
                api_name=api.name,
                api_doc=api_doc,
                logger=logger
            )

            # Create theorems
            api.doc = api_doc
            api.theorems = [
                APITheorem(description=req)
                for req in requirements
            ]

            if logger:
                logger.debug(f"Generated {len(requirements)} requirements for API: {api.name}")

        async def process_with_semaphore(task):
            async with sem:
                await process_api(task)

        # Run all tasks in parallel
        await asyncio.gather(*[process_with_semaphore(task) for task in tasks])

        return project

    async def generate(self,
                      project: ProjectStructure,
                      doc_path: Path,
                      logger: Optional[Logger] = None,
                      max_workers: int = 1) -> ProjectStructure:
        """Generate requirements and theorems for all APIs"""
        if max_workers > 1:
            return await self._generate_parallel(project, doc_path, logger, max_workers)

        # Original sequential logic
        if logger:
            logger.info(f"Generating API requirements for project: {project.name}")
            logger.info(f"Reading documentation from: {doc_path}")

        # Split API documentation
        api_docs = await self.doc_splitter.split_docs(project, doc_path, logger)

        # Generate requirements for each API
        for service in project.services:
            if logger:
                logger.info(f"Processing service: {service.name}")
                
            service_docs = api_docs.get(service.name, {})
            for api in service.apis:
                if logger:
                    logger.info(f"Generating requirements for API: {api.name}")
                    
                api_doc = service_docs.get(api.name)
                if not api_doc:
                    raise ValueError(f"Documentation not found for API {api.name} in service {service.name}")
                    
                # Generate requirements
                requirements = await self.requirement_generator.generate_requirements(
                    api_name=api.name,
                    api_doc=api_doc,
                    logger=logger
                )
                
                # Create theorems
                api.doc = api_doc
                api.theorems = [
                    APITheorem(description=req)
                    for req in requirements
                ]
                
                if logger:
                    logger.debug(f"Generated {len(requirements)} requirements for API: {api.name}")

        return project 