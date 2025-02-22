from dataclasses import dataclass
from typing import Dict, List, Optional
from src.utils.parse_project.parser import ProjectStructure

@dataclass
class TableDependencyInfo:
    """Table dependency analysis result"""
    project: ProjectStructure
    dependencies: Dict[str, List[str]]  # table_name -> list of tables it depends on
    topological_order: Optional[List[str]] = None  # One valid topological sort if exists 