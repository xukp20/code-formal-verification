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
5. Following the above rules, you need to look for sequential and hiding premises in the documentation, and express them explicitly in the requirements.
    - For example, if the first line of the documentation is "If the input param is not valid, return a input not valid error", and the following lines describe the logic when the input param is valid, you should:
        - First correct a requirement explaining that when the input param is not valid, the API will return a input not valid error.
        - Then, for the following lines, you should always add a explanation that "The input param is valid" as one of the premise, to make sure the requirement correctly describe the API behavior.
        - This is needed because every requirement will be used independently, so it needs to be self-contained, without losing any premise that is hidden in another requirement before it (which is not visible to it later).

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
Step-by-step reasoning of requirement extraction, following this format:

- If the documentation describe the API logic in a sequential way, please rewrite the doc content to make it more readable:
    - Add omitted premises if any to the other branches of the logic
    - Split the line with "or" logic into multiple lines
        - For example, if the doc content explains (If A or B, then C), then it means A -> C and B -> C, so you need to generate two requirements.
        - But any "and" logic should be considered as one requirement, for example, if the doc content explains (If A and B, then C), then it means A together with B gives C, so you only need to generate one requirement.
        - For the "or" logic, consider carefully to determine if you need to generate multiple requirements.

- Go through the doc line by line:
1. See if a new requirement is introduced. 
- If any new requirement is introduced, create a raw description of it, to go through the following steps one by one:
    - Consider which of the premises needs to be added to this requirement to make sure it is self-contained.
    - Premises should be added if they explain the control flow so that we can only move to the current requirement when the premise is true.
    - Not all of the premises are needed for every requirement. Sometimes the new requirement just contains the previous premise, for example, there is exactly one matched record in the table contains the premise that there are records matched the input params.
- Write the whole requirement as a sentence, explaining "If" what conditions, "then" what response from the API together with the database state changes.
2. Repeat the above steps until the whole documentation is considered.

So write the analysis like this:

#### Rewriting the doc content
<rewrite the doc content to make it more readable:
- Add omitted premises if any to the other branches of the logic
- Split the line with "or" logic into multiple lines

For example: 
- If s = A, return a
- then check if t = B or if t = C, if so return x.
- If not, then return y.

After rewriting:
- If s = A, return a
- If not s = A then check t:
    - If t = B, return x
    - If t = C, return x (Here we only split the line with "or" logic into multiple lines, and we don't add not t = B here because t = C already implies not t = B)
    - If not t = B and not t = C, return y

By writing like this, you can see the premises for each line (branch) of doc by merging the upper level items.

#### Requirement <0-n>
##### Doc content
<repeat the line of the doc content you depend on to generate this requirement>
    - If t = B, return x

##### Current premises 
<list all the premises you have considered so far, like "Check valid returns success, input param is legal...">
<This is can be done in the most cases by merging the upper level items of the doc content>
<For example, for a structure like:
If A:
    - If B:
        - If C:
            - If D, then x
            - If not D, then y
Then the final line should have premises:
- A
- B
- C
- not D

For example for the example line above, premises should be:
- not s = A

##### Thinking
<your thinking of how to describe this rule, and which premises are needed to combine with the doc content to generate this requirement>
For example, just consider how to merge "not s = A" with "If t = B, return x"

##### Requirement
<the requirement you finally write, by fusing the conditions from the doc content and premises that are not included in the doc content, and explaining the output and the database state changes>
<Consider which premises can be merged together if some of them contain others, and how to explain the requirement in a concise but complete way>
For example:
- If not s = A and t = C, return x

In the next loop:
The line is "- If not t = B and not t = C, return y"
Since this line is parallel to the previous line, we only use "not s = A" as the premise, and not add "t = C" to the list.
Then the premises are:
- not s = A
(By writing the doc in a structured itemized way, we can see the premises for each line (branch) of doc by merging the upper level items)


Loop until you have considered all the doc content.

Final Output format:

### Output
```json
["requirement 1", "requirement 2", ...]
```

Example:
### Output
```json
    [
        "If the input param a is not legal, return a input not legal error and all the tables remain unchanged",
        "If the input param a is legal, but checkValid returns false, return a input not valid error and keep the xxx table unchanged",
        "If the input is legal and checkValid returns true, and there are multiple records in the xxx table, return a database integrity error and keep the xxx table unchanged",
        "If the input is legal and checkValid returns true, and there is exactly one record in the xxx table, return ... and the table ...",
        "If the input is legal and checkValid returns true, and there is no record in the xxx table, return ... and the table ...",
        ...
    ]
```

Make sure you have "### Output\n```json" in your response so that I can find the Json easily."""

    def __init__(self, model: str = "qwen-max-latest", max_retries: int = 3):
        self.model = model
        self.max_retries = max_retries

    async def generate_requirements_once(self,
                                 api_name: str,
                                 api_doc: str,
                                 logger: Optional[Logger] = None) -> List[str]:
        """Generate requirements for a single API"""
        user_prompt = f"""# API Name
{api_name}

# Documentation
{api_doc}

Make sure you have "### Output\n```json" in your response so that I can find the Json easily."""

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
            # raise ValueError(f"Failed to parse requirement generation response for {api_name}: {e}")
            return None
            
        # Validate requirements
        if not requirements:
            # raise ValueError(f"No requirements generated for API: {api_name}")
            return None
        if not all(isinstance(r, str) and r.strip() for r in requirements):
            # raise ValueError(f"Invalid requirements format for API: {api_name}")
            return None
            
        return requirements 
    
    async def generate_requirements(self,
                                 api_name: str,
                                 api_doc: str,
                                 logger: Optional[Logger] = None) -> List[str]:
        """Generate requirements for a single API"""
        for _ in range(self.max_retries):
            requirements = await self.generate_requirements_once(api_name, api_doc, logger)
            if requirements:
                return requirements
        raise ValueError(f"Failed to generate requirements for API: {api_name}")