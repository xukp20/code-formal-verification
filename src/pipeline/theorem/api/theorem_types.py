from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from pathlib import Path
import json
from src.utils.parse_project.types import JSONSerializable, TableInfo, APIInfo, ServiceInfo
from src.utils.parse_project.parser import ProjectStructure
from src.pipeline.theorem.table.types import TablePropertiesInfo


@dataclass
class TheoremTableInfo(TableInfo):
    """Table info with theorem related fields"""
    lean_test_code: Optional[str] = None  # Complete lean test file content
    lean_theorems: List[str] = None  # Individual theorem snippets
    lean_prefix: Optional[str] = None  # Lean prefix for the table
    
    def __post_init__(self):
        if self.lean_theorems is None:
            self.lean_theorems = []
    
    def to_dict(self) -> Dict[str, Any]:
        base_dict = super().to_dict()
        base_dict.update({
            "lean_test_code": self.lean_test_code,
            "lean_theorems": self.lean_theorems,
            "lean_prefix": self.lean_prefix
        })
        return base_dict
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TheoremTableInfo':
        return cls(
            name=data["name"],
            description=data["description"],
            table_code=data.get("table_code"),
            lean_code=data.get("lean_code"),
            lean_test_code=data.get("lean_test_code"),
            lean_theorems=data.get("lean_theorems", []),
            lean_prefix=data.get("lean_prefix")
        )

@dataclass
class TheoremAPIInfo(APIInfo):
    """API info with theorem related fields"""
    lean_test_code: Optional[str] = None  # Complete lean test file content
    lean_theorems: List[str] = None  # Individual theorem snippets
    lean_prefix: Optional[str] = None  # Lean prefix for the API

    def __post_init__(self):
        if self.lean_theorems is None:
            self.lean_theorems = []

    def to_dict(self) -> Dict[str, Any]:
        base_dict = super().to_dict()
        base_dict.update({
            "lean_test_code": self.lean_test_code,
            "lean_theorems": self.lean_theorems,
            "lean_prefix": self.lean_prefix
        })
        return base_dict
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TheoremAPIInfo':
        return cls(
            name=data["name"],
            message_description=data.get("message_description"),
            planner_description=data.get("planner_description"),
            planner_code=data.get("planner_code"),
            message_typescript=data.get("message_typescript"),
            message_code=data.get("message_code"),
            lean_code=data.get("lean_code"),
            lean_test_code=data.get("lean_test_code"),
            lean_theorems=data.get("lean_theorems", []),
            lean_prefix=data.get("lean_prefix")
        )

@dataclass
class TheoremServiceInfo(ServiceInfo):
    """Service info with theorem types"""
    name: str
    apis: List[TheoremAPIInfo]
    tables: List[TheoremTableInfo]
    init_code: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "apis": [api.to_dict() for api in self.apis],
            "tables": [table.to_dict() for table in self.tables],
            "init_code": self.init_code
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TheoremServiceInfo':
        return cls(
            name=data["name"],
            apis=[TheoremAPIInfo.from_dict(api) for api in data["apis"]],
            tables=[TheoremTableInfo.from_dict(table) for table in data["tables"]],
            init_code=data.get("init_code")
        )

@dataclass
class TheoremProjectStructure(ProjectStructure):
    """Project structure with theorem support"""
    
    name: str
    base_path: Path
    services: List[TheoremServiceInfo]
    lean_base_path: Path
    lean_project_name: str
    lean_project_path: Path
    package_path: Path

    TEST_DIR: str = "Test"  # Directory for test files
    
    @classmethod
    def from_project(cls, project: ProjectStructure) -> 'TheoremProjectStructure':
        """Create from base project structure"""
        return cls(
            name=project.name,
            base_path=project.base_path,
            services=[TheoremServiceInfo.from_dict(service.to_dict()) for service in project.services],
            lean_base_path=project.lean_base_path,
            lean_project_name=project.lean_project_name,
            lean_project_path=project.lean_project_path,
            package_path=project.package_path
        )
    
    def set_test_lean(self, kind: str, service_name: str, name: str, code: str) -> None:
        """Set test lean code"""
        if kind.lower() == "table":
            table = self._find_table(name)
            if not table:
                raise ValueError(f"Table {name} not found")
            table.lean_test_code = code
        elif kind.lower() == "api":
            api = self._find_api(service_name, name)
            if not api:
                raise ValueError(f"API {name} not found in service {service_name}")
            api.lean_test_code = code
        else:
            raise ValueError(f"Unknown kind: {kind}")
            
        # Write to file
        file_path = self.get_test_lean_path(kind, service_name, name)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(code)
        
        # Update Basic.lean
        self._update_basic_lean()

    def get_test_lean(self, kind: str, service_name: str, name: str) -> str:
        """Get test lean code"""
        if kind.lower() == "table":
            table = self._find_table(name)
            if not table:
                raise ValueError(f"Table {name} not found")
            if not table.lean_test_code:
                return None
            return table.lean_test_code
        elif kind.lower() == "api":
            api = self._find_api(service_name, name)
            if not api:
                raise ValueError(f"API {name} not found in service {service_name}")
            if not api.lean_test_code:
                return None
            return api.lean_test_code
        raise ValueError(f"Unknown kind: {kind}")

    def del_test_lean(self, kind: str, service_name: str, name: str) -> None:
        """Delete test lean code"""
        if kind.lower() == "table":
            table = self._find_table(name)
            if not table:
                raise ValueError(f"Table {name} not found")
            table.lean_test_code = None
            table.lean_theorems = []
        elif kind.lower() == "api":
            api = self._find_api(service_name, name)
            if not api:
                raise ValueError(f"API {name} not found in service {service_name}")
            api.lean_test_code = None
            api.lean_theorems = []
        else:
            raise ValueError(f"Unknown kind: {kind}")
        
        # Delete file
        file_path = self.get_test_lean_path(kind, service_name, name)
        if file_path.exists():
            file_path.unlink()
        
        # Update Basic.lean
        self._update_basic_lean()

    def set_test_lean_prefix(self, kind: str, service_name: str, name: str, prefix: str) -> None:
        """Set test lean prefix"""
        if kind.lower() == "table":
            table = self._find_table(name)
            if not table:
                raise ValueError(f"Table {name} not found")
            table.lean_prefix = prefix
        elif kind.lower() == "api":
            api = self._find_api(service_name, name)
            if not api:
                raise ValueError(f"API {name} not found in service {service_name}")
            api.lean_prefix = prefix
        else:
            raise ValueError(f"Unknown kind: {kind}")
    
    def get_test_lean_prefix(self, kind: str, service_name: str, name: str) -> str:
        """Get test lean prefix"""
        if kind.lower() == "table":
            table = self._find_table(name)
            if not table:
                raise ValueError(f"Table {name} not found")
            return table.lean_prefix
        elif kind.lower() == "api":
            api = self._find_api(service_name, name)
            if not api:
                raise ValueError(f"API {name} not found in service {service_name}")
            return api.lean_prefix
        raise ValueError(f"Unknown kind: {kind}")

    def get_test_lean_path(self, kind: str, service_name: str, name: str) -> Path:
        """Get test lean file path"""
        if kind.lower() == "table":
            if not self._find_table(name):
                raise ValueError(f"Table {name} not found")
            return self.package_path / self.TEST_DIR / self.DATABASE_DIR / f"{name}.lean"
        elif kind.lower() == "api":
            if not self._find_api(service_name, name):
                raise ValueError(f"API {name} not found in service {service_name}")
            return self.package_path / self.TEST_DIR / self.SERVICE_DIR / service_name / f"{name}.lean"
        raise ValueError(f"Unknown kind: {kind}")

    def get_test_lean_import_path(self, kind: str, service_name: str, name: str) -> str:
        """Get test lean import path"""
        if kind.lower() == "table":
            return f"{self.lean_project_name}.Test.{self.DATABASE_DIR}.{name}"
        elif kind.lower() == "api":
            return f"{self.lean_project_name}.Test.{self.SERVICE_DIR}.{service_name}.{name}"
        raise ValueError(f"Unknown kind: {kind}")

    def add_test_lean_theorem(self, kind: str, service_name: str, name: str, theorem: str) -> None:
        """Add a theorem to test lean code"""
        if kind.lower() == "table":
            table = self._find_table(name)
            if not table:
                raise ValueError(f"Table {name} not found")
            if not table.lean_test_code:
                table.lean_test_code = ""
            table.lean_theorems.append(theorem)
        elif kind.lower() == "api":
            api = self._find_api(service_name, name)
            if not api:
                raise ValueError(f"API {name} not found in service {service_name}")
            if not api.lean_test_code:
                api.lean_test_code = ""
            api.lean_theorems.append(theorem)
        else:
            raise ValueError(f"Unknown kind: {kind}")
            
    def pop_test_lean_theorem(self, kind: str, service_name: str, name: str) -> Optional[str]:
        """Remove and return the last theorem"""
        if kind.lower() == "table":
            table = self._find_table(name)
            if not table or not table.lean_theorems:
                return None
            theorem = table.lean_theorems.pop()
        elif kind.lower() == "api":
            api = self._find_api(service_name, name)
            if not api or not api.lean_theorems:
                return None
            theorem = api.lean_theorems.pop()
        else:
            raise ValueError(f"Unknown kind: {kind}")
            
        return theorem

    def _update_basic_lean(self):
        """Update Basic.lean file with all imports including tests"""
        imports = []
        
        # Add database imports
        for service in self.services:
            for table in service.tables:
                if table.lean_code:
                    imports.append(f"import {self.lean_project_name}.{self.DATABASE_DIR}.{table.name}")
                if table.lean_test_code:
                    imports.append(f"import {self.lean_project_name}.{self.TEST_DIR}.{self.DATABASE_DIR}.{table.name}")
        
        # Add API imports
        for service in self.services:
            for api in service.apis:
                if api.lean_code:
                    imports.append(f"import {self.lean_project_name}.{self.SERVICE_DIR}.{service.name}.{api.name}")
                if api.lean_test_code:
                    imports.append(f"import {self.lean_project_name}.{self.TEST_DIR}.{self.SERVICE_DIR}.{service.name}.{api.name}")
        
        # Write to Basic.lean
        basic_path = self.package_path / self.BASIC_LEAN
        basic_path.write_text("\n".join(imports))

@dataclass
class APITheoremGenerationInfo(TablePropertiesInfo):
    """Information about API theorem generation"""
    project: TheoremProjectStructure  # Override project type
    formalized_theorem_apis: Dict[str, List[str]] = None  # service -> list of APIs with theorems
    
    def __post_init__(self):
        super().__post_init__()
        if self.formalized_theorem_apis is None:
            self.formalized_theorem_apis = {}
        if self.project and not isinstance(self.project, TheoremProjectStructure):
            # Convert project to TheoremProjectStructure if needed
            self.project = TheoremProjectStructure.from_project(self.project)
    
    def to_dict(self) -> Dict[str, Any]:
        base_dict = super().to_dict()
        base_dict.update({
            "formalized_theorem_apis": self.formalized_theorem_apis,
            "project": self.project.to_dict() if self.project else None
        })
        return base_dict
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'APITheoremGenerationInfo':
        # Create instance using parent class method first
        instance = super().from_dict(data)
        
        # Convert project to TheoremProjectStructure
        if instance.project:
            instance.project = TheoremProjectStructure.from_project(instance.project)
        
        # Add our fields
        instance.formalized_theorem_apis = data.get("formalized_theorem_apis", {})
        
        return instance
    
    @classmethod
    def from_properties(cls, properties_info: TablePropertiesInfo) -> 'APITheoremGenerationInfo':
        """Create from table properties info"""
        return cls(
            project=TheoremProjectStructure.from_project(properties_info.project),
            dependencies=properties_info.dependencies,
            topological_order=properties_info.topological_order,
            formalized_tables=properties_info.formalized_tables,
            api_table_dependencies=properties_info.api_table_dependencies,
            api_dependencies=properties_info.api_dependencies,
            api_topological_order=properties_info.api_topological_order,
            formalized_apis=properties_info.formalized_apis,
            api_docs=properties_info.api_docs,
            api_requirements=properties_info.api_requirements,
            table_properties=properties_info.table_properties,
            formalized_theorem_apis={}  # Initialize empty formalized APIs dict
        )
    
    def add_formalized_theorem_api(self, service_name: str, api_name: str) -> None:
        """Add an API to the list of formalized APIs"""
        if service_name not in self.formalized_theorem_apis:
            self.formalized_theorem_apis[service_name] = []
        if api_name not in self.formalized_theorem_apis[service_name]:
            self.formalized_theorem_apis[service_name].append(api_name)
    
    def is_api_theorem_formalized(self, service_name: str, api_name: str) -> bool:
        """Check if an API has been formalized"""
        return (service_name in self.formalized_theorem_apis and 
                api_name in self.formalized_theorem_apis[service_name])
    
    def get_api_theorems(self, service_name: str, api_name: str) -> List[Optional[str]]:
        """Get theorems for an API"""
        api = self.project._find_api(service_name, api_name)
        if not api:
            raise ValueError(f"API {api_name} not found in service {service_name}")
        return api.lean_theorems

    def get_table_theorems(self, table_name: str) -> List[Optional[str]]:
        """Get theorems for a table"""
        table = self.project._find_table(table_name)
        if not table:
            raise ValueError(f"Table {table_name} not found")
        return table.lean_theorems
    
    def save(self, output_path: Path) -> None:
        """Save theorem generation info to output directory"""
        save_path = output_path / "api_theorems.json"
        with open(save_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls, path: Path) -> 'APITheoremGenerationInfo':
        """Load theorem generation info from file"""
        output_path = path.parent
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)