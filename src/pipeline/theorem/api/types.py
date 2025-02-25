from dataclasses import dataclass
from typing import Dict, List, Any
from pathlib import Path
import json
from src.utils.parse_project.types import JSONSerializable
from src.utils.parse_project.parser import ProjectStructure

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
class APIRequirementGenerationInfo(JSONSerializable):
    """Complete API requirement generation information including project structure"""
    project: ProjectStructure
    api_docs: Dict[str, Dict[str, str]]  # service -> api -> doc
    api_requirements: Dict[str, Dict[str, APIRequirementInfo]]  # service -> api -> requirements
    output_path: Path

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project": self.project.to_dict(),
            "api_docs": self.api_docs,
            "api_requirements": {
                service: {
                    api: info.to_dict()
                    for api, info in apis.items()
                }
                for service, apis in self.api_requirements.items()
            }
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], output_path: Path) -> 'APIRequirementGenerationInfo':
        return cls(
            project=ProjectStructure.from_dict(data["project"]),
            api_docs=data["api_docs"],
            api_requirements={
                service: {
                    api: APIRequirementInfo.from_dict(info)
                    for api, info in apis.items()
                }
                for service, apis in data["api_requirements"].items()
            },
            output_path=output_path
        )

    def save(self) -> None:
        """Save requirement generation info to output directory"""
        save_path = self.output_path / "api_requirements.json"
        with open(save_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, output_path: Path) -> 'APIRequirementGenerationInfo':
        """Load requirement generation info from output directory"""
        load_path = output_path / "api_requirements.json"
        with open(load_path) as f:
            data = json.load(f)
        return cls.from_dict(data, output_path)

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
        return json.dumps(template, indent=2) 