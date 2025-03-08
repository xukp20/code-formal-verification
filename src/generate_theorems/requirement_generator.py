from typing import Dict, List, Optional
import json
from logging import Logger

from src.utils.apis.langchain_client import _call_openai_completion_async

class RequirementGenerator:
    """Generate formal requirements from API documentation"""
    
    ROLE_PROMPT = """You are a software specification analyzer focusing on API verification. You excel at identifying and formalizing specific, testable requirements from API documentation."""

    SYSTEM_PROMPT = """Background:
We need to verify API functionality by checking:
Given:
1. Input requirements
2. Database state requirements
Then what will be:
1. The response
2. The database update

Task:
Given an API's documentation, generate specific, testable requirements that:
1. Follow from the documentation
2. Cover all functionality
3. Are clear and unambiguous
4. Specify input/output relationships
5. Define database state changes

Each requirement should explain:
- Under what input conditions
- With what database states
- The API must:
  * Return what response
  * Make what database changes

Example requirements:
- "If the user is not in the database, the register operation should succeed, return a success message, and add the user to the database"
- "If the user exists, the register operation should fail, return an error message, and leave the database unchanged"

Important:
- Don't add requirements not in the documentation
- Focus on functional behavior
- Be specific about state changes
- Use clear English
- Avoid implementation details

Return your analysis in two parts:
### Analysis
Step-by-step reasoning of requirement extraction

### Output
```json
["requirement 1", "requirement 2", ...]
```

Make sure you have "### Output\n```json" in your response so that I can find the Json easily."""

    def __init__(self, model: str = "qwen-max-latest"):
        self.model = model

    async def generate_requirements(self,
                                 api_name: str,
                                 api_doc: str,
                                 logger: Optional[Logger] = None) -> List[str]:
        """Generate requirements for a single API"""
        user_prompt = f"""# API Name
{api_name}

# Documentation
{api_doc}"""

        if logger:
            logger.model_input(f"Requirement generation prompt for {api_name}:\n{user_prompt}")

        # Call LLM
        response = await _call_openai_completion_async(
            model=self.model,
            system_prompt=self.ROLE_PROMPT,
            user_prompt=self.SYSTEM_PROMPT + "\n\n" + user_prompt,
            temperature=0.0
        )

        if logger:
            logger.model_output(f"Requirement generation response for {api_name}:\n{response}")

        # Parse response
        try:
            json_str = response.split("### Output\n```json")[-1].split("```")[0].strip()
            requirements = json.loads(json_str)
        except Exception as e:
            raise ValueError(f"Failed to parse requirement generation response for {api_name}: {e}")
            
        # Validate requirements
        if not requirements:
            raise ValueError(f"No requirements generated for API: {api_name}")
        if not all(isinstance(r, str) and r.strip() for r in requirements):
            raise ValueError(f"Invalid requirements format for API: {api_name}")
            
        return requirements 