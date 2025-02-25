from pathlib import Path
from typing import Dict, List, Optional
import json
import yaml
from logging import Logger

from src.utils.parse_project.parser import ProjectStructure
from src.utils.apis.langchain_client import _call_openai_completion_async
from src.pipeline.theorem.api.types import (
    APIDocInfo, APIRequirementInfo, APIRequirementGenerationInfo
)

class APIRequirementGenerator:
    """Generate requirements for API verification based on documentation"""

    DOC_SPLIT_SYSTEM_PROMPT = """
You are a software documentation analyzer focusing on API functionality verification.

Task:
Analyze the provided API documentation and split it into individual API descriptions, adding necessary details for formal verification.

Background:
We need to formally verify each API's implementation against its documentation. The parsed documentation should clearly specify the input-output relationships for each API.

Output Format:
1. First, write your analysis process
2. Then, output a JSON structure between ```json and ``` markers where:
   - Top level keys are service names
   - Second level keys are API names within that service
   - Values are detailed API documentation
"""

    REQUIREMENT_GEN_SYSTEM_PROMPT = """
You are a software specification analyzer focusing on API verification.

Task:
Given an API's documentation, generate a list of specific requirements that need to be verified.

Background:
We need to verify API functionality by checking:
1. Input validation requirements
2. Database state requirements
3. Response requirements
4. Database update requirements

Each requirement should be a clear, testable statement about what the API must do, explaning under what kinds of inputs and input database states, the API must response what kind of outputs and give out what kind of database updates.

For example:
- If the user is not in the database, even the register should success and return a success message, and the user should be added to the database.
- If the user is already in the database, the register should fail and return a failure message, with the database unchanged.


Output Format:
First a reasoning process, then a JSON list between ```json and ``` markers, where each item is a requirement statement.
"""

    def __init__(self, model: str = "qwen-max-latest"):
        self.model = model

    async def split_api_docs(self, 
                           info: APIRequirementGenerationInfo,
                           doc_path: Path,
                           logger: Optional[Logger] = None) -> Dict[str, Dict[str, str]]:
        """Split project documentation into per-API documentation"""
        if not doc_path.exists():
            raise FileNotFoundError(f"Documentation file not found: {doc_path}")
            
        # Read documentation
        doc_content = doc_path.read_text()
        
        # Prepare prompt
        structure = info.format_project_structure()
        template = info.format_output_template()
        user_prompt = f"""
{structure}

# Documentation Content
{doc_content}

# Expected Output Format
{template}
"""

        if logger:
            logger.model_input(f"Doc split prompt:\n{user_prompt}")

        # Call LLM
        response = await _call_openai_completion_async(
            model=self.model,
            system_prompt=self.DOC_SPLIT_SYSTEM_PROMPT,
            user_prompt=user_prompt
        )

        if logger:
            logger.model_output(f"Doc split response:\n{response}")

        # Parse response
        try:
            json_str = response.split("```json")[-1].split("```")[0].strip()
            return json.loads(json_str)
        except Exception as e:
            raise ValueError(f"Failed to parse API doc split response: {e}")

    async def generate_api_requirements(self,
                                     service_name: str,
                                     api_name: str,
                                     api_doc: str,
                                     logger: Optional[Logger] = None) -> List[str]:
        """Generate requirement descriptions for a single API"""
        user_prompt = f"""
API Name: {api_name}

Documentation:
{api_doc}
"""

        if logger:
            logger.model_input(f"Requirement generation prompt for {api_name}:\n{user_prompt}")

        # Call LLM
        response = await _call_openai_completion_async(
            model=self.model,
            system_prompt=self.REQUIREMENT_GEN_SYSTEM_PROMPT,
            user_prompt=user_prompt
        )

        if logger:
            logger.model_output(f"Requirement generation response for {api_name}:\n{response}")

        # Parse response
        try:
            json_str = response.split("```json")[-1].split("```")[0].strip()
            return json.loads(json_str)
        except Exception as e:
            raise ValueError(f"Failed to parse requirement generation response for {api_name}: {e}")

    async def run(self,
                 project: ProjectStructure,
                 doc_path: Path,
                 output_path: Path,
                 logger: Optional[Logger] = None) -> APIRequirementGenerationInfo:
        """Generate requirements for all APIs in the project"""
        if logger:
            logger.info(f"Generating requirements for project: {project.name}")
            logger.info(f"Reading documentation from: {doc_path}")

        # Initialize result structure
        info = APIRequirementGenerationInfo(
            project=project,
            api_docs={},
            api_requirements={},
            output_path=output_path
        )

        # Split API documentation
        info.api_docs = await self.split_api_docs(info, doc_path, logger)

        # Generate requirements for each API
        for service in project.services:
            if logger:
                logger.info(f"Processing service: {service.name}")
                
            service_requirements = {}
            for api in service.apis:
                if logger:
                    logger.info(f"Generating requirements for API: {api.name}")
                    
                api_doc = info.api_docs.get(service.name, {}).get(api.name)
                if not api_doc:
                    raise ValueError(f"Documentation not found for API {api.name} in service {service.name}")
                    
                requirements = await self.generate_api_requirements(
                    service_name=service.name,
                    api_name=api.name,
                    api_doc=api_doc,
                    logger=logger
                )
                
                service_requirements[api.name] = APIRequirementInfo(
                    service_name=service.name,
                    api_name=api.name,
                    doc=api_doc,
                    requirements=requirements
                )
                
            info.api_requirements[service.name] = service_requirements

        # Save results
        info.save()
        return info 