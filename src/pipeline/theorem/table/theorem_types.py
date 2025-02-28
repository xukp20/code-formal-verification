from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from src.pipeline.theorem.api.theorem_types import APITheoremGenerationInfo
from src.utils.parse_project.types import TableInfo
import json
from pathlib import Path

@dataclass
class TableTheoremGenerationInfo(APITheoremGenerationInfo):
    """Information about table theorem generation"""
    formalized_theorem_tables: List[str] = None  # List of tables with formalized theorems
    
    def __post_init__(self):
        super().__post_init__()
        if self.formalized_theorem_tables is None:
            self.formalized_theorem_tables = []

    def to_dict(self) -> Dict[str, Any]:
        base_dict = super().to_dict()
        base_dict["formalized_theorem_tables"] = self.formalized_theorem_tables
        return base_dict
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TableTheoremGenerationInfo':
        instance = super().from_dict(data)
        instance.formalized_theorem_tables = data.get("formalized_theorem_tables")
        return instance
    
    def add_formalized_theorem_table(self, table_name: str) -> None:
        """Add a table to the list of formalized tables"""
        if table_name not in self.formalized_theorem_tables:
            self.formalized_theorem_tables.append(table_name)
    
    def is_table_theorem_formalized(self, table_name: str) -> bool:
        """Check if a table has been formalized"""
        return table_name in self.formalized_theorem_tables
    
    def get_table_theorems(self, table_name: str) -> List[Optional[str]]:
        """Get theorems for a table"""
        table = self.project._find_table(table_name)
        if not table:
            raise ValueError(f"Table {table_name} not found")
        return table.lean_theorems 
    
    @classmethod
    def from_api_theorem_generation_info(cls, api_theorem_generation_info: APITheoremGenerationInfo) -> 'TableTheoremGenerationInfo':
        """Create from API theorem generation info"""
        return TableTheoremGenerationInfo(
            project=api_theorem_generation_info.project,
            dependencies=api_theorem_generation_info.dependencies,
            topological_order=api_theorem_generation_info.topological_order,
            formalized_tables=api_theorem_generation_info.formalized_tables,
            api_table_dependencies=api_theorem_generation_info.api_table_dependencies,
            api_dependencies=api_theorem_generation_info.api_dependencies,
            api_topological_order=api_theorem_generation_info.api_topological_order,
            formalized_apis=api_theorem_generation_info.formalized_apis,
            api_docs=api_theorem_generation_info.api_docs,
            api_requirements=api_theorem_generation_info.api_requirements,
            table_properties=api_theorem_generation_info.table_properties,
            formalized_theorem_apis=api_theorem_generation_info.formalized_theorem_apis,
            formalized_theorem_tables=[]
        )
    
    def save(self, output_path: Path) -> None:
        """Save theorem generation info to output directory"""
        save_path = output_path / "table_theorems.json"
        with open(save_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls, path: Path) -> 'TableTheoremGenerationInfo':
        """Load theorem generation info from file"""
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)
    