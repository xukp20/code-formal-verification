from pathlib import Path
from typing import Dict, List, Optional
from logging import Logger

from src.types.project import ProjectStructure, APITheorem
from src.generate_theorems.api_doc_splitter import APIDocSplitter
from src.generate_theorems.requirement_generator import RequirementGenerator

class APIRequirementGenerator:
    """Generate API requirements and theorems from documentation"""

    def __init__(self, model: str = "qwen-max-latest"):
        self.model = model
        self.doc_splitter = APIDocSplitter(model)
        self.requirement_generator = RequirementGenerator(model)

    async def generate(self,
                      project: ProjectStructure,
                      doc_path: Path,
                      logger: Optional[Logger] = None) -> ProjectStructure:
        """Generate requirements and theorems for all APIs"""
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