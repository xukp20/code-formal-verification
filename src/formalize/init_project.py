from pathlib import Path
import yaml
from typing import Tuple
import os
from logging import Logger

from src.types.project import ProjectStructure

def init_project(project_name: str, base_path: str, lean_base_path: str) -> Tuple[bool, str, ProjectStructure]:
    """Initialize project structure and Lean repository
    
    Args:
        project_name: Name of the project
        base_path: Path to source code repository
        lean_base_path: Path to create Lean project
        
    Returns:
        (success, message, project_structure)
    """
    # First create project structure
    project = ProjectStructure(
        name=project_name,
        base_path=Path(base_path) / project_name,
        lean_project_name=project_name[0].upper() + project_name[1:],
        lean_project_path=Path(lean_base_path) / (project_name[0].upper() + project_name[1:])
    )
    
    # Load source code repository
    success, message = project.load_source_repository()
    if not success:
        return False, message, project
        
    # Initialize Lean repository
    success, message = project.init_lean_repository()
    if not success:
        return False, message, project
        
    return True, "Project initialized successfully", project


if __name__ == "__main__":
    success, message, project = init_project("UserAuthenticationProject11", "../source_code", "lean_project")
    print(success, message)
    print(project)
