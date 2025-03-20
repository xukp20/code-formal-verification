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

If you notice any potential formalization issues (e.g., missing return types, incomplete API functionality), you can include a warning section in your response. However, you should still attempt to provide the best possible theorem formalization given the current API implementation.


File Structure Requirements:
1. Imports Section:
   - Import all required APIs and tables from dependencies
   - Use correct import paths based on project structure
   - The open commands for the imported APIs and tables should also be in this part, after all the imports
   - Example:
     ```lean
     import Project.Service.APIs.API1
     import Project.Service.Tables.Table1
     open Project.Service.APIs.API1
     open Project.Service.Tables.Table1
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
   - If the requirement has constraints on the input params, you may consider directly provide the response of the dependent APIs (those called in the current API) of the current API as the premise of the theorem
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
2. Style:
   - Use clear variable names
   - Follow Lean 4 conventions
   - Maintain consistent formatting

Return your response in three parts:

### Analysis
Step-by-step reasoning of your formalization process, following the structure below:

#### Imports
- Analyze what to import and opens so that they can be used in the theorem
- It is common to import all the imports and opens in the API file, and also import and open the API itself in the theorem file

#### Inputs 
- First, read the implementation of the API function, you need to include all the inputs of the API function as variables in the theorem

#### Analyze the requirement
- First, read the natural language requirement to split it into several structured parts:
1. What are the conditions?
    - What are the restrictions on the input parameters?
    - What are the restrictions on the dependent APIs given the input params? Like the response of the dependent APIs given the current input params
    - What are the restrictions on the table states? Like the existence or non-existence of specific records in the table given the input params
    - How are these restrictions related together?
2. What are the inputs?
    - Do we need anymore inputs except the input parameters we have already included?
3. What is the output?
    - There is a function call to the given API, and the requirement should be related to the output of the function call
    - What is the output type of the function call?
    - If the type includes some value, what is the value?
    - If any table is returned, what is the table? This should be considered by comparing it to the old table state, to find any record updated, added or deleted, or table not changed

#### Conditions and hypotheses
- Using the conditions we have analyzed, determine one by one how they can be written as hypotheses in Lean:
1. First, determine if the condition is complicated and needs to use a helper function to represent it
2. If so, look for any existing helper functions that can do the job in the implementation of the API function. If you can't find any, create a new one.
    - Try your best to reuse the existing helper functions, instead of creating new ones, so that we can get concise and clear theorems
    - But remember to go through the chosen helper function to make sure it is correct and do what you want
    - If so, never create a new helper function that applys an exactly same logic as the existing helper functions, which may cause difficulty for the prover
3. If the condition is simple, you can write it directly as a hypothesis
4. Write this single part of the condition as a hypothesis in Lean
    - If you find the implementation of the API file missing some essential parts that you need to formalize the condition, you should consider it as a potential bug, which will be presented in the ### Warning section later. But you should still try your best to formalize the theorem based on the information you have.
        - For example, if the implementation of the API file has no API call to a `checkValid` API, but the requirement describes that the input params should be checked by the `checkValid` API, you should point it out here, but try to find the closest way to formalize the condition.
5. Repeat the above steps until all the conditions are written as hypotheses

#### Conclusion
- Using the requirements on the output of the API function, determine the conclusion of the theorem
1. First, break the requirement into several parts, like the output type, value and the state of the table
2. Then, try to formalize each part into a statement in Lean. Like the conditions, determine if you need to use an existing helper function or create a new one, or just write it directly
    - If you find the implementation of the API file missing some essential parts that you need to formalize the theorem, you should consider it as a potential bug, which will be presented in the ### Warning section later. But you should still try your best to formalize the theorem based on the information you have.
        - For example, if the return type of the API has no "NoPermissionError" type, but the requirement describes that the output type should be no permission error, you should point it out here, but try to find the closest type you can use to represent the requirement.
    - If you find some dependent APIs explained in the requirement is not given or not used in the implementation of the API function, you should point it out here, but try to find the closest way to formalize the requirement. Mark it as a potential bug.
    - Consider how to formalize the table state changes in the conclusion: Use new record, removed record or updated record. Or if you really need to check the whole table, make sure the new record is added to the end of the list.
3. Repeat the above steps until all the parts are written as statements in Lean
4. Combine all the statements into a single conclusion, you may need to use the logic of `and`, `or`, `not`, `implies` and `iff` to combine them. Write the logic notations in Lean.

#### Summary 
In this part, you should go through the analysis above to:
- Repeat the original requirement as comment here, so that you will make sure the requirement is not changed
- Construct the final theorem statement, the proof should be `sorry`
- Collect all the potential warnings here
    - Missing return types in API functions, which may lead to theorem statement not equal to the requirement
    - Missing dependent APIs in the implementation of the API function, which may lead to theorem statement not equal to the requirement

After these steps, you should have a complete theorem statement. Now put it in the ### Lean Code:


### Lean Code
```lean
<complete file content following the structure template>
```

### Warning 
(Optional)
If you notice any potential formalization issues that prevent you from writing a theorem statement, describe them here, with a title of "### Warning". For example:
- Missing return types in API functions, which may lead to theorem statement not equal to the requirement
- Missing dependent APIs in the implementation of the API function, which may lead to theorem statement not equal to the requirement
If you notice some issues but that doesn't lead to compilation errors, you should not include this section and try to do the formalization with the given formalization.
Don't include this section in the output json.
- If there is no warning, put a single word "None" for this part, without any other words

### Output  
```json
{{
  "imports": "string of import statements and open commands",
  "helper_functions": "string of helper function definitions or type definitions",
  "comment": "/- string of original requirement as comment, must not be modified, write as a Lean comment -/",
  "theorem_unproved": "string of theorem statement with sorry"
}}
```

Important:
- Use original requirement as comment
- Make theorem specific and precise
- Use sorry for proofs
- New records should be added to the end of the list of the table

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
- New records should be added to the end of the list of the table

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

Make sure you have "### Output\n```json" in your response so that I can find the Json easily.
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
                warning_text = self._parse_warning(response)
                if warning_text and logger:
                    logger.warning(f"Formalization warning for {api.name} theorem {theorem_id}:\n[{theorem.description}]\n{warning_text}")
                
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