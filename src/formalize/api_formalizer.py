from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import json
from logging import Logger
import asyncio

from src.types.project import ProjectStructure, Service, Table, APIFunction
from src.types.lean_file import LeanFunctionFile
from src.utils.apis.langchain_client import _call_openai_completion_async
from src.formalize.constants import DB_API_DECLARATIONS

class APIFormalizer:
    """Formalize APIs into Lean 4 functions"""
    
    ROLE_PROMPT = """You are a formal verification expert specializing in translating APIs into Lean 4 code. You excel at creating precise mathematical representations of API operations while maintaining their semantics and dependencies."""

    REFERENCE_DB_API_DECLARATIONS = """
## Reference Database API Interface
Here is the package implementation of the database APIs:
```scala
""" + DB_API_DECLARATIONS + """    
```
Note that this is the source code of scala that is for reference, there is not this file in the Lean Project. You should only look at it to understand the meaning of the database operations, but you can not import or use it in the Lean code.

"""

    SYSTEM_PROMPT = """
## Background
This software project uses multiple APIs with dependencies on tables and other APIs. You will formalize these APIs into Lean 4 code.

We have completed:
1. Table formalization into Lean 4 structures
2. API dependency analysis (both table and API dependencies)
Now we need to formalize each API implementation into Lean 4 code.


## Task
Convert the given API implementation into Lean 4 code which has exactly same meaning as the original code following these requirements:

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

   - You are given the scala code of the database APIs before, but they are only for you to understand the usage of database in the scala code, and should not be used in the Lean code, instead just read the raw sql code and translate it into Lean 4 code handling the table structure.
   
   - ! Keep the helper functions easy:
     - For the helper functions, if they don't change the table, you should not input and output the table parameters.
     - Only make sure every API has the related tables as parameters and return the updated tables as outputs.
   - Note that we need to check the correctness of the API, by examining both the output and the new table status, so in the current API and its helper functions, you MUST NOT ignore any updated table by assuming it is not changed.
   - Order of records: Since in the structure of the table we use a list of records to represent the table content which is actually a set, you should always add the new record to the end of the list if needed.

3. API dependencies:
   - A call to another API is in the format of `xxxMessage.send` in the Planner code, and you should import and open the dependent API file and formalize the api call as a function call to that API which is already formalized.
   - If the formalized function of the dependent API has any table as an input, you should `import and open` that table file (which can be copied from the import part of the dependent API file), and then:
    - You can use the short name for the table structure now in the definitions of the current API, like `XTable` or `YTable` instead of the full name like `xxx.yyy.ZTable`.
    - If the input table is not formalized as a input/output pair yet, you should add it to the input/output pair of the current API so that we can use the old table as the input parameter to the dependent API.
        - For example, the current API A use table X, and calls API B that use table Y, you should import and open both X and Y, and A is defined with two table parameters like (old_x_table: XTable, old_y_table: YTable), and you should return the updated tables as outputs.
    - If the required table of the dependent API is already formalized as a input/output pair, just use that for the input parameter and remember to update the table after the dependent API call.
   - Check the return type of the dependent API, to handle each part and each situation correctly.
    - The original code may return the error returned from the dependent API directly, so you need to look at each type that may be returned from the dependent API and handle them correctly with match-case. If the original code just return the error type, you need to add that error type to the result type of the current API too.
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
    - "Important": You can only ignore the table variable in this way, you must not ignore any return value or error types!

4. Outcome Types:
   - Use explicit inductive types for outcomes
   - Common patterns:
     ```lean
     inductive <api_name>Result where
       | Success : <api_name>Result
       | NotFoundFailure : <api_name>Result
       | <SomeKindOfError>Error : <api_name>Result
     ```
   - Name the result type as <api_name>Result like UserLoginResult, BalanceQueryResult, etc.
   - *Important*: Please distinguish different types of returns, including the response type and the message string to define each of them as a different result type
    - Every different type and different message should be a different result type, so that we can distinguish them in the result type
    - Don't just use a single Error type to represent all the errors, because we need to check if the error is expected or not too
   - *Important*: We don't keep the error message string in the result type, just use types to represent different results
   - If any value needs to be returned from the API, you should add it to the result type
    - For example, if the API returns an int, you should add it to the result type like this:
        ```lean
        inductive <api_name>Result where
          | Success : Int → <api_name>Result
          | ...
        ```
        So that we can check if the API returns a correct value or not.
   - *Important*: The exceptions raised in the code is just a type of the API response, so you should never use `panic!` to handle them (which will make the lean code crash), instead you should use the result type to represent the different results
   - Make sure you return the correct result type when error occurs, by checking that all the branches of the result type are covered.
    - Don't just put some comment beside the code, you must return the correct result type all the way from where it is created to the return of the main function.
   - Go through all the code of the main function and the helper functions to collect all the possible error types and messages.
   - Results with same type and message but returned from different functions are still the same result type, so be sure to merge them.
   - Make sure every defined result type is used in the code and will be returned from some branch of the code. Don't define a result type that is not used like an abstract "Error" type.
   - Return values directly without IO wrapper

5. Return Types:
   - The final return type of the function should be the outcome type together with all the tables that are input in the function signature
   - For example, if the function is defined as def foo (old_x_table: XTable) (old_y_table: YTable) : FooResult × XTable × YTable := ..., you should return FooResult × XTable × YTable in the return type.

6. Implementation Fidelity:
   - !Top1 priority: The formalized code should be semantically equivalent to the original code, in the level of each line of code
    - There maybe bugs in the original code, but you should not fix them, just translate the original code, because we just want to use the formalization to look for the bugs in the original code.
    - Translate based on the code logic, not the comments. You can refer to the comments to understand the code, but if they are not consistent with the code logic, you should follow the code logic.
   - Base the formalization on the Planner code
   - For the db operations, you may see raw SQL code, you should make sure the formalized code is semantically equivalent to the original code.
   - Except for the db operations, you should keep the original code structure and logic as much as possible, like the if-else structure, the match-case structure, etc.
   - Preserve error handling and validation logic

7. Code Structure
   - Keep the original code organization
   - Create helper functions matching internal methods, and keep the return types of the helper functions as much as possible (except for IO wrapper, db operations and add returned error types that are raised as exceptions in the original code)
   - Use meaningful names for all functions
   - Example:
     ```lean
     def validateInput (input: String) : Bool := ...
     def processData (data: String) (old_table: Table) : Result := ...
     ```

8. Function Naming
   - Try to use the same name as the original code for the helper functions
   - The main function of the API should be named as the API name, but following the Lean 4 naming convention, like `userLogin` or `balanceQuery` or `userRegister`
   - Don't add `Message` or `Planner` in the function name, just the API name

9. Possible Bugs
   - The target of our formalization is to find the bugs in the original code, so you should not fix the bugs in the original code, just translate the original code to keep that bug in the formalized code
   - But you are provided with an optional output part title as "### Warning" to collect all the possible bugs you think there are in the original code
   - So if you see any bugs in the original code, you should put them in the "### Warning" part, but still translate the original code to keep the bug in the formalized code


## Output

### Analysis
Step-by-step reasoning of your formalization approach following the structure below:

#### Imports
- Analyze what to import and opens based on the current file and the dependent APIs and tables
- All the tables that the dependent APIs use should be imported and opened, you can find the imports and open commands in the dependent APIs' imports part. After that you can use the short name for the table structure.
- Be aware that all the imports must be in the front of the file and all the open commands should be after them

#### Return Types
First list all the dependent APIs to analyze the return types of them to be handled in this API, like this:

##### Dependent APIs
For each of the dependent APIs, you need to:
1. Look for all the returned type in the Lean file of the dependent API
2. Find out where it is called and how the return type is handled
- Note that if some exception is not handled, it will be kept as an exception returned by the current API, which should be added to the result type of the current API

##### Helper Functions
For each of the helper functions, you need to:
1. Copy the content of the helper function for reference here
2. Look for all the exceptions raised in the helper function, which will be an result type too.

##### Main Function
For the main function, you need to:
1. Copy the content of the main function for reference here
2. Look for all the exceptions raised in the main function, which will be an result type too.
3. Look for success types and find out if there is any value returned from the API, if so, add it to the result type.
4. Note that the info message is not a return value:
    - For example, if all success gives a string "Success", you should not add a string "Success" to the success type.
    - But if the success type return an int value for some actual meaning that should be different for different input params, you should add it to the success type.

##### Collect all the result types
1. List all the result types presented above, each as an item in the list
2. For each one in the list, check that it is actually used in the code, which means it should be returned from some branch of the code or raised by a dependent API. If not, remove it from the list.
3. Look for result types that are exactly the same, which means they have the same type (success, or type of the exceptions) and the same content (the return value, or the error message). If so, merge them into one result type.
4. Note that the info message is not a return value:
    - For example, if all success gives a string "Success", you should not add a string "Success" to the success type.
    - But if the success type return an int value for some actual meaning that should be different for different input params, you should add it to the success type.
5. Be careful with return types that has a string inside, there is a big chance that it is not a return value but an info message, so you should not add it to the success type.
    - Examine all the return types with a string inside to figure out if it is a return value or an info message. If info message, just remove the string.

##### Formalize the result type
Present the Lean 4 code of the result type following the format below:
```lean
inductive <api_name>Result where
  | Success : <api_name>Result
  | ...
```
- We can assume that database operations are always successful, so you don't need to handle the error types of the database operations.
- This part should be put in the helper_functions part
-  Note that the info message is not a return value:
    - For example, if all success gives a string "Success", you should not add a string "Success" to the success type.
    - But if the success type return an int value for some actual meaning that should be different for different input params, you should add it to the success type.
- "Important": Be careful with return types that has a string inside, there is a big chance that it is not a return value but an info message, so you should not add it to the success type.
    - Examine all the return types with a string inside to figure out if it is a return value or an info message. If info message, just remove the string.

#### Code Structure
- Design the structure and the content of the helper functions and the main function following the original code structure
- You should put a definition of the result type in the helper_functions part
- You should put a list of helper functions in the helper_functions part
- You should put the main function in the main_function part
- Not other parts are needed in the helper_functions and main_function parts
- Tables should be imported from their files
- Don't add any functions related to raw SQL operations because they are wrapped in the database APIs and you just handle the structure of the tables in Lean 

#### Helper Functions Details
 - For this part, you need to first take out all the helper functions from the source code one by one.
 - For each function taken, first repeat its content for reference, and then try to understand what its doing and how it is implemented.
 - You may think there are some bugs in the original code, just point it out for future collection, then pay attention to it to make sure the formalized code is the same as the original code, which means the bug is still there in the formalized code
 - After that, write the formalized code for this single function
So for each of the helper functions, you need:
##### <helper_function_name>
1. Original Code
```scala
<original_code>
```

2. Analysis
- What it does, by reading the code line by line
- How it is implemented
- Any potential bugs
- What is called in this function: Any dependent APIs or any other helper functions? If so, what are the return types of the dependent functions and how to handle each of the branches?
    - For dependent APIs, any unchanged tables can be ignored?
    - For return values and error types that are not the table, make sure you never ignore them with "_"
- What is the return type of the function: if any exception is raised, you can return a value which is align with the original code type together with a result type of the current API to handle the errors
    - For example, if the original code returns a bool with some tables, you can return bool × <api_name>Result × AnyTable... if you need to handle possible errors raised in this function

3. Formalized Code
- Write the formalized code for this single function
- If call any helper functions or dependent APIs, you should handle all the possible return types and errors, instead of ignoring all or some of them
- Add comments to the Lean code in English, can be the same as the original code comments or some more detailed explanations
```lean
<formalized_code>
```

4. Analysis of the Formalized Code
- Compare the formalized code with the original code, to make sure the formalized code is semantically equivalent to the original code
- If not, rewrite the formalized code and analysis


#### Main Function Details
- For the main function, you need to:
1. Repeat the original code for reference
2. Analyze the original code
3. Write the formalized code
4. Analyze the formalized code to make sure it is semantically equivalent to the original code
Follow the same structure as the helper functions.
- "Important": Make sure you translate the original code without changing any logic or adding any new logic, there maybe bugs in the original code, but you should not fix them, just translate the original code. Don't fully trust the comments, you should follow the code logic.
- "Important": If call any helper functions or dependent APIs, you should handle all the possible return types and errors, instead of ignoring all or some of them
    - Which means you should match all the possible return types and errors from the helper functions or dependent APIs, and determine what to do for each of the branches
    - For example, if the helper function returns a db error or other kind of error, you cannot ignore it with "_", instead you should handle it with match-case and return the error type

#### Gather possible bugs
- After analyzing the original code and the formalized code, gather all the possible bugs in the original code here to be presented later.

#### Final Code
- Write the final code
    - Put imports and open commands in the imports part
    - Put the type definitions and helper functions in the helper_functions part
    - Put the main function in the main_function part
- Compare the original code with the formalized Lean code to make sure the formalized code is semantically equivalent to the original code, to fix any details that are not consistent
    - Put enough effort in this part because there maybe bugs that you didn't notice in the original code and modify it unconsciously and then the formalization is incorrect
    - Don't allow any difference between the original code and the formalized Lean code, to make sure the formalization is correct
- After this part, we have finished the Analysis part, then we will present the Lean code in the next part

(Use ```lean and ``` to wrap the code, not ```lean4!)
### Lean Code
```lean
<complete file content following the structure template>
```

### Warning
(Optional, only if you find some bugs during the analysis, write it with the title "### Warning". )
- assume that the database operations are always successful, so you don't need to look for possible errors in the database operations
- If there is no warning, put a single word "None" for this part, without any other words

### Output
```json
{{
  "imports": "string of import statements and open commands",
  "helper_functions": "string of return type definition and helper function definitions ",
  "main_function": "string of main function definition"
}}
```


Return your response in three parts: ### Analysis, ### Lean Code, ### Output
- Ensure all the error types are passed to the current API function and returned correctly instead of ignored with "_"
- Add comments to the Lean code in English
- Make sure the content in the Json object of the ### Output part is directly copied from the Lean Code part, and make no omission like the comments, the helper functions, etc.
- The final result will be taken from the ### Output part, so make sure to put everything in the Lean file into that part and make no omission like the comments, the helper functions, etc.
- Make sure you have "### Output\n```json" in your response so that I can find the Json easily.
"""

    RETRY_PROMPT = """
### Generated Lean file
{lean_file}
    
### Compilation failed with error
{error}

Please fix the Lean code while maintaining the same structure:
{structure_template}

Return both the corrected code and parsed fields.

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
                        "planner_code": True, 
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
            # "\n# Database API Interface",
            # "```scala",
            # DB_API_DECLARATIONS,
            # "```",
            # "(The Database API Interface is only for reference, you should not use it in the Lean code, instead just read the raw sql code and translate it into Lean 4 code handling the table structure.)\n\n",
            APIFormalizer._format_table_dependencies(project, service, table_deps),
            APIFormalizer._format_api_dependencies(project, api_deps),
            "\n# Current API",
            api.to_markdown(show_fields={"planner_code": True, "message_code": True}),
            # "\nInstructions: ",
            # "1. Keep the original code structure and logic as much as possible, like the if-else structure, the match-case structure, etc.",
            # "2. The formalized code should be semantically equivalent to the original code, in the level of each function or each line of code",
            # "3. You can add some comments to explain the code, but don't add too many comments, only add comments to the key steps and important parts.",
            # "4. I take the final output only from the Json part, so make sure to put everything in the Lean file into those fields and make no omission.",
            # "5. Make sure the content in the Json object is directly copied from the Lean Code part, and make no omission like the comments, the helper functions, etc.",
            # "6. Add comments to the code in English",
            # "Important: Make sure you translate the original code without changing any logic or adding any new logic, there maybe bugs in the original code, but you should not fix them, just translate the original code. Don't fully trust the comments, you should follow the code logic.",
            # "Remember: You are translating the code not writing the code, ALWAYS follow the given code carefully and look carefully at every detail of the code.",
            # "Make sure you have '### Output\n```json' in your response so that I can find the Json easily."
        ]
        return "\n".join(parts)

    def _post_process_response(self, fields: Dict[str, str], logger: Optional[Logger] = None) -> Optional[str]:
        """Check for illegal content in the response
        
        Args:
            fields: Parsed fields from LLM response
            logger: Optional logger
            
        Returns:
            Error message if illegal content found, None otherwise
        """
        # Check helper functions for panic!
        if "helper_functions" in fields:
            if "panic!" in fields["helper_functions"].lower():
                if logger:
                    logger.warning("Found panic! in helper functions")
                return "panic! is not allowed in helper functions. Please handle errors using result types instead."
                
        # Check main function for panic!
        if "function" in fields:
            if "panic!" in fields["function"].lower():
                if logger:
                    logger.warning("Found panic! in main function")
                return "panic! is not allowed in function body. Please handle errors using result types instead."
                
        return None
    
    def _parse_warning(self, response: str) -> Optional[str]:
        """Parse the warning from the response"""
        if "### Warning" in response:
            warning_parts = response.split("### Warning")
            if len(warning_parts) > 1:
                warning_text = warning_parts[-1].split("###")[0].strip()
                lines = warning_text.split("\n")
                # If any line is "None", return None
                if any(line.strip() == "None" for line in lines):
                    return None
                return warning_text
        return None

    async def formalize_api(self, project: ProjectStructure, service: Service, 
                           api: APIFunction, table_deps: List[str], 
                           api_deps: List[Tuple[str, str]], 
                           logger: Logger = None) -> bool:
        """Formalize a single API"""
        if logger:
            logger.debug(f"Formalizing API: {service.name}.{api.name}")
            
        # Initialize Lean file with lock
        await project.acquire_lock()
        lean_file = project.init_api_function(service.name, api.name)
        project.release_lock()
        
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
                     else self.REFERENCE_DB_API_DECLARATIONS + "\n\n" + f"{system_prompt}\n\n{user_prompt}")
            
            if logger:
                logger.model_input(f"Prompt:\n{prompt}")
                
            response = await _call_openai_completion_async(
                model=self.model,
                system_prompt=self.ROLE_PROMPT,
                user_prompt=prompt,
                history=history,
                temperature=0.0
            )

            history.extend([
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response if response else "Failed to get LLM response"}
            ])
            
            if logger:
                logger.model_output(f"LLM response:\n{response}")
                
            if not response:
                error_message = "Failed to get LLM response"
                await project.acquire_lock()
                project.restore_lean_file(lean_file)
                project.release_lock()
                continue
                
            # Parse response
            try:
                # look for warning part
                warning_text = self._parse_warning(response)
                if warning_text and logger:
                    logger.warning(f"Formalization warning for {api.name}: {warning_text}")
   
                json_str = response.split("```json")[-1].split("```")[0].strip()
                fields = json.loads(json_str)
                
            except Exception as e:
                if logger:
                    logger.error(f"Failed to parse LLM response: {e}")
                error_message = str(e)
                await project.acquire_lock()
                project.restore_lean_file(lean_file)
                project.release_lock()
                continue

            # Post-process response
            error_message = self._post_process_response(fields, logger)
            if error_message:
                if logger:
                    logger.warning(f"Post-processing failed: {error_message}")
                await project.acquire_lock()
                project.restore_lean_file(lean_file)
                project.release_lock()
                continue
            
            # Update and build with lock
            await project.acquire_lock()
            try:
                # Update Lean file
                project.update_lean_file(lean_file, fields)
                
                # Try compilation
                success, error_message = project.build(parse=True, add_context=True, only_errors=True)
                if success:
                    if logger:
                        logger.info(f"Successfully formalized API: {api.name}")
                    project.release_lock()
                    return True
                    
                lean_file_content = lean_file.to_markdown()
                project.restore_lean_file(lean_file)
            finally:
                project.release_lock()

        # Clean up on failure with lock
        await project.acquire_lock()
        project.delete_api_function(service.name, api.name)
        project.release_lock()
        
        if logger:
            logger.error(f"Failed to formalize API {api.name} after {self.max_retries} attempts")
        return False

    async def _formalize_parallel(self, project: ProjectStructure, logger: Logger = None, max_workers: int = 1) -> ProjectStructure:
        """Formalize APIs in parallel following dependency order"""
        if logger:
            logger.info(f"Formalizing APIs in parallel for project: {project.name}")

        # Track API completion status
        completed_apis = set()
        pending_apis = {(service_name, api_name) for service_name, api_name in project.api_topological_order}
        
        # Create semaphore to limit concurrent tasks
        sem = asyncio.Semaphore(max_workers)

        async def process_api(service_name: str, api_name: str):
            service = project.get_service(service_name)
            api = project.get_api(service_name, api_name)
            if not service or not api:
                return False

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
            
            if success:
                completed_apis.add((service_name, api_name))
            return success

        async def process_with_semaphore(service_name: str, api_name: str):
            async with sem:
                return await process_api(service_name, api_name)

        while pending_apis:
            # Find APIs whose dependencies are all completed
            ready_apis = set()
            for service_name, api_name in pending_apis:
                api = project.get_api(service_name, api_name)
                if not api:
                    continue
                    
                deps_completed = all((dep_service, dep_api) in completed_apis 
                                  for dep_service, dep_api in api.dependencies.apis)
                if deps_completed:
                    ready_apis.add((service_name, api_name))

            if not ready_apis:
                if logger:
                    logger.warning("No APIs ready to process, possible circular dependency")
                break

            # Process ready APIs in parallel
            tasks = [process_with_semaphore(service_name, api_name) 
                    for service_name, api_name in ready_apis]
            results = await asyncio.gather(*tasks)

            # Update pending set
            pending_apis -= ready_apis
            
            # Check for failures
            if not all(results):
                if logger:
                    logger.error("Some APIs failed to formalize, stopping")
                break

        return project

    async def formalize(self, project: ProjectStructure, logger: Logger = None, max_workers: int = 1) -> ProjectStructure:
        """Formalize all APIs in the project"""
        if not project.api_topological_order:
            if logger:
                logger.warning("No API topological order available, skipping formalization")
            return project

        if max_workers > 1:
            return await self._formalize_parallel(project, logger, max_workers)
            
        # Original sequential logic
        if logger:
            logger.info(f"Formalizing APIs for project: {project.name}")
            
        for service_name, api_name in project.api_topological_order:
            service = project.get_service(service_name)
            api = project.get_api(service_name, api_name)
            if not service or not api:
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