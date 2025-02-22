import json
import os
from typing import List, Optional
from pydantic import BaseModel
from src.utils.apis.langchain_client import _call_openai_completion
from src.trying.parse_apis import API
from langchain_core.output_parsers import PydanticOutputParser
from src.utils.lean.compile import LeanCompiler, DEFAULT_COMPILER
import argparse

class DBInferenceResult(BaseModel):
    reasoning_process: str
    functional_description: str

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="deepseek-r1")
    parser.add_argument("--output_dir", type=str, default="outputs/")
    parser.add_argument("--apis_file", type=str, default="apis.json")
    parser.add_argument("--max_retries", type=str, default=5)
    return parser.parse_args()

class CompilationResult:
    def __init__(self, success: bool, error: Optional[str] = None):
        self.success = success
        self.error = error

class DBFormalizer:
    def __init__(self, model: str, max_retries: int = 5):
        self.model = model
        self.max_retries = max_retries
        self.lean_compiler = DEFAULT_COMPILER

    def parse_lean_code(self, lean_code: str) -> str:
        return lean_code.split("```lean")[1].split("```")[0].strip()
    
    def formalize_to_lean(self, apis: List[API]) -> str:
        # Format APIs into markdown for analysis
        apis_md = "\n\n".join(api.to_markdown() for api in apis)
        
        system_prompt = """
You are a database architect and formal verification expert analyzing API usage patterns to infer and formalize the required database schema.

Follow these steps:
1. Analyze each API's database interactions
2. Identify tables and their relationships
3. Determine required columns and their types
4. List all necessary database operations to write a detailed design
5. Convert the design into Lean 4 code

Requirements for Lean 4 code:
1. Define database entities as Lean 4 types
2. Implement database operations as methods
- In order to express the side effects of the operation on the table itself, the inputs should ALWAYS include an old table and the outputs should ALWAYS include a new table, with other inputs and outputs for the operation. Even though the function does not change the table, it should still include the old table as an input and the new table as an output.
- Please define explicit types for the types of the different outputs like success, error, etc. You can add String inside for a description of the error.
3. Package everything in a module

Example Lean 4 format:
```lean
namespace DB

structure <name of the record1> where
    id: Nat
    value: String
    deriving Repr

structure <name of the table1> where
    records: List <name of the record1>

def <table1>.create (old_table: <name of the table1>) (new_record: <name of the record1>): (<name of the table1>, other return values) :=
    -- implementation

...

end DB
```

Provide your analysis in markdown format with these sections:
### Reasoning
Step-by-step analysis of how you arrived at the schema

### Functional Description
Clear description of required database capabilities

### Lean Code
```lean
<your Lean 4 implementation>
```
        """

        history = []
        user_prompt = f"Analyze these APIs and their DB usage:\n\n{apis_md}"

        print(user_prompt)
        
        for attempt in range(self.max_retries):
            if attempt > 0:
                user_prompt = f"Compilation failed with error:\n{compilation_result.error}\n\nPlease fix the Lean code."

            print(f"Attempt {attempt + 1} of {self.max_retries}")

            response = _call_openai_completion(
                model=self.model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                history=history,
                temperature=0.0
            )

            print(response)

            try:
                lean_code = self.parse_lean_code(response)
            except Exception as e:
                print(f"Error parsing Lean code: {e}")
                raise e

            # Try compiling the code
            compilation_result = self._compile_lean_code(lean_code)
            if compilation_result.success:
                return lean_code
            
            history.extend([
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": response},
            ])
            
        raise Exception("Failed to generate valid Lean code after max retries")

    def _compile_lean_code(self, code: str) -> CompilationResult:
        """Compile Lean code and return result"""
        success, result = self.lean_compiler.check_compile(code)
        print(success, result)
        if success:
            return CompilationResult(success=True)
        
        error_msg = self.lean_compiler.format_errors(result, code)
        return CompilationResult(success=False, error=error_msg)

def main():
    args = parse_args()
    
    # Load APIs
    with open(os.path.join(args.output_dir, args.apis_file), 'r') as f:
        data = json.load(f)
        apis = [API.model_validate(api_data) for api_data in data]
    
    formalizer = DBFormalizer(args.model)
    
    lean_code = formalizer.formalize_to_lean(apis)
    
    # Save Lean code
    with open(os.path.join(args.output_dir, 'db.lean'), 'w') as f:
        f.write(lean_code)

if __name__ == "__main__":
    main()