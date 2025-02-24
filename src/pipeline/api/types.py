from dataclasses import dataclass, field
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
            project=base.project,
            dependencies=base.dependencies,
            topological_order=base.topological_order,
            formalized_tables=base.formalized_tables,
            api_table_dependencies=data["api_table_dependencies"],
            api_dependencies=data["api_dependencies"],
            api_topological_order=data["api_topological_order"]
        )

@dataclass
class APIFormalizationInfo(APIDependencyInfo):
    """API formalization result"""
    formalized_apis: Set[str] = field(default_factory=set)  # Set of successfully formalized API names

    def add_formalized_api(self, api_name: str):
        """Add an API to the set of formalized APIs"""
        self.formalized_apis.add(api_name)

    def to_dict(self) -> dict:
        base_dict = super().to_dict()
        base_dict["formalized_apis"] = list(self.formalized_apis)
        return base_dict

    @classmethod
    def from_dict(cls, data: dict) -> 'APIFormalizationInfo':
        formalized_apis = set(data.pop("formalized_apis", []))
        base = super().from_dict(data)
        return cls(
            project=base.project,
            dependencies=base.dependencies,
            topological_order=base.topological_order,
            formalized_tables=base.formalized_tables,
            api_table_dependencies=base.api_table_dependencies,
            api_dependencies=base.api_dependencies,
            api_topological_order=base.api_topological_order,
            formalized_apis=formalized_apis
        )