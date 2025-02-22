from src.utils.apis.langchain_client import _call_openai_completion
import argparse
from pydantic import BaseModel
from typing import List
from langchain_core.output_parsers import PydanticOutputParser
import json
import os

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="deepseek-r1")
    parser.add_argument("--scala_path", type=str, default="source_code/register")
    parser.add_argument("--db_impl_file", type=str, default="Common/DBAPI/package.scala")
    parser.add_argument("--output_dir", type=str, default="outputs/")
    parser.add_argument("--output_file", type=str, default="db_operations.json")
    return parser.parse_args()


class Parameter(BaseModel):
    name: str
    type: str
    description: str

class ServiceMethod(BaseModel):
    name: str
    parameters: List[Parameter]
    returns: List[Parameter]
    logic: str
    read: bool
    write: bool

    def to_markdown(self) -> str:
        """
        Converts the ServiceMethod instance into a markdown formatted string.
        
        Returns:
            str: Markdown formatted representation of the method
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
        
        # Build the markdown string
        markdown = f"""
### {self.name}

#### Parameters:
{param_str if self.parameters else "- None"}

#### Returns:
{returns_str if self.returns else "- None"}

#### Logic:
{self.logic}

#### Database Operations:
- Read: {'Yes' if self.read else 'No'}
- Write: {'Yes' if self.write else 'No'}
"""
        return markdown.strip()

class MethodList(BaseModel):
    methods: List[ServiceMethod]


class DBMethodParser:
    def __init__(self, model: str):
        self.model = model
        self.output_parser = PydanticOutputParser(pydantic_object=MethodList)
        # self.format_instructions = self.output_parser.get_format_instructions()
        # print(self.format_instructions)

    def parse(self, code_content: str) -> MethodList:
        system_prompt = """
        You are a code analyzer that extracts database-related methods from Scala code.
        Analyze the provided code and identify all public methods that interact with the database.
        Skip internal utility methods like encode/decode.
        
        For each database method, extract:
        1. Method name
        2. Parameters (name, type, and description)
        3. Returns (name, type, and description)
        4. Logic explanation (how it uses parameters and interacts with the database)
        5. Whether it reads from the database
        6. Whether it writes to the database (including updates and deletes)
        
        Output the analysis in JSON format matching this structure:
        
        ```
        {
            "methods": [
                {
                    "name": "method_name",
                    "parameters": [
                        {
                            "name": "parameter_name",
                            "type": "parameter_type",
                            "description": "parameter_description"
                        }
                    ],
                    "returns": [
                        {
                            "name": "return_name",
                            "type": "return_type",
                            "description": "return_description"
                        }
                    ],
                    "logic": "logic_explanation",
                    "read": true/false,
                    "write": true/false
                }
            ]
        }
        ```
        """
        
        user_prompt = f"Analyze this Scala code and extract all database-related methods:\n\n{code_content}"
        
        response = _call_openai_completion(
            model=self.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.0,  # Use deterministic output for consistent parsing
            verbose=True
        )
        
        # Parse the JSON response into MethodList
        try:
            return self.output_parser.parse(response)
        except Exception as e:
            raise ValueError(f"Failed to parse LLM response into MethodList: {str(e)}")


def save_to_json(methods: MethodList, output_dir: str, output_file: str):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(output_dir + "/" + output_file, "w") as f:
        json.dump(methods.model_dump(), f)

def main():
    args = parse_args()
    parser = DBMethodParser(args.model)
    with open(args.scala_path + "/" + args.db_impl_file, "r") as f:
        code_content = f.read()
    
    methods = parser.parse(code_content)
    save_to_json(methods, args.output_dir, args.output_file)
    

if __name__ == "__main__":
    main()