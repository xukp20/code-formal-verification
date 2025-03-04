from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from pathlib import Path
import json
from src.utils.parse_project.types import JSONSerializable
from src.pipeline.formalize.api.types import APIFormalizationInfo

@dataclass
class APIDocInfo(JSONSerializable):
    """API documentation information"""
    service_name: str
    api_name: str
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_name": self.service_name,
            "api_name": self.api_name,
            "description": self.description
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'APIDocInfo':
        return cls(
            service_name=data["service_name"],
            api_name=data["api_name"],
            description=data["description"]
        )

@dataclass
class APIRequirementInfo(JSONSerializable):
    """API requirement information"""
    service_name: str
    api_name: str
    doc: str  # Original API documentation
    requirements: List[str]  # List of requirement descriptions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_name": self.service_name,
            "api_name": self.api_name,
            "doc": self.doc,
            "requirements": self.requirements
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'APIRequirementInfo':
        return cls(
            service_name=data["service_name"],
            api_name=data["api_name"],
            doc=data["doc"],
            requirements=data["requirements"]
        )

@dataclass
class APIRequirementGenerationInfo(APIFormalizationInfo):
    """Complete API requirement generation information extending formalization results"""
    api_docs: Dict[str, Dict[str, str]] = None  # service -> api -> doc
    api_requirements: Dict[str, Dict[str, APIRequirementInfo]] = None  # service -> api -> requirements

    def __post_init__(self):
        if self.api_docs is None:
            self.api_docs = {}
        if self.api_requirements is None:
            self.api_requirements = {}

    def to_dict(self) -> Dict[str, Any]:
        # Start with parent class dict
        result = super().to_dict()
        
        # Add our fields
        result.update({
            "api_docs": self.api_docs,
            "api_requirements": {
                service: {
                    api: info.to_dict()
                    for api, info in apis.items()
                }
                for service, apis in self.api_requirements.items()
            },
        })
        return result

    @classmethod
    def from_formalization(cls, formalization_info: APIFormalizationInfo) -> 'APIRequirementGenerationInfo':
        """Create from formalization results"""
        return cls(
            project=formalization_info.project,
            dependencies=formalization_info.dependencies,
            topological_order=formalization_info.topological_order,
            formalized_tables=formalization_info.formalized_tables,
            api_table_dependencies=formalization_info.api_table_dependencies,
            api_dependencies=formalization_info.api_dependencies,
            api_topological_order=formalization_info.api_topological_order,
            formalized_apis=formalization_info.formalized_apis,
            api_docs={},
            api_requirements={},
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'APIRequirementGenerationInfo':
        # Create instance using parent class method first
        instance = APIFormalizationInfo.from_dict(data)
        
        # Add our fields
        api_docs = data.get("api_docs", {})
        api_requirements = {
            service: {
                api: APIRequirementInfo.from_dict(info)
                for api, info in apis.items()
            }
            for service, apis in data.get("api_requirements", {}).items()
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
            api_docs=api_docs,
            api_requirements=api_requirements,
        )

    def save(self, output_path: Path) -> None:
        """Save requirement generation info to output directory"""
        save_path = output_path / "api_requirements.json"
        with open(save_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: Path) -> 'APIRequirementGenerationInfo':
        """Load requirement generation info from file"""
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)

    def format_project_structure(self) -> str:
        """Format project structure as markdown"""
        lines = ["# Project Structure\n"]
        for service in self.project.services:
            lines.append(f"## Service: {service.name}")
            for api in service.apis:
                lines.append(f"- API: {api.name}")
            lines.append("")
        return "\n".join(lines)

    def format_output_template(self) -> str:
        """Format expected output template"""
        template = {
            service.name: {
                api.name: f"<doc of api \"{api.name}\">"
                for api in service.apis
            }
            for service in self.project.services
        }
        return json.dumps(template, indent=2, ensure_ascii=False)
