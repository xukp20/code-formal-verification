import subprocess
import os, json


# look for compile_lean.sh in the same directory as this file
script_dir = os.path.dirname(__file__)
compile_lean_script = os.path.join(script_dir, "compile_lean.sh")


class LeanCompiler:
    def __init__(self, lean_project_path, source_dir):
        self.lean_project_path = lean_project_path
        self.source_dir = source_dir
        # self.temp_file_path = os.path.join(lean_project_path, source_dir, temp_file_name)
        # self.temp_rel_path = os.path.join(source_dir, temp_file_name)
        self.temp_file_path = None
        self.temp_rel_path = None

    def preprocess_lean_code(self, lean_code):
        return lean_code
    
    def postprocess_result(self, success, result):
        return success, result
    
    def get_temp_name(self):
        # generate a random name with 16 number or letters
        import random
        import string
        return ''.join(random.choices(string.ascii_letters + string.digits, k=16)) + ".lean"
    
    def write_temp_file(self, content, temp_file_name="temp.lean"):
        temp_file_path = os.path.join(self.lean_project_path, self.source_dir, temp_file_name)
        with open(temp_file_path, 'w') as f:
            f.write(content)
        f.close()

    def remove_temp_file(self, temp_file_name="temp.lean"):
        temp_file_path = os.path.join(self.lean_project_path, self.source_dir, temp_file_name)
        os.remove(temp_file_path)

    def parse_result_json(self, result):
        if result == "":
            return None
        try:
            errors = []
            result = result.split("\n")
            for i, line in enumerate(result):
                data = json.loads(line)
                error = {
                    "data": data["data"],
                    "pos": data["pos"],
                    "endPos": data["endPos"],
                    "severity": data["severity"],
                }
                # if data["severity"] == "error":
                errors.append(error)
            return errors
        
        except json.JSONDecodeError:
            print("Error parsing lake result: {}".format(result))
            return [{
                "data": result,
                "pos": {
                    "line": "Unknown",
                    "column": "Unknown",
                },
                "endPos": {
                    "line": "Unknown",
                    "column": "Unknown",
                }
            }]
        

    def compile_temp_file(self, temp_file_name="temp.lean"):
        temp_rel_path = os.path.join(self.source_dir, temp_file_name)
        result = subprocess.run(
            ["bash", compile_lean_script, temp_rel_path, self.lean_project_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        code_with_result = result.stdout.decode("utf-8").strip()
        error_trace = result.stderr.decode("utf-8").strip()
        if error_trace == "":
            error_trace = None

        code, result = code_with_result.split("|", 1)
        return code == "0", self.parse_result_json(result), error_trace

    def check_compile(self, lean_code, premies_codes=None):
        lean_code = self.preprocess_lean_code(lean_code)
        temp_file_name = self.get_temp_name()
        self.write_temp_file(lean_code, temp_file_name)

        premises_file_names = []
        if premies_codes:
            for code in premies_codes:
                premises_file_names.append(self.get_temp_name())
                self.write_temp_file(code, premises_file_names[-1])

        success, result, error_trace = self.compile_temp_file(temp_file_name)

        if error_trace is not None:
            raise Exception(error_trace)
        
        success, result = self.postprocess_result(success, result)

        self.remove_temp_file(temp_file_name)
        for file_name in premises_file_names:
            self.remove_temp_file(file_name)
        
        return success, result
    
    def format_errors(self, errors, lean_code, prefix_margin=0, suffix_margin=5):
        formatted_errors = "| Error | Start | End | Content |\n| --- | --- | --- | --- |\n"
        for error in errors:
            error["data"] = error["data"] or "Unknown error"
            error["pos"] = error["pos"] or {"line": "Unknown", "column": "Unknown"}
            error["endPos"] = error["endPos"] or {"line": "Unknown", "column": "Unknown"}

            # find the content given the line and column
            lines = lean_code.split("\n")
            start_line = error["pos"]["line"]
            start_column = error["pos"]["column"]
            end_line = error["endPos"]["line"]
            end_column = error["endPos"]["column"]
            content = ""
            # if no unknown
            if not (start_line == "Unknown" or start_column == "Unknown"):
                # fill the end position if unknown
                if end_line == "Unknown":
                    end_line = len(lines)
                    end_column = len(lines[end_line - 1])

                if start_line == end_line:
                    content = lines[start_line - 1][max(0, start_column - prefix_margin):min(len(lines[start_line - 1]), end_column + suffix_margin)]
                else:
                    content = lines[start_line - 1][max(0, start_column - prefix_margin):]
                    for i in range(start_line + 1, end_line - 1):
                        content += "\n" + lines[i]
                    content += "\n" + lines[end_line - 1][:min(len(lines[end_line - 1]), end_column + suffix_margin)]

            formatted_errors += f"| {error['data']} | line {error['pos']['line']}, column {error['pos']['column']} | line {error['endPos']['line']}, column {error['endPos']['column']} | {content} |\n"
        return formatted_errors
    
    def format_unsolved_goals(self, unsolved_goals):
        return "\n\n".join(goal["goal"] for goal in unsolved_goals)
    
    def filter_unsolved_goals(self, errors):
        """
            Filter out the unsolved goals from the errors
            Return a list of unsolved goals and the remaining errors
        """
        unsolved_goals = []
        remaining_errors = []
        for error in errors:
            if error["data"].startswith("unsolved goals\n"):
                error.update({
                    "goal": error["data"].split("unsolved goals\n")[1].strip()
                })
                unsolved_goals.append(error)
            else:
                remaining_errors.append(error)
        return unsolved_goals, remaining_errors
    
# load project path from env
LEAN_PROJECT_NAME = os.getenv("LEAN_PROJECT_NAME", "./lean_project")
DEFAULT_COMPILER = LeanCompiler(LEAN_PROJECT_NAME, "")

if __name__ == "__main__":
    compiler = LeanCompiler("./lean_project", "LeanProject")
    lean_code = """
import Mathlib
import Aesop

set_option maxHeartbeats 0
open BigOperators Real Nat Topology Rat


abbrev C: Nat := 1
abbrev b: Nat := 2

theorem add (a: Nat) (h0: a = 4): a + C + b = 7 := by
"""
    code, result = compiler.check_compile(lean_code)
    print(code, result)

    if result is not None:
        unsolved_goals, remaining_errors = compiler.filter_unsolved_goals(result)
        print(unsolved_goals)
        print(remaining_errors)
