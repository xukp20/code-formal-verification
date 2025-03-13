from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
import json
from logging import Logger
import asyncio

from src.types.project import ProjectStructure, Service, APIFunction, APITheorem
from src.types.lean_file import LeanTheoremFile
from src.utils.apis.langchain_client import _call_openai_completion_async

class APITheoremFormalizer:
    """Formalize API theorems into Lean 4 code"""
    
    ROLE_PROMPT = """You are a theorem formalizer for Lean 4 code, specializing in converting API requirements into formal theorems. You excel at creating precise mathematical representations of API behaviors while maintaining semantic correctness."""

#    - If you believe the helper function from the API file that you want to use is easy and clear enough so that it is correct and need no more proof, you can import and use it.
#    - Or else you should define the helper function in the theorem file.

    SYSTEM_PROMPT = """Background:
We need to formalize API requirements into Lean 4 theorems that verify API behavior.

Code Structure:
- APIs are implemented as Lean 4 functions
- Database tables are Lean 4 structures
- Each theorem verifies one specific requirement
- Use 'sorry' for all proofs

Task:
Convert an API requirement into a formal Lean 4 theorem following this structure:
{structure_template}

File Structure Requirements:
1. Imports Section:
   - Import all required APIs and tables from dependencies
   - Use correct import paths based on project structure
   - The open commands for the imported APIs and tables should also be in this part, after all the imports
   - Example:
     ```lean
     import Project.Service.API
     import Project.Service.Table
     open Project.Service.API
     open Project.Service.Table
     ```

2. Helper Functions:
   - Try to use existing helper functions in the API file as much as possible
   - Add new helper functions only if none of the existing ones can do the same job or you don't trust the existing ones to be correct
   - Keep functions small and focused
   - New type definitions should be in the helper_functions field of the file too, if needed
   - Example:
     ```lean
     def isValidState (table : Table) : Bool := ...
     def checkCondition (input : Type) : Bool := ...
     ```

3. Comment:
   - Use the original requirement text
   - Format as a Lean comment
   - Remember to add /- and -/ at the beginning and end of the comment
   - Example:
     ```lean
     /- If the user exists, the operation should fail and return an error -/
     ```

4. Theorem:
    Name:
   - Name should reflect the property being verified

   Inputs:
   - Include all necessary parameters

   Conditions and hypotheses:
   - Specify pre and post conditions

   Input constraints and dependent API responses:
   - If the requirement has constraints on the input params, you may consider directly provide the response of the dependent APIs (those called in the API) of the current API as the premise of the theorem
    - For example, if the requirement says `if the user and password is valid` and the current API depends on a `checkValid` API, you can directly write one of the hypothesis as `h_checkValid : checkValid user password = <some success type from that API>`
    - By doing this, we can separate the correctness of the current API from the correctness of the dependent APIs, and we can prove the current API's correctness by assuming the correctness of the dependent APIs
   - If the responses of the dependent APIs are directly provided in the requirement, you MUST use them as the premise of the theorem, instead of breaking them down into lower level hypotheses
    - For example, if the requirement says `if the user and password is valid` and the current API calls a `checkValid` API to implement the logic. If `valid` actually means this record is in the table, which is also what the `checkValid` API does, you must use the response of the `checkValid` API as the premise of the theorem, instead of writing a hypothesis like `h_record_in_table : table.rows.any (fun row => row.phone_number == phoneNumber ∧ row.password = password)`, because the `checkValid` API is what we trust to be correct

    Table changes:
   - If the output state involved table changes: 
     - Explain it as the addition, deletion, modification or existence of specific records in the table, or the difference between the original table state and the new table state.
        - For example:
            - If you need to show a new record is added, you can check: table.rows.any (fun row => row.phone_number == phoneNumber ∧ row.password = password)
            - If you need to show a record is not in the table, you can check: ¬ table.rows.any (fun row => row.phone_number == phoneNumber ∧ row.password = password)

     - Try not to check all the records of the table one by one, if you have to, make sure the order of the records is the same as the returned table of the API.
        - Order of records: Since in the structure of the Table we use a list of records to represent the table content which is actually a set, you should always add the new record to the end of the list if needed.
        - Which means you should always use rows ++ [row'] instead of [row'] ++ rows in the theorem if the returned table has some new records appended to the original table.
    
    Proof:
   - Use 'sorry' for the proof
   - The theorem should be structured that each parameter, hypothesis, and conclusion should be clearly defined.
   - Example:
     ```lean
    theorem userRegisterSuccessWhenNotExists
        (phoneNumber : String)
        (password : String)
        (old_user_table : UserTable)
        (h_not_exists : ¬ old_user_table.rows.any (fun row => row.phone_number == phoneNumber)) :
        let (result, new_user_table) := userRegister phoneNumber password old_user_table;
        result = RegistrationResult.Success ∧
        new_user_table.rows = {{ phone_number := phoneNumber, password := password }} :: old_user_table.rows := by
        sorry
     ```
     
Hints:
1. State Management:
   - Track database state changes
   - Consider old vs new states
   - Handle all possible outcomes
2. Style:
   - Use clear variable names
   - Add helpful comments
   - Follow Lean 4 conventions
   - Maintain consistent formatting
3. Common Patterns:
   - For validation checks, include the conditions in theorem assumptions
   - For state changes, specify the relationship between old and new states
   - For error cases, ensure they're properly represented in the theorem


Return your response in three parts:
### Analysis
Step-by-step reasoning of your formalization process

### Lean Code
```lean
<complete file content following the structure template>
```

### Output  
```json
{{
  "imports": "string of import statements and open commands",
  "helper_functions": "string of helper function definitions or type definitions",
  "comment": "/- string of original requirement as comment, write as a Lean comment -/",
  "theorem_unproved": "string of theorem statement with sorry"
}}
```

Important:
- Follow file structure exactly
- Include all necessary imports
- Define required helper functions
- Use original requirement as comment
- Make theorem specific and precise
- Use sorry for proofs
- Try not to define new helper functions if you can use the existing ones

Make sure you have "### Output\n```json" in your response so that I can find the Json easily."""

    RETRY_PROMPT = """
Lean theorem file content created from your previous response:
{lean_file}

Compilation failed with error:
{error}

Please fix the Lean code while maintaining the same structure:
{structure_template}

Make sure to:
1. Address the specific compilation error
2. Maintain the same theorem logic
3. Use correct import paths
4. Follow Lean 4 syntax

Hints:
- Remember to add open commands to your imports to open the imported namespace after imports, these open commands should be in the imports field of the json
- All the newly defined helper functions and types should be in the helper_functions field of the json

Return both the corrected code and parsed fields.
Make sure you have "### Output\n```json" in your response so that I can find the Json easily."""

    def __init__(self, model: str = "qwen-max-latest", max_retries: int = 3):
        self.model = model
        self.max_retries = max_retries

    @staticmethod
    def _format_dependencies(api: APIFunction, project: ProjectStructure) -> str:
        """Format API dependencies as markdown"""
        lines = []
        
        # Format API dependencies
        if api.dependencies.apis:
            lines.append("# Dependent APIs")
            for dep_service_name, dep_api_name in api.dependencies.apis:
                dep_api = project.get_api(dep_service_name, dep_api_name)
                if dep_api:
                    lines.extend([
                        f"\n## {dep_service_name}.{dep_api_name}",
                        dep_api.to_markdown(show_fields={"lean_function": True, "doc": True})
                    ])
                    
        # Format table dependencies
        if api.dependencies.tables:
            lines.append("\n# Dependent Tables")
            for table_name in api.dependencies.tables:
                for service in project.services:
                    table = project.get_table(service.name, table_name)
                    if table:
                        lines.extend([
                            table.to_markdown(show_fields={"lean_structure": True})
                        ])
                        break
                        
        return "\n".join(lines)

    async def formalize_theorem(self,
                              project: ProjectStructure,
                              service: Service,
                              api: APIFunction,
                              theorem: APITheorem,
                              theorem_id: int,
                              logger: Optional[Logger] = None) -> bool:
        """Formalize a single API theorem"""
        if logger:
            logger.info(f"Formalizing theorem for {service.name}.{api.name}: {theorem.description}")

        # Initialize empty theorem file with lock
        await project.acquire_lock()
        lean_file = project.init_api_theorem(service.name, api.name, theorem_id)
        project.release_lock()
            
        if not lean_file:
            if logger:
                logger.error(f"Failed to initialize theorem file for {api.name}")
            return False

        # Format dependencies
        dependencies = self._format_dependencies(api, project)
        
        # Prepare prompts
        structure_template = LeanTheoremFile.get_structure(proved=False)
        system_prompt = self.SYSTEM_PROMPT.format(structure_template=structure_template)
        user_prompt = f"""
# Dependencies
{dependencies}

# API Information
Service: {service.name}

{api.to_markdown(show_fields={"lean_function": True})}

# Requirement to Formalize
{theorem.description}
"""

        if logger:
            logger.model_input(f"Theorem formalization prompt:\n{user_prompt}")
            
        # Try formalization with retries
        history = []
        error_message = None
        lean_file_content = None
        
        for attempt in range(self.max_retries):
            if logger:
                logger.info(f"Attempt {attempt + 1}/{self.max_retries}")

            # Backup current state
            lean_file.backup()
                
            # Prepare prompt
            prompt = (self.RETRY_PROMPT.format(
                error=error_message, 
                structure_template=structure_template,
                lean_file=lean_file_content
            ) if attempt > 0 else system_prompt + "\n\n" + user_prompt)
                
            if logger:
                logger.model_input(f"Theorem formalization prompt:\n{prompt}")

            # Call LLM
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
                logger.model_output(f"Theorem formalization response:\n{response}")
                
            if not response:
                await project.acquire_lock()
                project.restore_lean_file(lean_file)
                project.release_lock()
                error_message = "Failed to get LLM response"
                continue
                
            try:
                # Parse response
                json_str = response.split("```json")[-1].split("```")[0].strip()
                fields = json.loads(json_str)
            except Exception as e:
                if logger:
                    logger.error(f"Failed to process response: {e}")
                error_message = str(e)
                await project.acquire_lock()
                project.restore_lean_file(lean_file)
                project.release_lock()
                continue

            # Update and build with lock
            await project.acquire_lock()
            try:
                # Update theorem file
                project.update_lean_file(lean_file, fields)
                
                # Try compilation
                success, error_message = project.build(parse=True, add_context=True, only_errors=True)
                if success:
                    if logger:
                        logger.info(f"Successfully formalized theorem for {api.name}")
                    project.release_lock()
                    return True
                    
                # Restore on failure
                lean_file_content = lean_file.to_markdown()
                project.restore_lean_file(lean_file)
            finally:
                project.release_lock()
                
        # Clean up on failure with lock
        await project.acquire_lock()
        project.delete_api_theorem(service.name, api.name, theorem_id)
        project.release_lock()
        
        if logger:
            logger.error(f"Failed to formalize theorem after {self.max_retries} attempts")
        return False

    async def _formalize_parallel(self,
                                project: ProjectStructure,
                                logger: Optional[Logger] = None,
                                max_workers: int = 1) -> ProjectStructure:
        """Formalize API theorems in parallel"""
        if logger:
            logger.info(f"Formalizing API theorems in parallel for project: {project.name}")

        # Initialize tracking sets
        pending_apis = {(service.name, api.name) 
                       for service in project.services 
                       for api in service.apis}
        completed_apis = set()

        # Create semaphore to limit concurrent tasks
        sem = asyncio.Semaphore(max_workers)

        async def process_theorem(service: Service, api: APIFunction, 
                                theorem: APITheorem, theorem_id: int) -> None:
            """Process a single theorem"""
            if logger:
                logger.info(f"Processing theorem {theorem_id} for API: {api.name}")
            
            success = await self.formalize_theorem(
                project=project,
                service=service,
                api=api,
                theorem=theorem,
                theorem_id=theorem_id,
                logger=logger
            )
            
            if not success and logger:
                logger.error(f"Failed to formalize theorem {theorem_id} for API: {api.name}")

        async def process_with_semaphore(service: Service, api: APIFunction, 
                                       theorem: APITheorem, theorem_id: int):
            async with sem:
                await process_theorem(service, api, theorem, theorem_id)

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

            # Create tasks for all theorems of ready APIs
            tasks = []
            for service_name, api_name in ready_apis:
                service = project.get_service(service_name)
                api = project.get_api(service_name, api_name)
                if not service or not api:
                    continue
                
                if not api.theorems:
                    if logger:
                        logger.warning(f"No theorems to formalize for API: {api.name}")
                    continue

                # Add all theorems from this API to tasks
                for theorem_id, theorem in enumerate(api.theorems):
                    tasks.append(process_with_semaphore(service, api, theorem, theorem_id))

            # Process all theorems in parallel and wait for completion
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            # Update pending and completed sets
            pending_apis -= ready_apis
            completed_apis.update(ready_apis)

            if logger:
                logger.info(f"Completed processing APIs: {', '.join(f'{s}.{a}' for s,a in ready_apis)}")

        return project

    async def formalize(self,
                       project: ProjectStructure,
                       logger: Optional[Logger] = None,
                       max_workers: int = 1) -> ProjectStructure:
        """Formalize all API theorems in the project"""
        if not project.api_topological_order:
            if logger:
                logger.warning("No API topological order available, skipping formalization")
            return project

        if max_workers > 1:
            return await self._formalize_parallel(project, logger, max_workers)
            
        # Original sequential logic
        if logger:
            logger.info(f"Formalizing API theorems for project: {project.name}")
            
        for service_name, api_name in project.api_topological_order:
            service = project.get_service(service_name)
            if not service:
                continue
            api = project.get_api(service_name, api_name)
            if not api:
                continue
            if logger:
                logger.info(f"Processing API: {api.name}")
                    
            if not api.theorems:
                if logger:
                    logger.warning(f"No theorems to formalize for API: {api.name}")
                continue
                
            for id, theorem in enumerate(api.theorems):
                success = await self.formalize_theorem(
                    project=project,
                    service=service,
                    api=api,
                    theorem=theorem,
                    theorem_id=id,
                    logger=logger
                )
                
                if not success:
                    if logger:
                        logger.error(f"Failed to formalize theorem for API: {api.name}")

        return project 