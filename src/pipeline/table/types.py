from dataclasses import dataclass, field
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

    def to_dict(self) -> dict:
        return {
            "project": self.project.to_dict(),
            "dependencies": self.dependencies,
            "topological_order": self.topological_order
        }

    def save(self, path: Path):
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> 'TableDependencyInfo':
        return cls(
            project=ProjectStructure.from_dict(data["project"]),
            dependencies=data["dependencies"],
            topological_order=data["topological_order"]
        )

    @classmethod
    def load(cls, path: Path) -> 'TableDependencyInfo':
        with open(path) as f:
            return cls.from_dict(json.load(f))

@dataclass
class TableFormalizationInfo(TableDependencyInfo):
    """Table formalization result"""
    formalized_tables: Set[str] = field(default_factory=set)  # Set of successfully formalized table names

    def add_formalized_table(self, table_name: str):
        """Add a table to the set of formalized tables"""
        self.formalized_tables.add(table_name)

    def to_dict(self) -> dict:
        base_dict = super().to_dict()
        base_dict["formalized_tables"] = list(self.formalized_tables)  # Convert set to list for JSON
        return base_dict

    def save(self, path: Path):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> 'TableFormalizationInfo':
        # Convert list back to set for formalized_tables
        formalized_tables = set(data.pop("formalized_tables", []))
        base = super().from_dict(data)
        return cls(
            project=base.project,
            dependencies=base.dependencies,
            topological_order=base.topological_order,
            formalized_tables=formalized_tables
        )

    @classmethod
    def load(cls, path: Path) -> 'TableFormalizationInfo':
        with open(path, "r") as f:
            return cls.from_dict(json.load(f))
