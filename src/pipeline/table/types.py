from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Set
from src.utils.parse_project.parser import ProjectStructure
import json
from pathlib import Path

@dataclass
class TableDependencyInfo:
    """Table dependency analysis result"""
    project: ProjectStructure
    dependencies: Dict[str, List[str]]  # table_name -> list of tables it depends on
    topological_order: Optional[List[str]] = None  # One valid topological sort if exists 

    def save(self, path: Path):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: Path) -> 'TableDependencyInfo':
        with open(path, "r") as f:
            return cls.from_dict(json.load(f))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project": self.project.to_dict(),
            "dependencies": self.dependencies,
            "topological_order": self.topological_order
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TableDependencyInfo':
        return cls(
            project=ProjectStructure.from_dict(data["project"]),
            dependencies=data["dependencies"],
            topological_order=data["topological_order"]
        )
    

class TableFormalizationInfo(TableDependencyInfo):
    """Table formalization result"""
    formalized_tables: Set[str] = set()  # Set of successfully formalized table names

    def save(self, path: Path):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: Path) -> 'TableFormalizationInfo':
        with open(path, "r") as f:
            return cls.from_dict(json.load(f))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project": self.project.to_dict(),
            "dependencies": self.dependencies,
            "formalized_tables": list(self.formalized_tables)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TableFormalizationInfo':
        return cls(
            project=ProjectStructure.from_dict(data["project"]),
            dependencies=data["dependencies"],
            formalized_tables=set(data["formalized_tables"])
        )
