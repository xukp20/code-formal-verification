from dataclasses import dataclass
from typing import Dict, List, Any
from pathlib import Path
import json
from src.utils.parse_project.types import JSONSerializable
from src.pipeline.theorem.api.types import APIRequirementGenerationInfo

@dataclass
class TableProperty(JSONSerializable):
    """A property that a table maintains under certain APIs"""
    property: str  # Description of the property
    apis: Dict[str, List[str]]  # service -> list of APIs that maintain this property
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "property": self.property,
            "apis": self.apis
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TableProperty':
        return cls(
            property=data["property"],
            apis=data["apis"]
        )

@dataclass
class TablePropertiesInfo(APIRequirementGenerationInfo):
    """Information about table properties derived from API requirements"""
    table_properties: Dict[str, Dict[str, List[TableProperty]]] = None  # service -> table -> list of properties
    
    def __post_init__(self):
        super().__post_init__()
        if self.table_properties is None:
            self.table_properties = {}
    
    def to_dict(self) -> Dict[str, Any]:
        # Start with parent class dict
        result = super().to_dict()
        
        # Add our fields
        result.update({
            "table_properties": {
                service: {
                    table: [prop.to_dict() for prop in props]
                    for table, props in tables.items()
                }
                for service, tables in self.table_properties.items()
            },

        })
        return result
    
    @classmethod
    def from_requirements(cls, requirements_info: APIRequirementGenerationInfo) -> 'TablePropertiesInfo':
        """Create from API requirements info"""
        return cls(
            project=requirements_info.project,
            dependencies=requirements_info.dependencies,
            topological_order=requirements_info.topological_order,
            formalized_tables=requirements_info.formalized_tables,
            api_table_dependencies=requirements_info.api_table_dependencies,
            api_dependencies=requirements_info.api_dependencies,
            api_topological_order=requirements_info.api_topological_order,
            formalized_apis=requirements_info.formalized_apis,
            api_docs=requirements_info.api_docs,
            api_requirements=requirements_info.api_requirements,
            table_properties={}
        )
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TablePropertiesInfo':
        # Create instance using parent class method first
        instance = APIRequirementGenerationInfo.from_dict(data)
        
        # Add our fields
        table_properties = {
            service: {
                table: [TableProperty.from_dict(prop) for prop in props]
                for table, props in tables.items()
            }
            for service, tables in data.get("table_properties", {}).items()
        }
        
        # Create new instance with all fields
        return cls(
            project=instance.project,
            dependencies=instance.dependencies,
            topological_order=instance.topological_order,
            formalized_tables=instance.formalized_tables,
            api_table_dependencies=instance.api_table_dependencies,
            api_dependencies=instance.api_dependencies,
            api_topological_order=instance.api_topological_order,
            formalized_apis=instance.formalized_apis,
            api_docs=instance.api_docs,
            api_requirements=instance.api_requirements,
            table_properties=table_properties
        )
    
    def save(self, output_path: Path) -> None:
        """Save table properties info to output directory"""
        save_path = output_path / "table_properties.json"
        with open(save_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls, path: Path) -> 'TablePropertiesInfo':
        """Load table properties info from file"""
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)
    
    def get_table_properties(self, service_name: str, table_name: str) -> List[TableProperty]:
        """Get properties for a specific table"""
        return self.table_properties.get(service_name, {}).get(table_name, [])
