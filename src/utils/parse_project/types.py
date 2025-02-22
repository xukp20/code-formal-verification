from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, TypeVar, Type, Optional, List

T = TypeVar('T', bound='JSONSerializable')

class JSONSerializable:
    """Base class for JSON serializable objects"""
    def to_dict(self) -> Dict[str, Any]:
        raise NotImplementedError
    
    @classmethod
    def from_dict(cls: Type[T], data: Dict[str, Any]) -> T:
        raise NotImplementedError

@dataclass
class TableInfo(JSONSerializable):
    """表信息"""
    name: str
    description: dict  # yaml content
    table_code: Optional[str] = None  # scala code if exists
    lean_code: Optional[str] = None  # lean code if exists

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "table_code": self.table_code,
            "lean_code": self.lean_code
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TableInfo':
        return cls(
            name=data["name"],
            description=data["description"],
            table_code=data.get("table_code"),
            lean_code=data.get("lean_code")
        )

@dataclass
class APIInfo(JSONSerializable):
    """API信息"""
    name: str
    message_description: dict  # message yaml content
    planner_description: dict  # planner yaml content
    planner_code: Optional[str] = None  # scala code if exists
    message_typescript: Optional[str] = None  # typescript code if exists
    message_code: Optional[str] = None  # scala message code if exists
    lean_code: Optional[str] = None  # lean code if exists

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "message_description": self.message_description,
            "planner_description": self.planner_description,
            "planner_code": self.planner_code,
            "message_typescript": self.message_typescript,
            "message_code": self.message_code,
            "lean_code": self.lean_code
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'APIInfo':
        return cls(
            name=data["name"],
            message_description=data["message_description"],
            planner_description=data["planner_description"],
            planner_code=data.get("planner_code"),
            message_typescript=data.get("message_typescript"),
            message_code=data.get("message_code"),
            lean_code=data.get("lean_code")
        )

@dataclass
class ServiceInfo(JSONSerializable):
    """服务信息"""
    name: str
    apis: List[APIInfo]
    tables: List[TableInfo]
    init_code: Optional[str] = None  # Init.scala content if exists

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "apis": [api.to_dict() for api in self.apis],
            "tables": [table.to_dict() for table in self.tables],
            "init_code": self.init_code
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ServiceInfo':
        return cls(
            name=data["name"],
            apis=[APIInfo.from_dict(api) for api in data["apis"]],
            tables=[TableInfo.from_dict(table) for table in data["tables"]],
            init_code=data.get("init_code")
        )

@dataclass
class ProjectStructure(JSONSerializable):
    """项目结构"""
    name: str
    base_path: Path
    services: List[ServiceInfo]
    lean_base_path: Path
    lean_project_name: str
    lean_project_path: Path
    package_path: Path

    # Lean project constants
    DATABASE_DIR = "Database"
    SERVICE_DIR = "Service"
    TEST_DIR = "Test"
    BASIC_LEAN = "Basic.lean"

    