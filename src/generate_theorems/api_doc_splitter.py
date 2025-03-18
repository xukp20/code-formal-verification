from pathlib import Path
from typing import Dict, List, Optional
import json
from logging import Logger

from src.types.project import ProjectStructure, Service
from src.utils.apis.langchain_client import _call_openai_completion_async

class APIDocSplitter:
    """Split project API documentation into per-API documentation"""
    
    ROLE_PROMPT = """You are a software documentation analyzer focusing on API functionality verification. You excel at understanding and organizing API documentation to support formal verification."""

    SYSTEM_PROMPT = """Background:
We need to formally verify each API's implementation against its documentation. The parsed documentation should clearly specify the input-output relationships for each API.

Task:
Analyze the provided API documentation and split it into individual API descriptions by:
1. Identifying documentation sections for each API
2. Matching sections to the provided API list
3. Ensuring each API has clear documentation

Return your analysis in two parts:
### Analysis
Step-by-step reasoning of your documentation splitting process
- First, find out all the services and the names of the APIs in each service
- Then, for each service, write a "## ServiceName" title, and then:
    - Look for the documentation of each API in the service section
    - Write the documentation for each API in the format of "### API Name\nAPI documentation text"
- After that, write all the API documentation in the format of "### Output\n```json"
- Make sure no API is duplicated or missing

### Output
```json
{
  "ServiceName": {
    "APIName": "API documentation text",
    ...
  },
  ...
}
```

Important:
- Every API must have documentation
- Documentation should be clear and complete
- Maintain original documentation meaning
- Only include APIs from the provided list
- The Json dict starts from the ServiceName key, so you should not include the project name as the highest level key
- Just ignore the project name if it is in the documentation
- Write all the documentation in English
- If the old doc content is well-structured like each API is in a separate section of markdown, you should keep that structure, and just take out the documentation for each API maintaining the original markdown format

Make sure you have "### Output\n```json" in your response so that I can find the Json easily."""

    def __init__(self, model: str = "qwen-max-latest"):
        self.model = model

    @staticmethod
    def _format_api_list(project: ProjectStructure) -> str:
        """Format available APIs as markdown"""
        lines = ["# Available APIs"]
        for service in project.services:
            lines.append(f"\n## {service.name}")
            for api in service.apis:
                lines.append(f"- {api.name}")
        return "\n".join(lines)

    def _validate_docs(self, docs: Dict[str, Dict[str, str]], project: ProjectStructure) -> None:
        """Validate API documentation coverage and structure"""
        for service in project.services:
            if service.name not in docs:
                raise ValueError(f"Missing documentation for service: {service.name}")
                
            service_docs = docs[service.name]
            for api in service.apis:
                if api.name not in service_docs:
                    raise ValueError(f"Missing documentation for API: {service.name}.{api.name}")
                if not service_docs[api.name].strip():
                    raise ValueError(f"Empty documentation for API: {service.name}.{api.name}")

    async def split_docs(self, 
                        project: ProjectStructure,
                        doc_path: Path,
                        logger: Optional[Logger] = None) -> Dict[str, Dict[str, str]]:
        """Split project documentation into per-API documentation"""
        if not doc_path.exists():
            raise FileNotFoundError(f"Documentation file not found: {doc_path}")
            
        # Read documentation
        doc_content = doc_path.read_text()
        
        # Prepare prompt
        api_list = self._format_api_list(project)
        user_prompt = f"""# API Documentation
{doc_content}

{api_list}"""

        if logger:
            logger.model_input(f"Doc split prompt:\n{user_prompt}")

        # Call LLM
        response = await _call_openai_completion_async(
            model=self.model,
            system_prompt=self.ROLE_PROMPT,
            user_prompt=self.SYSTEM_PROMPT + "\n\n" + user_prompt,
            temperature=0.0
        )

        if logger:
            logger.model_output(f"Doc split response:\n{response}")

        # Parse response
        try:
            json_str = response.split("### Output\n```json")[-1].split("```")[0].strip()
            docs = json.loads(json_str)
        except Exception as e:
            raise ValueError(f"Failed to parse API doc split response: {e}")
            
        # Validate results
        self._validate_docs(docs, project)
        
        return docs 