from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
from logging import Logger

from src.types.project import ProjectStructure, Table, APIFunction, Service, TableProperty, TableTheorem
from src.types.lean_file import LeanTheoremFile
from src.utils.apis.langchain_client import _call_openai_completion_async

class TableTheoremFormalizer:
    """Formalize table properties into Lean 4 theorems"""
    
    ROLE_PROMPT = """You are a formal verification expert specializing in database properties. You excel at converting high-level database invariants into precise mathematical theorems."""

    SYSTEM_PROMPT = """Background:
We need to formalize database properties into Lean 4 theorems that verify how APIs maintain table invariants.

Task:
Convert a table property into a Lean 4 theorem following this structure:
{structure_template}

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
     import Project.Service.API
     import Project.Service.Table
     open Project.Service.API
     open Project.Service.Table
     ```

2. Helper Functions:
   - If you believe the helper function from the API file that you want to use is easy and clear enough so that it is correct and need no more proof, you can import and use it.
   - Or else you should define the helper function in the theorem file.
   - Keep functions small and focused
   - New type definitions should be in the helper_functions field of the file too, if needed
   - Example:
     ```lean
     def isValidState (table : Table) : Bool := ...
     def checkCondition (input : Type) : Bool := ...
     ```

3. Comment:
   - Use the API-specific description as comment
   - Format as a Lean comment
   - Remember to add /- and -/ at the beginning and end of the comment
    
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
            - If you need to show a record is modified, you can check the old one does not exist in the new table and the new one exists in the new table

     - Try not to check all the records of the table one by one, if you have to, make sure the order of the records is the same as the returned table of the API.
        - For example, rows ++ [row'] is not the same as [row'] ++ rows in Lean, but it is the same in the real table, so you need to use the same order in the theorem as the order in returned table of the API
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
- How this API maintains the property
- Specific description for this API
- Key points to verify

### Lean Code
```lean
<complete file content following structure>
```

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
        if api.dependencies.tables:
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
            logger.info(f"Formalizing theorem for table {table.name} with API {dep_api.name}")

        # Initialize empty theorem file
        lean_file = project.init_table_theorem(service.name, table.name, property_id, theorem_id)
            
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
                continue
                
            try:
                # Parse response
                json_str = response.split("```json")[-1].split("```")[0].strip()
                fields = json.loads(json_str)
                assert "description" in fields
            except Exception as e:
                if logger:
                    logger.error(f"Failed to parse response: {e}")
                continue
            
            # Get description out of fields
            description = fields["description"]
            theorem.description = description
            fields = {k: v for k, v in fields.items() if k != "description"}

            # Update theorem file
            project.update_lean_file(lean_file, fields)
            
            # Try compilation
            success, error_message = project.build(parse=True, add_context=True, only_errors=True)
            lean_file_content = lean_file.to_markdown()
            
            if success:
                if logger:
                    logger.info(f"Successfully formalized theorem for table {table.name} with API {dep_api.name}")
                return True
                    
            # Restore on failure
            project.restore_lean_file(lean_file)
                
        # Clean up on failure
        project.delete_table_theorem(service.name, table.name, property_id, theorem_id)
        if logger:
            logger.error(f"Failed to formalize theorem after {self.max_retries} attempts")
        return False

    async def formalize(self,
                       project: ProjectStructure,
                       logger: Optional[Logger] = None) -> ProjectStructure:
        """Formalize all table theorems in the project"""
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
                            break

        return project 