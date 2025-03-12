from typing import Dict, List, Optional
import json
from logging import Logger

from src.utils.apis.langchain_client import _call_openai_completion_async

class RequirementGenerator:
    """Generate formal requirements from API documentation"""
    
    ROLE_PROMPT = """You are a software specification analyzer focusing on API verification. You excel at identifying and formalizing specific, testable requirements from API documentation."""

    SYSTEM_PROMPT = """Background:

We are working on a software project that has a few services, each service has a few APIs.
We want to test each API by generating specific, testable requirements for its input and output.
For the APIs, they maybe call other APIs, so we need to consider the dependent API responses when generating requirements.
In order to break the project and the services into separate APIs, when checking API A, we don't the functionality of its dependent APIs, so we just assume the dependent APIs work as expected and give the response of them as the premise.

Task:
Given an API's documentation, generate a list of specific, testable requirements that:
1. Follow from the documentation
2. Cover all functionality
3. Are clear and unambiguous
4. Specify input/output relationships
5. Specify the relationship between the input params and the input table state. Like the input matches any record in the table or not.
6. Or, specify the relationship between the input params and response of dependent APIs given that input params. Like the dependent api will return success type given the input params.
7. Define database state changes between the original table state and the new table state after the API is called. Explain it as the addition, deletion, modification or existence of specific records in the table, or the difference between the original table state and the new table state.

To be specific, in the input part, we may explain:
1. Input param requirements
2. Database state requirements, maybe related to the input params
3. Dependent API responses given the input params if any dependent APIs are called
4. May need to add some other premises in advance to rule out some possible errors:
    - For example, to make a login API works correctly, we need to assume that the user table has no duplicate users. So If you want to check the database error response, you can assume the user table has duplicate users.
    - But if you want to check the success response or the invalid credential error response, you need to express first that the user table has no duplicate users as the high level premise, after that explaining if the user exists or if the password is correct to determine the response.
    - You need to express this kind of premise in the requirements too, to make sure the requirement correctly describe the API behavior.

The output part will be:
1. The response of the API
2. The database update or new attributes of the table

Each requirement should explain:
- Under what input conditions
- With what database states
- If any dependent APIs are called, what are the responses of the dependent APIs
- The API must:
  * Return what response
  * Make what database changes

Example requirements:
- "If the user is not in the user table, the register operation should succeed, return a success message, and the user table should have the new user record"
- "If the user exists in the user table, the register operation should fail, return an error message, and the user table should not be changed"
- "If the user and the password pass the validation and return success, then this API should return the user info and the table should not be changed"

Important:
- Don't add requirements not in the documentation
- Focus on functional behavior
- Be specific about state changes
- Always explicitly explain the responses of the dependent APIs if any, by providing the name of the API and the response type
- Use clear English
- Avoid implementation details, just focus on the input/output relationship and the database state changes

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