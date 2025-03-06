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

    SYSTEM_PROMPT = """Background:
This software project uses multiple APIs with dependencies on tables and other APIs. You will formalize these APIs into Lean 4 code.

Task:
Convert the given API implementation into Lean 4 code following these requirements:

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

3. Return Types:
   - Use explicit inductive types for outcomes
   - Common patterns:
     ```lean
     inductive OperationResult where
       | Success : String → OperationResult
       | NotFound : String → OperationResult
       | Error : String → OperationResult
     ```
   - Replace the OperationResult with a meaning result type
   - Use these types to represent success/failure states
   - Include meaningful messages in constructors
   - Handle all error cases without panic!
   - Return values directly without IO

4. Implementation Fidelity:
   - Maintain semantic equivalence with original code
   - Maintain the same structure of the original code, the more similar the better
   - Try to translate the codes line by line if possible to make sure they are semantically equivalent
   - Translate SQL operations accurately
   - Preserve error handling logic

5. Code Structure
   - Keep the original code organization
   - Create helper functions matching internal methods
   - Use meaningful names for all functions
   - Maintain the same function hierarchy
   - Example:
     ```lean
     def validateInput (input: String) : Option String := ...
     def processData (data: String) : Result := ...
     def mainFunction (input: String) : Result := ...
     ```

6. Function Naming
   - Try to use the same name as the original code

Return your response in two parts:
### Lean Code
```lean
<complete file content following the structure template>
```

### Output
```json
{{
  "imports": "string of import statements",
  "helper_functions": "string of helper function definitions",
  "main_function": "string of main function definition"
}}
```
"""

    RETRY_PROMPT = """Compilation failed with error:
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
        lines = ["# Table Dependencies"]
        for table_name in table_deps:
            table = project.get_table(service.name, table_name)
            if not table:
                continue
            lines.extend([
                table.to_markdown(show_fields={"description": True, "lean_structure": True})
            ])
        return "\n".join(lines)

    @staticmethod
    def _format_api_dependencies(project: ProjectStructure, api_deps: List[Tuple[str, str]]) -> str:
        """Format dependent APIs with their implementations and Lean code"""
        lines = ["# API Dependencies"]
        for service_name, api_name in api_deps:
            api = project.get_api(service_name, api_name)
            if not api:
                continue
            lines.extend([
                api.to_markdown(show_fields={
                    "planner_code": True, 
                    "message_code": True, 
                    "lean_function": True
                })
            ])
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
            "(The Database API Interface is only for reference, you should not use it in the Lean code, instead just read the raw sql code and translate it into Lean 4 code handling the table structure.)",
            APIFormalizer._format_table_dependencies(project, service, table_deps),
            APIFormalizer._format_api_dependencies(project, api_deps),
            "\n# Current API",
            api.to_markdown(show_fields={"planner_code": True, "message_code": True})
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

        for attempt in range(self.max_retries):
            # Backup current state
            lean_file.backup()
            
            # Call LLM
            prompt = (self.RETRY_PROMPT.format(error=error_message, 
                     structure_template=structure_template) if attempt > 0 
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
                continue
                
            # Parse response
            try:
                lean_code = response.split("### Lean Code\n```lean")[-1].split("```")[0].strip()
                json_str = response.split("### Output\n```json")[-1].split("```")[0].strip()
                fields = json.loads(json_str)
                
            except Exception as e:
                if logger:
                    logger.error(f"Failed to parse LLM response: {e}")
                project.restore_lean_file(lean_file)
                continue

            
            # Update Lean file
            project.update_lean_file(lean_file, fields)
            
            # Try compilation
            success, error = project.build(parse=True, add_context=True, only_errors=True)
            if success:
                if logger:
                    logger.debug(f"Successfully formalized API: {api.name}")
                return True
                
            # Restore on failure
            project.restore_lean_file(lean_file)
            error_message = error
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