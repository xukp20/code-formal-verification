from typing import Dict, List, Optional, Set, Tuple
import json
from src.utils.parse_project.parser import ProjectStructure
from src.utils.apis.langchain_client import _call_openai_completion_async
from src.pipeline.api.types import APIFormalizationInfo
from src.pipeline.api.constants import DB_API_DECLARATIONS
from logging import Logger

class APIFormalizer:
    """Formalize APIs to Lean 4 code"""
    
    SYSTEM_PROMPT = """
You are a formal verification expert tasked with formalizing APIs into Lean 4 code.

Background:
We have completed:
1. Table formalization into Lean 4 structures
2. API dependency analysis (both table and API dependencies)
Now we need to formalize each API implementation into Lean 4 code.

Task:
Convert the given API implementation into Lean 4 code following these specific requirements:

1. Import Dependencies
   - Use correct import paths for all dependent tables and APIs
   - Import paths should match the project structure
   - All the imports should be in the front of the file
   - You can open the imported namespace to use the types without prefix
   - Example: `import ProjectName.Database.TableName`
   - You should define a namespace for current file, and put all the code in the namespace, so that other files can open the namespace to use the types without prefix

2. Database Operations
   - For each table accessed (read or write):
     * Add an input parameter named 'old_<table_name>' of type '<TableName>'
     * Add an output parameter named 'new_<table_name>' of type '<TableName>'
   - For read-only operations:
     * Return the input table unchanged as 'new_<table_name>'
   - For multiple tables:
     * Add parameters in a consistent order
     * Use clear naming to show input/output correspondence
   - Example:
     ```lean
     def updateUser (id: Nat) (name: String) (old_user_table: UserTable) : UpdateResult × UserTable := 
       // ... implementation ...
       return (UpdateResult.Success, new_user_table)
     ```

3. Return Types
   - Define explicit inductive types for different outcomes
   - Common patterns:
     ```lean
     inductive OperationResult where
       | Success : String → OperationResult
       | NotFound : String → OperationResult
       | Error : String → OperationResult
     ```
   - Use these types to represent success/failure states
   - Include meaningful messages in constructors
   - ! Never use panic! to handle errors, always use a defined error type and return all the way to the top level api function
   - Don't need to use IO to wrap the return value, just return the value directly
   
4. Implementation Fidelity
   - !Top1 priority: The formalized code should be semantically equivalent to the original code, in the level of each line of code
   - Base the formalization on the Planner code
   - Maintain the same logical flow and operations
   - Translate each operation to its Lean equivalent
   - For the db operations, you may see raw SQL code, you should make sure the formalized code is semantically equivalent to the original code.
        - Some interfaces are provided by the table formalization, you can use them directly.
        - But if none of the interfaces are entirely the same as the sql code, you should write the logic of handling the table by yourself, remember the equivalence is always the top priority.
   - Preserve error handling and validation logic

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
   - Use clear verb phrases for main functions
   - Follow pattern: <verb><object>[<action>]
   - Examples:
     * createUserAccount
     * validateUserCredentials
     * updateUserProfile

Return your analysis in this format:
### Analysis
Step-by-step reasoning of your formalization approach

(Use ```lean and ``` to wrap the code, not ```lean4!)
### Lean Code
```lean
<complete file content>
```

Please make sure you have '### Lean Code\n```lean' in your response so that I can find the Lean code easily.
"""

    def __init__(self, model: str = "deepseek-r1", max_retries: int = 5):
        self.model = model
        self.max_retries = max_retries

    def _format_dependencies_prompt(self, 
                                  project: ProjectStructure,
                                  api_name: str,
                                  table_deps: List[str],
                                  api_deps: List[str]) -> str:
        """Format the dependencies section of the prompt"""
        lines = ["# Dependencies\n"]
        
        # Add table dependencies
        if table_deps:
            lines.append("## Table Dependencies")
            for table_name in table_deps:
                service, table = project._find_table_with_service(table_name)
                if service and table:
                    lines.append(project._table_to_markdown(service, table))
        
        # Add API dependencies
        if api_deps:
            lines.append("## API Dependencies")
            for dep_api in api_deps:
                service, api = project._find_api_with_service(dep_api)
                if service and api:
                    lines.append(project._api_to_markdown(service, api))
        
        return "\n".join(lines)

    async def formalize_api(self,
                           project: ProjectStructure,
                           service_name: str,
                           api_name: str,
                           table_deps: List[str],
                           api_deps: List[str],
                           history: List[Dict[str, str]] = None,
                           logger: Logger = None) -> bool:
        """Formalize a single API"""
        service, api = project._find_api_with_service(api_name, service_name=service_name)
        if not service or not api:
            raise ValueError(f"API {api_name} not found")

        # Prepare prompts
        deps_prompt = self._format_dependencies_prompt(project, api_name, table_deps, api_deps)
        api_prompt = project._api_to_markdown(service, api, include_description=False)
        target_path = project.get_lean_import_path("api", service_name, api_name)
        
        user_prompt = f"""
# Database API Interface
```scala
{DB_API_DECLARATIONS}
```

{deps_prompt}

# Current API
{api_prompt}

# Target Lean Import Path
`{target_path}`
"""

        history = history or []
        
        for attempt in range(self.max_retries):
            if attempt > 0:
                user_prompt = f"Compilation failed. Error:\n{compilation_error}\n\nPlease fix the Lean code.\n\nPlease make sure you have '### Lean Code\n```lean' in your response so that I can find the Lean code easily."

            if logger:
                logger.debug(f"Formalizing API {api_name} (attempt {attempt + 1}/{self.max_retries})")
                logger.model_input(f"User prompt: {user_prompt}")

            # Call LLM
            response = await _call_openai_completion_async(
                model=self.model,
                system_prompt=self.SYSTEM_PROMPT,
                user_prompt=user_prompt,
                history=history,
                temperature=0.0
            )

            if logger:
                logger.model_output(f"Response: {response}")

            if not response:
                continue

            # Extract Lean code
            try:
                # find the final ```lean and ```
                lean_code = response.split("### Lean Code\n```lean")[-1].split("```")[0].strip()
            except Exception as e:
                if logger:
                    logger.error(f"Failed to extract Lean code: {e}")
                continue

            # Update project structure
            project.set_lean("api", service_name, api_name, lean_code)

            # Try to build
            success, compilation_error = project.build()
            if success:
                if logger:
                    logger.debug(f"Successfully formalized API: {api_name}")
                return True
            else:
                if logger:
                    logger.error(f"Failed to formalize API {api_name}: {compilation_error}")

            # Remove failed code
            project.del_lean("api", service_name, api_name)

            # Update history
            history.extend([
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": response}
            ])

        if logger:
            logger.error(f"Failed to formalize API {api_name} after {self.max_retries} attempts")
        
        return False

    async def run(self, 
                 api_dependency_info: APIFormalizationInfo,
                 logger: Logger = None) -> APIFormalizationInfo:
        """Formalize all APIs in topological order"""
        if not api_dependency_info.api_topological_order:
            raise ValueError("No valid API topological order available")

        result = APIFormalizationInfo(
            project=api_dependency_info.project,
            dependencies=api_dependency_info.dependencies,
            topological_order=api_dependency_info.topological_order,
            formalized_tables=api_dependency_info.formalized_tables,
            api_table_dependencies=api_dependency_info.api_table_dependencies,
            api_dependencies=api_dependency_info.api_dependencies,
            api_topological_order=api_dependency_info.api_topological_order
        )

        for service_name, api_name in api_dependency_info.api_topological_order:
            success = await self.formalize_api(
                project=result.project,
                service_name=service_name,
                api_name=api_name,
                table_deps=result.api_table_dependencies.get(api_name, []),
                api_deps=result.api_dependencies.get(api_name, []),
                logger=logger
            )
            
            if success:
                result.add_formalized_api(api_name)
            else:
                break

        return result 