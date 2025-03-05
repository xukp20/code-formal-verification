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
   - Import table structure
   - Import API implementation
   - Use correct import paths

2. Helper Functions:
   - Define any needed helper functions
   - Keep functions focused and reusable

3. Comment:
   - Use the API-specific description as comment
   - Format as a Lean comment

4. Theorem:
   - Name should reflect the property for this API
   - Include necessary parameters
   - Specify pre and post conditions
   - Use 'sorry' for proof

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
  "description": "API-specific description",
  "imports": "import statements",
  "helper_functions": "helper function definitions",
  "comment": "API-specific description",
  "theorem_unproved": "theorem statement with sorry"
}}
```

Make sure you have "### Output\n```json" in your response so that I can find the Json easily."""

    RETRY_PROMPT = """Compilation failed with error:
{error}

Please fix the Lean code while maintaining the same structure:
{structure_template}

Make sure to:
1. Address the specific compilation error
2. Maintain the same theorem logic
3. Use correct import paths
4. Follow Lean 4 syntax

Return both the corrected code and parsed fields.
Make sure you have "### Output\n```json" in your response."""

    def __init__(self, model: str = "qwen-max", max_retries: int = 3):
        self.model = model
        self.max_retries = max_retries

    @staticmethod
    def _format_dependencies(table: Table, api: APIFunction, project: ProjectStructure) -> str:
        """Format table and API dependencies as markdown"""
        sections = []
        
        # Add table definition
        sections.append(table.to_markdown(show_fields={"lean_structure": True}))
        
        # Add API implementation
        sections.append(api.to_markdown(show_fields={"lean_function": True}))
        
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
        dependencies = self._format_dependencies(table, dep_api, project)
        
        # Prepare prompts
        structure_template = LeanTheoremFile.get_structure(proved=False)
        system_prompt = self.SYSTEM_PROMPT.format(structure_template=structure_template)
        user_prompt = f"""# Property Information
Table: {table.name}
API: {dep_api.name}
Property: {property.description}

# Dependencies
{dependencies}"""

        if logger:
            logger.model_input(f"Theorem formalization prompt:\n{user_prompt}")
            
        # Try formalization with retries
        history = []
        error_message = None

        for attempt in range(self.max_retries):
            if logger:
                logger.info(f"Attempt {attempt + 1}/{self.max_retries}")

            # Backup current state
            lean_file.backup()
                
            # Prepare prompt
            prompt = (self.RETRY_PROMPT.format(
                error=error_message, 
                structure_template=structure_template
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
            fields = {k: v for k, v in fields.items() if k != "description"}

            # Update theorem file
            project.update_lean_file(lean_file, fields)
            
            # Try compilation
            success, error = project.build(parse=True, add_context=True, only_errors=True)
            
            if success:
                if logger:
                    logger.info(f"Successfully formalized theorem for table {table.name} with API {dep_api.name}")
                return True
                    
            # Restore on failure
            project.restore_lean_file(lean_file)
            error_message = error
            history.extend([
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response}
            ])
                
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
                                logger.error(f"Failed to formalize theorem for table {table.name} with API {api.name}")
                            break

        return project 