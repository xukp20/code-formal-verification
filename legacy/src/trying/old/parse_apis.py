import argparse
import json
import os
from typing import Dict, List, Optional
from pydantic import BaseModel
from src.utils.apis.langchain_client import _call_openai_completion
from src.trying.parse_db_operations import ServiceMethod, Parameter, MethodList
from langchain_core.output_parsers import PydanticOutputParser

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="deepseek-r1")
    parser.add_argument("--scala_path", type=str, default="source_code/register")
    parser.add_argument("--init_impl_file", type=str, default="Process/Init.scala")
    parser.add_argument("--apis_dir", type=str, default="Impl")
    parser.add_argument("--output_dir", type=str, default="outputs/")
    parser.add_argument("--db_operations_file", type=str, default="db_operations.json")
    parser.add_argument("--output_file", type=str, default="apis.json")
    return parser.parse_args()


class DBEffect(BaseModel):
    read: bool
    write: bool
    logic: str


class SideEffects(BaseModel):
    db: Optional[DBEffect] = None


class API(BaseModel):
    name: str
    main_code: str
    dependencies: List[str]
    parameters: List[Parameter]
    returns: List[Parameter]
    logic: str
    side_effects: SideEffects

    def to_markdown(self) -> str:
        """
        Converts the API instance into a markdown formatted string.

        Returns:
            str: Markdown formatted representation of the API
        """
        # Format parameters
        param_str = "\n".join([
            f"- **{p.name}** ({p.type}): {p.description}"
            for p in self.parameters
        ])

        # Format returns
        returns_str = "\n".join([
            f"- **{r.name}** ({r.type}): {r.description}"
            for r in self.returns
        ])

        # Format side effects
        side_effects_str = "\n".join([
            f"### {k}\n"
            f"**Read**: {self.side_effects.model_dump()[k]['read']}\n"
            f"**Write**: {self.side_effects.model_dump()[k]['write']}\n"
            f"**Logic**: {self.side_effects.model_dump()[k]['logic']}\n"
            for k in self.side_effects.model_dump().keys()
        ])

        # Build the markdown string
        markdown = f"""
# {self.name}

## Main Code:
{self.main_code}

## Dependencies:
{self.dependencies}

## Parameters:
{param_str if self.parameters else "- None"}

## Returns:
{returns_str if self.returns else "- None"}

## Logic:
{self.logic}

## Side Effects:
{side_effects_str if self.side_effects else "- None"}
"""
        return markdown.strip()
    

class APIParser:
    def __init__(self, model: str, db_operations: List[ServiceMethod]):
        self.model = model
        self.db_operations = db_operations
        self.output_parser = PydanticOutputParser(pydantic_object=API)

    def parse(self, file_name: str, code_content: str) -> API:
        # Format DB operations into markdown
        db_operations_md = "\n\n".join(op.to_markdown() for op in self.db_operations)
        
        system_prompt = """
        You are a code analyzer that extracts API information from Scala code.
        Analyze the provided Scala file which contains either a Planner class (API) or Init implementation.
        
        Extract the following information:
        1. Name: The class name (xxxPlanner) or "Init"
        2. Main Code: The main code of the file, which should be the method of the class that contains the logic of the API, please retrieve the entire method definition and the entire body of the method
        3. Dependencies: Any database operations used from the provided list
        4. Parameters: Input parameters with name, type, and description
        5. Returns: Output values with name, type, and description
        6. Logic: Detailed explanation of the API's logic
        7. Side Effects on Database:
           - Whether it reads from the database
           - Whether it writes to the database
           - Detailed logic of database operations
        
        Available database operations:

{db_operations_md}
        
        Output in JSON format:
        ```
        {
            "name": "APIName",
            "main_code": "copy the main_code of the main method, full code not changed",
            "dependencies": ["db_op1", "db_op2"],
            "parameters": [
                {
                    "name": "param_name",
                    "type": "param_type",
                    "description": "param_description"
                }
            ],
            "returns": [
                {
                    "name": "return_name",
                    "type": "return_type",
                    "description": "return_description"
                }
            ],
            "logic": "detailed_explanation",
            "side_effects": {
                "db": {
                    "read": true/false,
                    "write": true/false,
                    "logic": "detailed_db_logic"
                }
            }
        }
        ```
        """.replace("{db_operations_md}", db_operations_md)
        
        user_prompt = f"File name: {file_name}\n\nAnalyze this Scala code:\n\n{code_content}"
        
        response = _call_openai_completion(
            model=self.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.0
        )
        
        try:
            return self.output_parser.parse(response)
        except Exception as e:
            raise ValueError(f"Failed to parse LLM response into API: {str(e)}")


def load_db_operations(output_dir: str, db_operations_file: str) -> List[ServiceMethod]:
    """Load and parse DB operations from the JSON file into ServiceMethod objects"""
    with open(os.path.join(output_dir, db_operations_file), 'r') as f:
        data = json.load(f)
        method_list = MethodList.model_validate(data)
        return method_list.methods


def save_apis(apis: List[API], output_dir: str, output_file: str):
    """Save parsed APIs to JSON file"""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    with open(os.path.join(output_dir, output_file), 'w') as f:
        json.dump([api.model_dump() for api in apis], f, indent=2)


def main():
    args = parse_args()
    
    # Load DB operations
    db_operations = load_db_operations(args.output_dir, args.db_operations_file)
    
    # Initialize parser
    parser = APIParser(args.model, db_operations)
    apis = []
    
    # Parse Init implementation
    init_path = os.path.join(args.scala_path, args.init_impl_file)
    if os.path.exists(init_path):
        with open(init_path, 'r') as f:
            init_content = f.read()
        apis.append(parser.parse("Init.scala", init_content))
    
    # Parse all Planner implementations
    impl_dir = os.path.join(args.scala_path, args.apis_dir)
    for file_name in os.listdir(impl_dir):
        if file_name.endswith(".scala"):
            with open(os.path.join(impl_dir, file_name), 'r') as f:
                content = f.read()
            apis.append(parser.parse(file_name, content))
    
    # Save results
    save_apis(apis, args.output_dir, args.output_file)


if __name__ == "__main__":
    main()


