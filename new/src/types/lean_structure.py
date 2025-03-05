from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

@dataclass
class LeanProjectStructure:
    """Static manager for Lean project file structure"""
    
    @staticmethod
    def get_api_path(package: str, service: str, api_name: str) -> List[str]:
        """Get relative path for API implementation file"""
        return [package, service, "APIs", f"{api_name}"]
    
    @staticmethod
    def get_process_path(package: str, service: str, process_name: str) -> List[str]:
        """Get relative path for Process implementation file"""
        return [package, service, "Processes", f"{process_name}"]
    
    @staticmethod
    def get_table_path(package: str, service: str, table_name: str) -> List[str]:
        """Get relative path for Table implementation file"""
        return [package, service, "Tables", f"{table_name}"]
    
    @staticmethod
    def get_api_theorem_path(package: str, service: str, api_name: str, 
                           theorem_idx: int, negative: bool = False) -> List[str]:
        """Get relative path for API theorem file"""
        suffix = "Neg" if negative else ""
        return [package, service, "Tests", "APIs", api_name, f"Theorem{theorem_idx}{suffix}"]
    
    @staticmethod
    def get_table_theorem_path(package: str, service: str, table_name: str,
                             theorem_idx: int, negative: bool = False) -> List[str]:
        """Get relative path for Table theorem file"""
        suffix = "Neg" if negative else ""
        return [package, service, "Tests", "Tables", table_name, f"Theorem{theorem_idx}{suffix}"]
    
    @staticmethod
    def get_basic_path(package: str) -> List[str]:
        """Get relative path for Basic.lean"""
        return [package, "Basic"]
    
    @staticmethod
    def to_file_path(project_root: Path, relative_path: List[str]) -> Path:
        """Convert relative path list to absolute file path"""
        relative_path[-1] = relative_path[-1] + ".lean"
        return project_root.joinpath(*relative_path)
    
    @staticmethod
    def to_import_path(path: List[str]) -> str:
        """Convert relative path to Lean import path"""
        # Remove .lean extension if present
        return ".".join(path)
    
    @staticmethod
    def get_entry_path(package: str) -> List[str]:
        """Get relative path for project entry file"""
        return [f"{package}"] 