from typing import Dict, List, Optional, Any
from logging import Logger
import json
from pathlib import Path
from src.utils.apis.langchain_client import _call_openai_completion_async
from src.pipeline.theorem.table.theorem_types import TableTheoremGenerationInfo

class DBTheoremFormalizer:
    """Formalize database properties into theorems"""
    
    SYSTEM_PROMPT = """
You are a formal verification expert tasked with formalizing database properties into Lean 4 theorems.

Task:
Convert a database property into Lean 4 theorems, one for each related API.
The property means under a given condition, the database state will change in a certain way, and it is related to a list of APIs, which all obey the same property.

Background:
1. All APIs and tables are formalized in Lean 4
2. All APIs have their theorems formalized
3. Each property should become multiple theorems (one per API)
4. Focus on database state changes, not API return values

Output Format:
1. Analysis Process:
   - Explain how you interpret the property
   - Identify key state changes to verify
   - Note any assumptions or edge cases
   - You should include draft of the full code after analysis, with import prefix and all the old theorems and the new theorems, to make your task easier
   - Look at the old theorems to check if the new property is actually the same as some of the old properties, if so, you can skip the new property, by returning the same import prefix and empty theorems list
2. ### Output
```json
{
    "import_prefix": "<complete import section with all necessary imports and opens>",
    "theorems": [
        "<theorem 1 complete code including comments>",
        "<theorem 2 complete code including comments>",
        ...
    ]
}
```

Requirements:
1. Import Prefix:
   - Include necessary imports and opens
   - Don't repeat any code other than imports/opens
   - Keep existing imports and add new ones if needed
   - Use correct import paths as provided
   - If you want to use some helper functions, you can add them in the import prefix

2. Theorem Code:
   - Each theorem in the list should be complete and independent
   - Include property and API description as comments before the theorem
   - Use 'sorry' for all proofs as you don't need to prove them now
   - Focus on database state changes, that means we don't need to check the response type of the API
   - Don't repeat existing theorems! If you find out the theorem to be written is already in the existing theorems, just skip it, you are allowed to return a empty list if necessary
   It means the property is the same as some properties already formalized
   - Each item in the returned list should be a complete theorem code and also contains only one theorem
"""

    def __init__(self, model: str = "qwen-max", max_retries: int = 5):
        self.model = model
        self.max_retries = max_retries

    def _format_dependencies_prompt(self, info: TableTheoremGenerationInfo, 
                                  table_name: str,
                                  service_name: str,
                                  property_apis: Dict[str, List[str]]) -> str:
        """Format dependencies into a readable prompt"""
        sections = []
        
        # Add current table
        table = info.project._find_table(table_name)
        sections.append(f"Current Table Definition:")
        sections.append(f"Import path: {info.project.get_lean_import_path('table', service_name, table_name)}")
        sections.append("```lean")
        sections.append(table.lean_code)
        sections.append("```\n")
        
        # Add related APIs
        sections.append("Related APIs:")
        for service_name, apis in property_apis.items():
            for api_name in apis:
                api = info.project._find_api(service_name, api_name)
                if api:
                    sections.append(f"\n{service_name}.{api_name}:")
                    sections.append(f"Implementation Import Path: {info.project.get_lean_import_path('api', service_name, api_name)}")
                    sections.append("Implementation:")
                    sections.append("```lean")
                    sections.append(api.lean_code)
                    sections.append("```")
                    
                    if api.lean_test_code:
                        sections.append(f"Theorems Import Path: {info.project.get_test_lean_import_path('api', service_name, api_name)}")
                        sections.append("Theorems:")
                        sections.append("```lean")
                        sections.append(api.lean_test_code)
                        sections.append("```")
        
        return "\n".join(sections)

    def _find_table_service(self, info: TableTheoremGenerationInfo, table_name: str) -> Optional[str]:
        """Find the service that contains the table"""
        for service in info.project.services:
            if any(t.name == table_name for t in service.tables):
                return service.name
        return None

    async def _try_compile(self,
                           service_name: str,
                           table_name: str,
                           code: str,
                           info: TableTheoremGenerationInfo,
                           logger: Optional[Logger] = None) -> bool:
        """Try to compile the theorem code"""
        # Check if current theorem code exists
        current_theorem = info.project.get_test_lean("table", service_name, table_name)

        try:
            info.project.set_test_lean("table", service_name, table_name, code)
            
            # Try to build
            success, message = info.project.build()
            
            if not success:
                if logger:
                    logger.error(f"Compilation failed: {message}")
                # Restore backup if exists
                if current_theorem:
                    info.project.set_test_lean("table", service_name, table_name, current_theorem)
                else:
                    info.project.del_test_lean("table", service_name, table_name)
            return success, message
        except Exception as e:
            if logger:
                logger.error(f"Compilation failed: {e}")
            return False, str(e)

    async def _formalize_property(self,
                                table_name: str,
                                property_info: Dict[str, Any],
                                info: TableTheoremGenerationInfo,
                                logger: Optional[Logger] = None) -> bool:
        """Formalize a single property into theorems"""
        if logger:
            logger.info(f"Formalizing property for table {table_name}: {property_info.property}")
        
        # Find service containing the table
        service_name = self._find_table_service(info, table_name)
        if not service_name:
            if logger:
                logger.error(f"Could not find service for table {table_name}")
            return False
        
        # Initialize history
        history = []
        
        # Format initial prompt
        current_prompt = f"""
Please formalize the following database property into Lean 4 theorems:

Table: {table_name}
Property: {property_info.property}

Current import prefix:
```lean
{info.project.get_test_lean_prefix('table', service_name, table_name) or ''}
```

Current theorems:
Import path: {info.project.get_test_lean_import_path('table', service_name, table_name)}
```lean
{info.project.get_test_lean('table', service_name, table_name) or ''}
```

Dependencies:
{self._format_dependencies_prompt(info, table_name, service_name, property_info.apis)}

Please ensure all import statements use the exact paths provided above.

Make sure you have "### Output\n```json" in your response so that I can parse the output correctly
"""

        for attempt in range(self.max_retries):
            if logger:
                logger.info(f"Attempt {attempt + 1}/{self.max_retries}")
                logger.model_input(current_prompt)
            
            response = await _call_openai_completion_async(
                system_prompt=self.SYSTEM_PROMPT,
                user_prompt=current_prompt,
                history=history,
                model=self.model,
                temperature=0.0
            )
            
            if not response:
                if logger:
                    logger.error("Failed to get model response")
                continue
                
            if logger:
                logger.model_output(response)
            
            try:
                # Parse JSON output
                output_section = response.split("### Output\n```json")[1].split("```")[0]
                output_data = json.loads(output_section)
                prefix = output_data["import_prefix"]
                theorems = output_data["theorems"]

                # Check if the new property is already in the old theorems
                if theorems == []:
                    if logger:
                        logger.warning(f"Property '{property_info.property}' for table '{table_name}' is already formalized")
                    return True
            except Exception as e:
                if logger:
                    logger.error(f"Failed to parse model response: {e}")
                continue
            
            # Combine code
            current_theorems =  info.get_table_theorems(table_name) or []
            full_code = f"{prefix}\n\n{'\n\n'.join(current_theorems)}\n\n{'\n\n'.join(theorems)}"
            
            # Try to compile
            success, error_message = await self._try_compile(
                service_name=service_name,
                table_name=table_name,
                code=full_code,
                info=info,
                logger=logger
            )

            if logger:
                logger.info(f"Compilation result: success={success}, error_message={error_message}")
            
            if success:
                # Update prefix and add theorems
                info.project.set_test_lean_prefix("table", service_name, table_name, prefix)
                for theorem in theorems:
                    if theorem.strip():
                        info.project.add_test_lean_theorem("table", service_name, table_name, theorem.strip())
                return True
            
            # Update history
            history.extend([
                {"role": "user", "content": current_prompt},
                {"role": "assistant", "content": response}
            ])
            
            current_prompt = f"""
Compilation failed with error:
{error_message}

Please fix the Lean code. Make sure to:
1. Address the specific compilation error
2. Maintain the same theorem logic
3. Use correct import paths
4. Follow Lean 4 syntax

You have no right to change the code in the other files, so you must fix the error by yourself, in this single file

Please provide your response in the same format:
1. Analysis of the error and your fixes
2. ### Output
```json
{{
    "import_prefix": "<corrected imports and opens>",
    "theorems": [
        "<corrected theorem 1>",
        "<corrected theorem 2>",
        ...
    ]
}}
```
"""
            
            if logger:
                logger.warning(f"Compilation failed (attempt {attempt + 1}): {error_message}")
        
        if logger:
            logger.error(f"Failed to formalize property after {self.max_retries} attempts")
        
        return False

    async def formalize_table_theorems(self,
                                     table_name: str,
                                     info: TableTheoremGenerationInfo,
                                     logger: Optional[Logger] = None) -> bool:
        """Formalize all properties for a table"""
        if logger:
            logger.info(f"Formalizing theorems for table {table_name}")
        
        # Get properties
        table_properties = []
        for service_properties in info.table_properties.values():
            if table_name in service_properties:
                table_properties.extend(service_properties[table_name])
        
        if not table_properties:
            if logger:
                logger.warning(f"No properties found for table {table_name}")
            return True
        
        success = True
        for property_info in table_properties:
            if not await self._formalize_property(table_name, property_info, info, logger):
                success = False
        
        if success:
            info.add_formalized_theorem_table(table_name)
        
        return success

    async def run(self,
                  info: TableTheoremGenerationInfo,
                  output_path: Path,
                  logger: Optional[Logger] = None) -> TableTheoremGenerationInfo:
        """Run the complete formalization process"""
        if logger:
            logger.info("Starting database theorem formalization")
        
        # Process tables in topological order
        for table_name in info.topological_order:
            # Skip if already formalized
            if info.is_table_theorem_formalized(table_name):
                if logger:
                    logger.info(f"Skipping already formalized table {table_name}")
                continue
            
            # Formalize table
            await self.formalize_table_theorems(table_name, info, logger)
            
            # Save progress
            info.save(output_path)
        
        if logger:
            logger.info("Database theorem formalization completed")
        
        return info 