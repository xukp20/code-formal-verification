from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import json
from logging import Logger

from src.types.project import ProjectStructure, Service, Table, APIFunction
from src.types.lean_file import LeanFunctionFile
from src.utils.apis.langchain_client import _call_openai_completion_async
from src.formalize.constants import DB_API_DECLARATIONS

class APIFormalizer:
    """Formalize APIs into Lean 4 functions"""
    
    ROLE_PROMPT = """You are a formal verification expert specializing in translating APIs into Lean 4 code. You excel at creating precise mathematical representations of API operations while maintaining their semantics and dependencies."""

    SYSTEM_PROMPT = """
## Background
This software project uses multiple APIs with dependencies on tables and other APIs. You will formalize these APIs into Lean 4 code.

We have completed:
1. Table formalization into Lean 4 structures
2. API dependency analysis (both table and API dependencies)
Now we need to formalize each API implementation into Lean 4 code.


## Task
Convert the given API implementation into Lean 4 code following these requirements:

## Requirements
1. Follow the exact file structure:
{structure_template}

2. Database Operations:
   - ! Always input and output the related tables in the main function of the API
    - For API, each table accessed should have a corresponding parameter in the function signature
        * Input parameter: old_<table_name>: <TableName>
        * Output parameter: new_<table_name>: <TableName>
    - For read-only: return input table unchanged
    - Example:
        ```lean
        def updateUser (id: Nat) (name: String) (old_user_table: UserTable) : UpdateResult × UserTable := 
        // ... implementation ...
        return (UpdateResult.Success, new_user_table)
        ```

   - You are given the scala code of the database APIs, but they should not be used in the Lean code, instead just read the raw sql code and translate it into Lean 4 code handling the table structure.
   
   - ! Keep the helper functions easy:
     - For the helper functions, if they don't change the table, you should not input and output the table parameters.
     - Only make sure every API has the related tables as parameters and return the updated tables as outputs.
   - Note that we need to check the correctness of the API, by examining both the output and the new table status, so in the current API and its helper functions, you MUST NOT ignore any updated table by assuming it is not changed.
   - You should always take the updated tables from a helper function that uses the table or a dependent API to use it for the future operations until return it as the part of the return value.

3. API dependencies:
   - A call to another API is in the format of xxxMessage.send in the Planner code, and you should import and open the dependent API file and formalize the api call as a function call to that API which is already formalized.
   - If the formalized function of the dependent API has any table as an input, you should `import and open` that table file (which can be copied from the import part of the dependent API file), and then:
    - If the input table is not formalized as a input/output pair yet, you should add it to the input/output pair of the current API so that we can use the old table as the input parameter to the dependent API.
        - For example, the current API A use table X, and calls API B that use table Y, you should import and open both X and Y, and A is defined with two table parameters like (old_x_table: XTable, old_y_table: YTable), and you should return the updated tables as outputs.
    - If the required table of the dependent API is already formalized as a input/output pair, just use that for the input parameter and remember to update the table after the dependent API call.
   - Check the return type of the dependent API, to handle each part and each situation correctly.
   - *Possible simplification*: Since we are trying to formalize the current API instead of the dependent API, you are allowed to simplify the call to APIs that are read-only, by ignoring the returned tables from the dependent API and use the old table for the future operations.
    - This can only be used when you are sure the dependent API is read-only, which means it doesn't change any tables.
    - If so, you can write the function call like this:
        ```lean
        let (result, _) := queryXXX(params, old_x_table);
        -- Use the old_x_table for the future operations
        ```
        instead of:
        ```lean
        let (result, new_x_table) := queryXXX(params, old_x_table);
        -- Use the new_x_table for the future operations
        ```

4. Outcome Types:
   - Use explicit inductive types for outcomes
   - Common patterns:
     ```lean
     inductive <api_name>Result where
       | Success : <api_name>Result
       | NotFound : <api_name>Result
       | Error : <api_name>Result
     ```
   - Name the result type as <api_name>Result like UserLoginResult, BalanceQueryResult, etc.
   - Use these types to represent success/failure states
   - Please distinguish different types of returns, including the response type and the message string to define each of them as a different result type
   - We don't keep the raw string in the result type, just use types to represent different results
   - *Important*: The exceptions raised in the code is just a type of the API response, so you should never use panic! to handle them, instead you should use the result type to represent the different results
   - Make sure you return the correct result type when error occurs, by checking that all the branches of the result type are covered.
   - Return values directly without IO wrapper

5. Return Types:
   - The final return type of the function should be the outcome type together with all the tables that are input in the function signature
   - For example, if the function is defined as def foo (old_x_table: XTable) (old_y_table: YTable) : FooResult × XTable × YTable := ..., you should return FooResult × XTable × YTable in the return type.

6. Implementation Fidelity:
   - !Top1 priority: The formalized code should be semantically equivalent to the original code, in the level of each line of code
   - Base the formalization on the Planner code
   - Maintain the same logical flow and operations
   - For the db operations, you may see raw SQL code, you should make sure the formalized code is semantically equivalent to the original code.
        - Some interfaces are provided by the table formalization, you can use them directly.
        - But if none of the interfaces are entirely the same as the sql code, you should write the logic of handling the table by yourself, remember the equivalence is always the top priority.
   - Except for the db operations, you should keep the original code structure and logic as much as possible, like the if-else structure, the match-case structure, etc.
   - Preserve error handling and validation logic

7. Code Structure
   - Keep the original code organization
   - Create helper functions matching internal methods
   - Use meaningful names for all functions
   - Maintain the same function hierarchy
   - Example:
     ```lean
     def validateInput (input: String) : Bool := ...
     def processData (data: String) (old_table: Table) : Result := ...
     ```

8. Function Naming
   - Try to use the same name as the original code
   - The main function of the API should be named as the API name, but following the Lean 4 naming convention, like `userLogin` or `balanceQuery` or `userRegister`
   - Don't add `Message` or `Planner` in the function name, just the API name

   
## Output
Return your response in three parts:

### Analysis
Step-by-step reasoning of your formalization approach

(Use ```lean and ``` to wrap the code, not ```lean4!)
### Lean Code
```lean
<complete file content following the structure template>
```

### Output
```json
{{
  "imports": "string of import statements and open commands",
  "helper_functions": "string of helper function definitions or type definitions",
  "main_function": "string of main function definition"
}}
```
"""

    RETRY_PROMPT = """
Generated Lean file:
{lean_file}
    
Compilation failed with error:
{error}

Please fix the Lean code while maintaining the same structure:
{structure_template}

Return both the corrected code and parsed fields.

Hints:
- Remember to add open commands to your imports to open the imported namespace after imports, these open commands should be in the imports field of the json
- All the newly defined helper functions and types should be in the helper_functions field of the json

Make sure you have "### Output\n```json" in your response so that I can find the Json easily.
"""

    def __init__(self, model: str = "qwen-max-latest", max_retries: int = 3):
        self.model = model
        self.max_retries = max_retries

    @staticmethod
    def _format_table_dependencies(project: ProjectStructure, service: Service, 
                                 table_deps: List[str]) -> str:
        """Format dependent tables with their descriptions and Lean code"""
        if table_deps:
            lines = ["# Table Dependencies"]
            for table_name in table_deps:
                table = project.get_table(service.name, table_name)
                if not table:
                    continue
                lines.extend([
                    table.to_markdown(show_fields={"description": True, "lean_structure": True})
                ])
        else:
            lines = []
        return "\n".join(lines)

    @staticmethod
    def _format_api_dependencies(project: ProjectStructure, api_deps: List[Tuple[str, str]]) -> str:
        """Format dependent APIs with their implementations and Lean code"""
        if api_deps:
            lines = ["# API Dependencies"]
            for service_name, api_name in api_deps:
                api = project.get_api(service_name, api_name)
                if not api:
                    continue
                lines.extend([
                    api.to_markdown(show_fields={
                        # "planner_code": True, 
                        # "message_code": True, 
                        "lean_function": True
                    })
                ])
        else:
            lines = []
        return "\n".join(lines)

    @staticmethod
    def _format_user_prompt(project: ProjectStructure, service: Service, 
                           api: APIFunction, table_deps: List[str], 
                           api_deps: List[Tuple[str, str]]) -> str:
        """Format the complete user prompt"""
        parts = [
            "\n# Database API Interface",
            "```scala",
            DB_API_DECLARATIONS,
            "```",
            "(The Database API Interface is only for reference, you should not use it in the Lean code, instead just read the raw sql code and translate it into Lean 4 code handling the table structure.)\n\n",
            APIFormalizer._format_table_dependencies(project, service, table_deps),
            APIFormalizer._format_api_dependencies(project, api_deps),
            "\n# Current API",
            api.to_markdown(show_fields={"planner_code": True, "message_code": True}),
            "\nInstructions: ",
            "1. Keep the original code structure and logic as much as possible, like the if-else structure, the match-case structure, etc.",
            "2. The formalized code should be semantically equivalent to the original code, in the level of each function or each line of code",
            "3. You can add some comments to explain the code, but don't add too many comments, only add comments to the key steps and important parts.",
            "4. I take the final output only from the Json part, so make sure to put everything in the Lean file into those fields and make no omission.",
            "Make sure you have '### Output\n```json' in your response so that I can find the Json easily."
        ]
        return "\n".join(parts)

    async def formalize_api(self, project: ProjectStructure, service: Service, 
                           api: APIFunction, table_deps: List[str], 
                           api_deps: List[Tuple[str, str]], 
                           logger: Logger = None) -> bool:
        """Formalize a single API"""
        if logger:
            logger.debug(f"Formalizing API: {service.name}.{api.name}")
            
        # Initialize Lean file
        lean_file = project.init_api_function(service.name, api.name)
        if not lean_file:
            if logger:
                logger.error(f"Failed to initialize Lean file for {api.name}")
            return False
            
        # Prepare prompts
        structure_template = LeanFunctionFile.get_structure()
        system_prompt = self.SYSTEM_PROMPT.format(structure_template=structure_template)
        user_prompt = self._format_user_prompt(project, service, api, table_deps, api_deps)
        
        if logger:
            logger.model_input(f"Role prompt:\n{self.ROLE_PROMPT}")
            
        # Try formalization with retries
        history = []
        error_message = None
        lean_file_content = None

        for attempt in range(self.max_retries):
            # Backup current state
            lean_file.backup()
            
            # Call LLM
            prompt = (self.RETRY_PROMPT.format(error=error_message, 
                     structure_template=structure_template,
                     lean_file=lean_file_content) if attempt > 0 
                     else f"{system_prompt}\n\n{user_prompt}")
            
            if logger:
                logger.model_input(f"Prompt:\n{prompt}")
                
            response = await _call_openai_completion_async(
                model=self.model,
                system_prompt=self.ROLE_PROMPT,
                user_prompt=prompt,
                history=history,
                temperature=0.0
            )
            
            if logger:
                logger.model_output(f"LLM response:\n{response}")
                
            if not response:
                error_message = "Failed to get LLM response"
                project.restore_lean_file(lean_file)
                continue
                
            # Parse response
            try:
                lean_code = response.split("### Lean Code\n```lean")[-1].split("```")[0].strip()
                json_str = response.split("### Output\n```json")[-1].split("```")[0].strip()
                fields = json.loads(json_str)
                
            except Exception as e:
                if logger:
                    logger.error(f"Failed to parse LLM response: {e}")
                error_message = str(e)
                project.restore_lean_file(lean_file)
                continue

            
            # Update Lean file
            project.update_lean_file(lean_file, fields)
            
            # Try compilation
            success, error_message = project.build(parse=True, add_context=True, only_errors=True)
            if success:
                if logger:
                    logger.debug(f"Successfully formalized API: {api.name}")
                return True
            lean_file_content = lean_file.to_markdown()
                
            # Restore on failure
            project.restore_lean_file(lean_file)
            history.extend([
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response}
            ])
            
                
        # Clean up on failure
        project.delete_api_function(service.name, api.name)
        if logger:
            logger.error(f"Failed to formalize API {api.name} after {self.max_retries} attempts")
        return False

    async def formalize(self, project: ProjectStructure, logger: Logger = None) -> ProjectStructure:
        """Formalize all APIs in the project"""
        if logger:
            logger.info(f"Formalizing APIs for project: {project.name}")
            
        if not project.api_topological_order:
            if logger:
                logger.warning("No API topological order available, skipping formalization")
            return project
            
        # Process APIs in topological order
        for service_name, api_name in project.api_topological_order:
            service = project.get_service(service_name)
            if not service:
                continue
            api = project.get_api(service_name, api_name)
            if not api:
                continue
                
            # Get dependencies
            table_deps = api.dependencies.tables
            api_deps = api.dependencies.apis
            
            success = await self.formalize_api(
                project=project,
                service=service,
                api=api,
                table_deps=table_deps,
                api_deps=api_deps,
                logger=logger
            )
            
            if not success:
                if logger:
                    logger.error(f"Failed to formalize API {api_name}, stopping formalization")
                break
                
        return project 