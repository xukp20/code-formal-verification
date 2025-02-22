import json
import os
from typing import List, Dict
from pydantic import BaseModel
from src.utils.apis.langchain_client import _call_openai_completion
from src.utils.lean.compile import DEFAULT_COMPILER
from src.trying.parse_apis import API
import argparse


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="deepseek-r1")
    parser.add_argument("--output_dir", type=str, default="outputs/")
    parser.add_argument("--apis_file", type=str, default="apis.json")
    parser.add_argument("--db_lean_file", type=str, default="db.lean")
    parser.add_argument("--max_retries", type=int, default=5)
    return parser.parse_args()

class APIMapping(BaseModel):
    api_name: str
    lean_name: str

class APIFormalizer:
    def __init__(self, model: str, max_retries: int = 5):
        self.model = model
        self.max_retries = max_retries
        self.lean_compiler = DEFAULT_COMPILER

    def formalize_api(self, api: API, db_code: str) -> tuple[str, str]:
        """Formalize an API into a Lean function with retry mechanism"""
        system_prompt = """
You are a formal verification expert converting API specifications to Lean 4 functions.

Requirements:
1. Create a Lean function that matches the API's behavior
2. Function must take old table as input and return new table as output, in order to express the side effects of the operation on the table itself.
3. Include other API parameters as inputs
4. Define response types as inductive types for different responses (Success/Error/Failed)
5. Include necessary imports

Example format:
```lean
import DB

namespace API

inductive RegisterResponse
| success : String → RegisterResponse
| error : String → RegisterResponse
deriving Repr

def register (oldTable : DB.UsersTable) (username : String) (password : String) : 
    (DB.UsersTable × RegisterResponse) := 
    -- implementation using DB operations

end API
```

The function name should be a valid Lean identifier (lowercase, no special characters).
"""
        
        user_prompt = f"""
DB Implementation:
```lean
{db_code}
```

API to formalize:
{api.to_markdown()}
"""
        
        history = []
        lean_name = None
        
        for attempt in range(self.max_retries):
            if attempt > 0:
                user_prompt = f"Compilation failed with error:\n{error_msg}\n\nPlease fix the Lean code."
            
            print(f"Attempt {attempt + 1} of {self.max_retries}")
            print(user_prompt)
            
            response = _call_openai_completion(
                model=self.model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                history=history,
                temperature=0.0
            )
            
            try:
                lean_code = response.split("```lean")[1].split("```")[0].strip()
                print(lean_code)
                # Extract function name from the code
                for line in lean_code.split("\n"):
                    if line.startswith("def "):
                        lean_name = line.split()[1].strip()
                        break
                if not lean_name:
                    raise ValueError("Could not find function definition in Lean code")
                
                # Try compiling the code
                success, result = self.lean_compiler.check_compile(lean_code, [db_code])
                if success:
                    return lean_name, lean_code
                
                error_msg = self.lean_compiler.format_errors(result, lean_code)
                print(error_msg)
                history.extend([
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": response},
                ])
                
            except Exception as e:
                error_msg = str(e)
                print(error_msg)
                history.extend([
                    {"role": "assistant", "content": response},
                    {"role": "user", "content": f"Error processing response: {error_msg}"}
                ])
        
        raise ValueError(f"Failed to generate valid Lean code after {self.max_retries} attempts")

    def validate_lean_code(self, lean_code: str, db_code: str) -> bool:
        """Validate Lean code compilation"""
        success, result = self.lean_compiler.check_compile(lean_code, [db_code])
        if not success:
            error_msg = self.lean_compiler.format_errors(result, lean_code)
            raise ValueError(f"Compilation failed:\n{error_msg}")
        return True

def main():
    args = parse_args()
    
    # Load APIs
    with open(os.path.join(args.output_dir, args.apis_file), 'r') as f:
        apis = [API.model_validate(api_data) for api_data in json.load(f)]
    
    # Load DB code
    with open(os.path.join(args.output_dir, args.db_lean_file), 'r') as f:
        db_code = f.read()
    
    formalizer = APIFormalizer(args.model)
    mappings: List[APIMapping] = []
    
    # Create APIs directory if it doesn't exist
    apis_dir = os.path.join(args.output_dir, "apis")
    os.makedirs(apis_dir, exist_ok=True)
    
    # Process each API
    for api in apis:
        print(f"Formalizing API: {api.name}")
        lean_name, lean_code = formalizer.formalize_api(api, db_code)
        
        # Validate the code
        try:
            formalizer.validate_lean_code(lean_code)
        except ValueError as e:
            print(f"Warning: Generated code for {api.name} failed validation: {str(e)}")
            continue
        
        # Save the Lean file
        file_name = f"{lean_name}.lean"
        with open(os.path.join(apis_dir, file_name), 'w') as f:
            f.write(lean_code)
        
        # Add to mappings
        mappings.append(APIMapping(api_name=api.name, lean_name=lean_name))
    
    # Save mappings
    with open(os.path.join(args.output_dir, "api_mappings.json"), 'w') as f:
        json.dump([m.model_dump() for m in mappings], f, indent=2)

if __name__ == "__main__":
    main() 