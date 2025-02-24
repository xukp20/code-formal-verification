from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from src.pipeline.table.types import TableFormalizationInfo

@dataclass
class APIDependencyInfo(TableFormalizationInfo):
    """API dependency analysis result"""
    api_table_dependencies: Dict[str, List[str]] = None  # api_name -> list of table names it depends on
    api_dependencies: Dict[str, List[str]] = None  # api_name -> list of api names it depends on
    api_topological_order: Optional[List[str]] = None  # One valid topological sort of APIs if exists 

    def to_dict(self) -> dict:
        base_dict = super().to_dict()
        base_dict["api_table_dependencies"] = self.api_table_dependencies
        base_dict["api_dependencies"] = self.api_dependencies
        base_dict["api_topological_order"] = self.api_topological_order
        return base_dict

    @classmethod
    def from_dict(cls, data: dict) -> 'APIDependencyInfo':
        base = super().from_dict(data)
        return cls(
            **base.__dict__,
            api_table_dependencies=data["api_table_dependencies"],
            api_dependencies=data["api_dependencies"],
            api_topological_order=data["api_topological_order"]
        )
