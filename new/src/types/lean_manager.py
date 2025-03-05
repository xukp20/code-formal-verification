from pathlib import Path
from typing import List, Optional, Tuple, Dict
import subprocess
import shutil
from dataclasses import dataclass
import time
import os


from src.utils.lean.build_parser import (
    parse_build_output_to_messages,
    parse_lean_message_details,
    all_errors_are_unsolved_goals
)

@dataclass
class LeanProjectManager:
    """Static manager for Lean project operations"""
    
    LAKEFILE_TEMPLATE = '''
import Lake
open Lake DSL

package {name} {{
  -- add package configuration options here
}}

@[default_target]
lean_lib «{name}» {{
  -- add library configuration options here
}}
'''

    LAKEFILE_TEMPLATE_WITH_MATHLIB = '''
import Lake
open Lake DSL

require "leanprover-community" / "mathlib"

package {name} {{
  -- add package configuration options here
}}

@[default_target]
lean_lib «{name}» {{
  -- add library configuration options here
}}
'''

    @staticmethod
    def _run_lake_build(project_path: Path) -> Tuple[bool, str]:
        """Run lake build command
        
        Args:
            project_path: Path to project root (containing lakefile.lean)
            
        Returns:
            (success, output)
        """
        try:
            env = os.environ.copy()

            result = subprocess.run(
                ["lake", "build"],
                cwd=project_path,
                capture_output=True,
                text=True,
                env=env
            )
            return result.returncode == 0, result.stdout
        except Exception as e:
            return False, f"Build failed: {str(e)}"

    @staticmethod
    def _run_lake_update(project_path: Path) -> Tuple[bool, str]:
        """Run lake update command
        
        Args:
            project_path: Path to project root (containing lakefile.lean)
            
        Returns:
            (success, output)
        """
        try:
            env = os.environ.copy()

            result = subprocess.run(
                ["lake", "update"],
                cwd=project_path,
                capture_output=True,
                text=True,
                env=env
            )
            return result.returncode == 0, result.stdout
        except Exception as e:
            return False, f"Update failed: {str(e)}"

    @staticmethod
    def _try_copy_package(lean_project_path: Path) -> bool:
        """Try to copy package to lean_project"""
        # load package_path from env
        package_path = os.getenv("PACKAGE_PATH")
        if package_path:
            start_time = time.time()
            print(f"Copying package to {lean_project_path / '.lake'}")
            # mkdir .lake in the lean project path
            (lean_project_path / ".lake").mkdir(parents=True, exist_ok=True)
            # package_path is the dir "packages", copy it with the content to .lake
            shutil.copytree(package_path, lean_project_path / ".lake" / "packages")
            end_time = time.time()
            print(f"Copying package to {lean_project_path / '.lake'} took {end_time - start_time} seconds")
        

    @staticmethod
    def init_project(lean_base_path: Path, project_name: str, with_mathlib: bool = True) -> Tuple[bool, str]:
        """Initialize new Lean project
        
        Args:
            lean_base_path: Base directory for all Lean projects
            project_name: Name of the Lean project
            with_mathlib: Whether to include mathlib
            
        Returns:
            (success, message)
        """
        try:
            # Create base directory
            lean_base_path.mkdir(parents=True, exist_ok=True)
            
            # Run lake new
            result = subprocess.run(
                ["lake", "new", project_name],
                cwd=lean_base_path,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                return False, f"Lake init failed: {result.stderr}"
            
            project_path = lean_base_path / project_name
            
            # Delete Main.lean
            main_path = project_path / "Main.lean"
            if main_path.exists():
                main_path.unlink()
            
            # Update lakefile
            lakefile_path = project_path / "lakefile.lean"
            template = (LeanProjectManager.LAKEFILE_TEMPLATE_WITH_MATHLIB if with_mathlib 
                      else LeanProjectManager.LAKEFILE_TEMPLATE)
            lakefile_path.write_text(template.format(name=project_name))
            
            # Copy package
            LeanProjectManager._try_copy_package(project_path)

            # Run lake update
            success, message = LeanProjectManager._run_lake_update(project_path)
            if not success:
                return False, f"Lake update failed: {message}"
            
            # Run lake build
            success, message = LeanProjectManager._run_lake_build(project_path)
            if not success:
                return False, f"Lake build failed: {message}"
                
            return True, "Project initialized successfully"
            
        except Exception as e:
            return False, f"Failed to initialize project: {str(e)}"

    @staticmethod
    def write_file(file_path: Path, content: str) -> Tuple[bool, str]:
        """Write content to file, creating parent directories if needed"""
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
            return True, "File written successfully"
        except Exception as e:
            return False, f"Failed to write file: {str(e)}"
    
    @staticmethod
    def delete_file(file_path: Path) -> Tuple[bool, str]:
        """Delete file if it exists"""
        try:
            if file_path.exists():
                file_path.unlink()
            return True, "File deleted successfully"
        except Exception as e:
            return False, f"Failed to delete file: {str(e)}"

    @staticmethod
    def _get_error_context(file_path: Path, line: int, column: int) -> str:
        """Get context lines around an error
        
        Args:
            file_path: Path to the file
            line: Line number
            column: Column number
            
        Returns:
            String containing the context lines with error marked
        """
        try:
            with open(file_path, 'r') as f:
                lines = f.readlines()
                
            # Get context lines (line numbers are 1-based)
            line_idx = line - 1
            context_lines = []
            
            # Add previous line if exists
            if line_idx > 0:
                context_lines.append(lines[line_idx - 1].rstrip())
                
            # Add error line with marker
            error_line = lines[line_idx].rstrip()
            marked_line = (
                error_line[:column] + 
                "[error]" + 
                error_line[column:]
            )
            context_lines.append(marked_line)

            # Add next line if exists
            if line_idx < len(lines) - 1:
                context_lines.append(lines[line_idx + 1].rstrip())

            return "\n".join(context_lines)
        except Exception as e:
            return f"Error getting context: {str(e)}"
        
    @staticmethod
    def _format_error_message(lean_project_path: Path, error_info: Dict[str, str], add_context: bool = False) -> str:
        """Format error information as markdown
        
        Args:
            lean_project_path: Path to Lean project
            error_info: Dict containing error details
            add_context: Whether to include file context

        Returns:
            Formatted markdown string
        """
        file = error_info["file"]
        line = error_info["line"]
        column = error_info["column"]

        # Get absolute file path
        file_path = lean_project_path / file
        if not file_path.exists():
            return f"File not found: {file_path}"
        
        # Get context if requested
        if add_context:     
            return f"""### File Path
{file_path}

### Line: Column
{line}: {column}

### Context ([error] marks the error position)
```lean
{LeanProjectManager._get_error_context(file_path, line, column)}
```

### Content
{error_info["content"]}
----------------------------------------------------
"""
        else:
            return f"""### File Path
{file_path}

### Line: Column
{line}: {column}

### Content
{error_info["content"]}
----------------------------------------------------
"""
            
    @staticmethod
    def build(project_path: Path, parse: bool = False, 
             only_errors: bool = False, add_context: bool = False,
             only_first: bool = False) -> Tuple[bool, str]:
        """Run lake build and parse output if requested
        
        Args:
            project_path: Path to project root
            parse: Whether to parse build output
            only_errors: Only include errors in output
            add_context: Add context to error messages
            only_first: Only include first error
            
        Returns:
            (success, message)
        """
        success, output = LeanProjectManager._run_lake_build(project_path)
        
        if not parse:
            return success, output
            
        # Parse build output
        messages = parse_build_output_to_messages(output)
        if not messages:
            return success, output
            
        details = parse_lean_message_details(
            messages,
            only_errors=only_errors,
        )
        
        if not details:
            return success, f"No errors or warnings found in \n{output}" if success else f"Build failed with no parseable errors:\n{output}"
            
        # Format parsed output
        formatted_messages = []
        for detail in details:
            formatted_messages.append(
                LeanProjectManager._format_error_message(
                    project_path, detail, add_context
                )
            )

        return success, "\n\n".join(formatted_messages)