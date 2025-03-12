from pathlib import Path
from typing import Dict, List, Optional
import json
import argparse
import asyncio
from logging import Logger, getLogger

from src.types.project import ProjectStructure, Service, APIFunction
from src.utils.apis.langchain_client import _call_openai_completion_async

class APIDocGenerator:
    """Generate API documentation from project structure"""
    
    SYSTEM_PROMPT = """You are a technical documentation writer. Your task is to analyze API implementations and generate clear, comprehensive documentation.

For each API, you should focus on:
1. Overall functionality summary
2. Input/output types and their meanings
3. The APIs it depends on, which means those it calls
4. Detailed behavior for different input scenarios, including:
   - Success cases
   - Error cases
   - Edge cases
   - Input validation
   - Response patterns
5. You need to explain the response using the returned result and type from the dependent APIs
   - Like "If login succeeds, look for the user info in the user info table, and return success with the user info"


Format your response as a clear description that covers:
1. What the API does (high-level summary)
2. What inputs it accepts and what outputs it returns
3. How it behaves in different scenarios

Example format 1:

Accepts user credentials (username and password). Validates the input and:
- If credentials match: Returns success with user session
- If user not found: Returns failure with "invalid credentials" message
- If password incorrect: Returns failure with "invalid credentials" message
- If multiple matching users: Returns error indicating database integrity issue

Example format 2:

This API accepts three parameters: a username, a password, and an amount of money. It relies on the BalanceQuery API:
- Verify that the amount must be a positive integer; if not, return an "Invalid Parameter" error.
- Call the Balance Query function:
    - If it returns an authentication failure, return an authentication failure
    - If it returns a database error, return a database error
    - If the current balance is retrieved successfully, calculate the new balance after the withdrawal:
        - If the new balance is negative, return an insufficient balance error
        - If the new balance is non-negative, write a withdrawal record to the transaction table with the `amount` as the negative value of the withdrawal amount, and return the new balance, indicating success.

Requirement:
- The doc should be a short pure text, no markdown format
- at most 100-200 words
"""

    def __init__(self, model: str = "qwen-max-latest"):
        self.model = model
        self.logger = getLogger(__name__)

    async def generate_api_doc(self, api: APIFunction) -> str:
        """Generate documentation for a single API"""
        prompt = f"""Please analyze this API implementation and generate documentation:

Planner Code:
```scala
{api.planner_code}
```

Message Code:
```scala
{api.message_code}
```

Return a clear description focusing on functionality, inputs/outputs, and behavior in different scenarios.
Don't add any other text."""

        response = await _call_openai_completion_async(
            model=self.model,
            system_prompt=self.SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=0.1
        )
        
        return response.strip() if response else ""

    async def generate_project_doc(self, project: ProjectStructure) -> str:
        """Generate complete project documentation"""
        # Project header
        doc = f"# {project.name}\n\n"
        
        for service in project.services:
            # Service section
            doc += f"## {service.name}\n\n"
            
            for api in service.apis:
                # API section
                doc += f"### {api.name}\n"
                api_doc = await self.generate_api_doc(api)
                self.logger.info(f"Generated API documentation for {api.name}:\n{api_doc}\n\n")
                doc += f"{api_doc}\n\n"
        
        return doc

async def main():
    """Command line interface"""
    parser = argparse.ArgumentParser(description="Generate API documentation")
    
    # Required arguments
    parser.add_argument("--project-name", required=True,
                      help="Name of the project")
                      
    # Optional arguments
    parser.add_argument("--output-base-path", default="outputs",
                      help="Base path for output files")
    parser.add_argument("--project-file",
                      help="Path to project structure file (default: outputs/<project>/formalization/init.json)")
    parser.add_argument("--output-file",
                      help="Path to output documentation file (default: outputs/<project>/doc/api_doc.md)")
    parser.add_argument("--model", default="qwen-max-latest",
                      help="Model to use for documentation generation")

    args = parser.parse_args()
    
    # Set default paths if not provided
    if not args.project_file:
        args.project_file = f"{args.output_base_path}/{args.project_name}/formalization/init.json"
    if not args.output_file:
        doc_dir = Path(f"{args.output_base_path}/{args.project_name}/doc")
        doc_dir.mkdir(parents=True, exist_ok=True)
        args.output_file = str(doc_dir / "api_doc.md")

    # Load project structure
    try:
        with open(args.project_file) as f:
            project = ProjectStructure.from_dict(json.load(f))
    except Exception as e:
        print(f"Failed to load project structure: {e}")
        return False

    # Generate documentation
    generator = APIDocGenerator(model=args.model)
    doc = await generator.generate_project_doc(project)

    # Save documentation
    try:
        with open(args.output_file, "w") as f:
            f.write(doc)
        print(f"Documentation saved to: {args.output_file}")
        return True
    except Exception as e:
        print(f"Failed to save documentation: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1) 