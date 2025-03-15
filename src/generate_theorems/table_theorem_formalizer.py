from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
from logging import Logger
import asyncio

from src.types.project import ProjectStructure, Table, APIFunction, Service, TableProperty, TableTheorem
from src.types.lean_file import LeanTheoremFile
from src.utils.apis.langchain_client import _call_openai_completion_async

class TableTheoremFormalizer:
    """Formalize table properties into Lean 4 theorems"""
    
    ROLE_PROMPT = """You are a formal verification expert specializing in database properties. You excel at converting high-level database invariants into precise mathematical theorems."""

    SYSTEM_PROMPT = """Background:
We need to formalize database properties into Lean 4 theorems that verify how APIs maintain table invariants.

Code Structure:
- APIs are implemented as Lean 4 functions
- Database tables are Lean 4 structures
- Each theorem verifies the property of the table after one of the APIs that maintain the property is called
- Use 'sorry' for all proofs

Task:
Convert a table property into a Lean 4 theorem following this structure:
{structure_template}


If you notice any potential formalization issues (e.g., missing return types, incomplete API functionality), you can include a warning section in your response. However, you should still attempt to provide the best possible theorem formalization given the current API implementation.

First, analyze the property to create a specific description for the current API:
1. Focus on how this specific API maintains the property
2. Describe the pre and post conditions for this API
3. Specify what remains invariant after the API operation

Then, formalize this specific description into a Lean 4 theorem that:
1. Uses the table's structure definition
2. References the API's implementation
3. Specifies state changes precisely
4. Uses 'sorry' for the proof

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
   - Use 'sorry' for proof
   - The theorem should be structured that each parameter, hypothesis, and conclusion should be clearly defined.
   - Example:
    ```lean
    theorem userRegisterPreservesUniquePhoneNumbers
        (phoneNumber : String)
        (password : String)
        (old_user_table : UserTable)
        (h_unique_initially : hasUniquePhoneNumbers old_user_table) :
        let (result, new_user_table) := userRegister phoneNumber password old_user_table;
        hasUniquePhoneNumbers new_user_table := by
    sorry
    ```

Return your response in three parts:

### Analysis
Step-by-step reasoning of your formalization process, following the structure below:

#### Write the theorem description
- First, read the property description to understand what the property is
- Then, analyze the API implementation to understand how the API maintains the property
    - Since this theorem is related to the table, we only check the table changes, not the API output
- Then, write the theorem description based on the property and the API implementation in natural language

#### Imports
- Analyze what to import and opens so that they can be used in the theorem
- It is common to import all the imports and opens in the API file, and also import and open the table file in the theorem file

#### Inputs
- First, read the implementation of the API function, you need to include all the inputs of the API function as variables in the theorem as that you can call the API function later in the theorem

#### Analyze the requirement
- First, read the natural language description of the theorem to split it into several structured parts:
1. What are the conditions?
    - What are the restrictions on the input parameters?
    - What are the restrictions on the dependent APIs given the input params? Like the response of the dependent APIs given the current input params
    - What are the restrictions on the table states? Like the existence or non-existence of specific records in the table given the input params
    - How are these restrictions related together?
2. What are the inputs?
    - Do we need anymore inputs except the input parameters we have already included?
3. What is the output?
    - Since we want to examine the table state changes using this theorem, you need to pay much attention to the returned table.
        - This should be considered by comparing it to the old table state, to find any record updated, added or deleted, or table not changed
    - Determine if we need to consider the output type of the API function.
        - As the table change is what we care about, the output type of the API function is mostly ignored and needs not to be check.
        - But there maybe some cases that the output type is necessary to be checked, so decide it based on the theorem description

#### Conditions and hypotheses
- Using the conditions we have analyzed, determine one by one how they can be written as hypotheses in Lean:
1. First, determine if the condition is complicated and needs to use a helper function to represent it
2. If so, look for any existing helper functions that can do the job in the implementation of the API function. If you can't find any, create a new one.
3. If the condition is simple, you can write it directly as a hypothesis
4. Write this single part of the condition as a hypothesis in Lean
    - If you find the implementation of the API file missing some essential parts that you need to formalize the condition, you should consider it as a potential bug, which will be presented in the ### Warning section later. But you should still try your best to formalize the theorem based on the information you have.
        - For example, if the implementation of the API file has no API call to a `checkValid` API, but the requirement describes that the input params should be checked by the `checkValid` API, you should point it out here, but try to find the closest way to formalize the condition.
5. Repeat the above steps until all the conditions are written as hypotheses

#### Conclusion
- Using the requirements on the output of the API function, determine the conclusion of the theorem
1. First, break the requirement into several parts, like the output type, value and the state of the table
2. Then, try to formalize each part into a statement in Lean. Like the conditions, determine if you need to use an existing helper function or create a new one, or just write it directly
3. Repeat the above steps until all the parts are written as statements in Lean
4. Combine all the statements into a single conclusion, you may need to use the logic of `and`, `or`, `not`, `implies` and `iff` to combine them. Write the logic notations in Lean.

#### Summary 
In this part, you should go through the analysis above to:
- Construct the final theorem statement, the proof should be `sorry`
- Collect all the potential warnings here

After these steps, you should have a complete theorem statement. Now put it in the ### Lean Code:

### Lean Code
```lean
<complete file content following structure>
```

### Warning 
(Optional)
If you notice any potential formalization issues that prevent you from writing a theorem statement, describe them here, with a title of "### Warning". For example:
- Missing return types in API functions
If you notice some issues but that doesn't lead to compilation errors, you should not include this section and try to do the formalization with the given formalization.
Don't include this section in the output json.
! If not any warning, just don't add this title and content. Please don't put this section with a content saying "There is no warning" which will be considered as a fake warning.

### Output
```json
{{
  "description": "string of API-specific description",
  "imports": "string of import statements and open commands",
  "helper_functions": "string of helper function definitions or extra type definitions",
  "comment": "/- string of API-specific description as comment, write as a Lean comment -/",
  "theorem_unproved": "string of theorem statement with sorry"
}}
```

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
Make sure you have "### Output\n```json" in your response."""

    def __init__(self, model: str = "qwen-max", max_retries: int = 3):
        self.model = model
        self.max_retries = max_retries

    @staticmethod
    def _format_dependencies(service: Service, table: Table, api: APIFunction, project: ProjectStructure) -> str:
        """Format table and API dependencies as markdown"""
        sections = []
        
        # Add table definition
        sections.append(f"# Current Table")
        sections.append(table.to_markdown(show_fields={"lean_structure": True}))
        
        # Add API implementation
        sections.append(f"# Current API")
        sections.append(api.to_markdown(show_fields={"lean_function": True}))
        
        # Add API's dependent APIs
        if api.dependencies.apis:
            sections.append("\n# Dependent APIs of the current API")
            for dep_service_name, dep_api_name in api.dependencies.apis:
                dep_api = project.get_api(dep_service_name, dep_api_name)
                if dep_api:
                    sections.extend([
                        f"\n## {dep_service_name}.{dep_api_name}",
                        dep_api.to_markdown(show_fields={"lean_function": True, "doc": True})
                    ])
        
        # Add API's dependent tables
        if api.dependencies.tables and api.dependencies.tables != [table.name]:
            sections.append("\n# Dependent Tables of the current API")
            for table_name in api.dependencies.tables:
                dep_table = project.get_table(service.name, table_name)
                if dep_table and dep_table.name != table.name:
                    sections.extend([
                        dep_table.to_markdown(show_fields={"lean_structure": True})
                    ])
        
        return "\n".join(sections)

    async def formalize_theorem(self,
                              project: ProjectStructure,
                              service: Service,
                              table: Table,
                              property: TableProperty,
                              property_id: int,
                              theorem: TableTheorem,
                              theorem_id: int,
                              logger: Optional[Logger] = None) -> bool:
        """Formalize a single table theorem"""
        dep_api = project.get_api(service.name, theorem.api_name)
        if logger:
            logger.info(f"Formalizing theorem for table {table.name} with API {theorem.api_name}")

        # Initialize empty theorem file with lock
        await project.acquire_lock()
        lean_file = project.init_table_theorem(service.name, table.name, property_id, theorem_id)
        project.release_lock()
            
        if not lean_file:
            if logger:
                logger.error(f"Failed to initialize theorem file for table {table.name}")
            return False

        # Format dependencies
        dependencies = self._format_dependencies(service, table, dep_api, project)
        
        # Prepare prompts
        structure_template = LeanTheoremFile.get_structure(proved=False)
        system_prompt = self.SYSTEM_PROMPT.format(structure_template=structure_template)
        user_prompt = f"""# Property Information
Table: {table.name}
API: {dep_api.name}
Property: {property.description}

{dependencies}"""

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
                assert "description" in fields
            except Exception as e:
                if logger:
                    logger.error(f"Failed to parse response: {e}")
                error_message = str(e)
                await project.acquire_lock()
                project.restore_lean_file(lean_file)
                project.release_lock()
                continue
            
            # Get description out of fields
            description = fields["description"]
            theorem.description = description
            fields = {k: v for k, v in fields.items() if k != "description"}

            # Update and build with lock
            await project.acquire_lock()
            try:
                # Update theorem file
                project.update_lean_file(lean_file, fields)
                
                # Try compilation
                success, error_message = project.build(parse=True, add_context=True, only_errors=True)
                if success:
                    if logger:
                        logger.info(f"Successfully formalized theorem for table {table.name}")
                    project.release_lock()
                    return True
                    
                # Restore on failure
                lean_file_content = lean_file.to_markdown()
                project.restore_lean_file(lean_file)
            finally:
                project.release_lock()
                
        # Clean up on failure with lock
        await project.acquire_lock()
        project.delete_table_theorem(service.name, table.name, property_id, theorem_id)
        project.release_lock()
        
        if logger:
            logger.error(f"Failed to formalize theorem after {self.max_retries} attempts")
        return False

    async def _formalize_parallel(self,
                                project: ProjectStructure,
                                logger: Optional[Logger] = None,
                                max_workers: int = 1) -> ProjectStructure:
        """Formalize table theorems in parallel"""
        if logger:
            logger.info(f"Formalizing table theorems in parallel for project: {project.name}")

        # Create tasks for each theorem
        tasks = []
        for service in project.services:
            for table in service.tables:
                if not table.properties:
                    continue
                    
                for property_id, property in enumerate(table.properties):
                    for theorem_id, theorem in enumerate(property.theorems):
                        tasks.append((service, table, property, property_id, theorem, theorem_id))

        # Create semaphore to limit concurrent tasks
        sem = asyncio.Semaphore(max_workers)

        async def process_theorem(task):
            service, table, property, property_id, theorem, theorem_id = task
            return await self.formalize_theorem(
                project=project,
                service=service,
                table=table,
                property=property,
                property_id=property_id,
                theorem=theorem,
                theorem_id=theorem_id,
                logger=logger
            )

        async def process_with_semaphore(task):
            async with sem:
                return await process_theorem(task)

        # Process all theorems in parallel
        results = await asyncio.gather(*[process_with_semaphore(task) for task in tasks])

        # Check for failures
        if not all(results):
            if logger:
                logger.error("Some theorems failed to formalize")

        return project

    async def formalize(self,
                       project: ProjectStructure,
                       logger: Optional[Logger] = None,
                       max_workers: int = 1) -> ProjectStructure:
        """Formalize all table theorems in the project"""
        if max_workers > 1:
            return await self._formalize_parallel(project, logger, max_workers)
            
        # Original sequential logic
        if logger:
            logger.info(f"Formalizing table theorems for project: {project.name}")
            
        for service in project.services:
            if logger:
                logger.info(f"Processing service: {service.name}")
                
            for table in service.tables:
                if logger:
                    logger.info(f"Processing table: {table.name}")
                    
                if not table.properties:
                    if logger:
                        logger.warning(f"No properties to formalize for table: {table.name}")
                    continue
                    
                for property_id, property in enumerate(table.properties):
                    for theorem_id, theorem in enumerate(property.theorems):
                        success = await self.formalize_theorem(
                            project=project,
                            service=service,
                            table=table,
                            property=property,
                            property_id=property_id,
                            theorem=theorem,
                            theorem_id=theorem_id,
                            logger=logger
                        )
                        
                        if not success:
                            if logger:
                                logger.error(f"Failed to formalize theorem for table {table.name}")

        return project 