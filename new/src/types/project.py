from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import json
from collections import defaultdict

from src.types.lean_file import LeanFunctionFile, LeanStructureFile, LeanTheoremFile
from src.types.lean_manager import LeanProjectManager
from src.types.lean_structure import LeanProjectStructure
from logging import Logger
@dataclass
class Dependency:
    """Dependencies of an API/Process/Table"""
    tables: List[str] = field(default_factory=list)
    processes: List[str] = field(default_factory=list)
    apis: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tables": self.tables,
            "processes": self.processes,
            "apis": self.apis
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Dependency':
        return cls(
            tables=data.get('tables', []),
            processes=data.get('processes', []),
            apis=data.get('apis', [])
        )

@dataclass
class APITheorem:
    """A theorem about API functionality"""
    description: Optional[str] = None
    theorem: Optional[LeanTheoremFile] = None
    theorem_negative: Optional[LeanTheoremFile] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "theorem": self.theorem.__dict__ if self.theorem else None,
            "theorem_negative": self.theorem_negative.__dict__ if self.theorem_negative else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'APITheorem':
        return cls(
            description=data.get('description'),
            theorem=LeanTheoremFile(**data['theorem']) if data.get('theorem') else None,
            theorem_negative=LeanTheoremFile(**data['theorem_negative']) if data.get('theorem_negative') else None
        )

@dataclass
class APIFunction:
    name: Optional[str] = None
    planner_code: Optional[str] = None
    message_code: Optional[str] = None
    dependencies: Optional[Dependency] = None
    lean_function: Optional[LeanFunctionFile] = None
    doc: Optional[str] = None
    theorems: List[APITheorem] = field(default_factory=list)

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = Dependency()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "planner_code": self.planner_code,
            "message_code": self.message_code,
            "dependencies": self.dependencies.to_dict() if self.dependencies else None,
            "lean_function": self.lean_function.__dict__ if self.lean_function else None,
            "doc": self.doc,
            "theorems": [thm.to_dict() for thm in self.theorems]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'APIFunction':
        return cls(
            name=data.get('name'),
            planner_code=data.get('planner_code'),
            message_code=data.get('message_code'),
            dependencies=Dependency.from_dict(data['dependencies']) if data.get('dependencies') else None,
            lean_function=LeanFunctionFile(**data['lean_function']) if data.get('lean_function') else None,
            doc=data.get('doc'),
            theorems=[APITheorem.from_dict(t) for t in data.get('theorems', [])]
        )

    def to_markdown(self, show_fields: Dict[str, bool] = None) -> str:
        if show_fields is None:
            show_fields = {
                "planner_code": True,
                "message_code": True,
                "dependencies": False,  # Default to False
                "lean_function": True,
                "doc": True,
                "theorems": True
            }
            
        lines = [f"## API: {self.name}"]
        
        if show_fields.get("planner_code", True) and self.planner_code:
            lines.extend([
                "\n### Planner Code",
                "```scala",
                self.planner_code,
                "```"
            ])
            
        if show_fields.get("message_code", True) and self.message_code:
            lines.extend([
                "\n### Message Code",
                "```scala",
                self.message_code,
                "```"
            ])
            
        if show_fields.get("dependencies", True) and self.dependencies and any([
            self.dependencies.tables,
            self.dependencies.processes,
            self.dependencies.apis
        ]):
            lines.append("\n### Dependencies")
            if self.dependencies.tables:
                lines.extend([
                    "#### Tables:",
                    ", ".join(self.dependencies.tables)
                ])
            if self.dependencies.processes:
                lines.extend([
                    "#### Processes:",
                    ", ".join(self.dependencies.processes)
                ])
            if self.dependencies.apis:
                lines.extend([
                    "#### APIs:",
                    ", ".join([f"{d['service']}.{d['api']}" for d in self.dependencies.apis])
                ])
                
        if show_fields.get("lean_function", True) and self.lean_function:
            lines.extend([
                "\n### Lean Function",
                self.lean_function.to_markdown()
            ])
            
        if show_fields.get("doc", True) and self.doc:
            lines.extend([
                "\n### Documentation",
                self.doc
            ])
            
        if show_fields.get("theorems", True) and self.theorems:
            lines.append("\n### Theorems")
            for thm in self.theorems:
                lines.extend([
                    f"\n#### Theorem Description",
                    thm.description or "No description",
                    "\n##### Positive Theorem:",
                    thm.theorem.to_markdown() if thm.theorem else "Not defined",
                    "\n##### Negative Theorem:",
                    thm.theorem_negative.to_markdown() if thm.theorem_negative else "Not defined"
                ])
                
        return "\n".join(lines)

    @staticmethod
    def get_markdown_structure(show_fields: Dict[str, bool] = None) -> str:
        if show_fields is None:
            show_fields = {
                "planner_code": True,
                "message_code": True,
                "dependencies": False,
                "lean_function": True,
                "doc": True,
                "theorems": True
            }
            
        lines = ["## API: <name>"]
        
        if show_fields.get("planner_code", True):
            lines.extend([
                "\n### Planner Code",
                "```scala",
                "<planner implementation>",
                "```"
            ])
            
        if show_fields.get("message_code", True):
            lines.extend([
                "\n### Message Code",
                "```scala",
                "<message implementation>",
                "```"
            ])
            
        if show_fields.get("dependencies", False):
            lines.extend([
                "\n### Dependencies",
                "#### Tables:",
                "<table1, table2, ...>",
                "#### Processes:",
                "<process1, process2, ...>",
                "#### APIs:",
                "<service1.api1, service2.api2, ...>"
            ])
            
        if show_fields.get("lean_function", True):
            lines.extend([
                "\n### Lean Function",
                "<lean function code>"
            ])
            
        if show_fields.get("doc", True):
            lines.extend([
                "\n### Documentation",
                "<api documentation>"
            ])
            
        if show_fields.get("theorems", True):
            lines.extend([
                "\n### Theorems",
                "#### Theorem Description",
                "<theorem description>",
                "##### Positive Theorem:",
                "<theorem code>",
                "##### Negative Theorem:",
                "<theorem code>"
            ])
            
        return "\n".join(lines)

@dataclass
class TableTheorem:
    """A theorem about table property under an API"""
    api_name: Optional[str] = None
    description: Optional[str] = None
    theorem: Optional[LeanTheoremFile] = None
    theorem_negative: Optional[LeanTheoremFile] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "api_name": self.api_name,
            "description": self.description,
            "theorem": self.theorem.__dict__ if self.theorem else None,
            "theorem_negative": self.theorem_negative.__dict__ if self.theorem_negative else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TableTheorem':
        return cls(
            api_name=data.get('api_name'),
            description=data.get('description'),
            theorem=LeanTheoremFile(**data['theorem']) if data.get('theorem') else None,
            theorem_negative=LeanTheoremFile(**data['theorem_negative']) if data.get('theorem_negative') else None
        )

@dataclass
class TableProperty:
    """A property of a table"""
    description: Optional[str] = None
    theorems: List[TableTheorem] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "theorems": [thm.to_dict() for thm in self.theorems]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TableProperty':
        return cls(
            description=data.get('description'),
            theorems=[TableTheorem.from_dict(t) for t in data.get('theorems', [])]
        )

@dataclass
class Table:
    name: Optional[str] = None
    description: Optional[str] = None
    dependencies: Optional[Dependency] = None
    lean_structure: Optional[LeanStructureFile] = None
    properties: List[TableProperty] = field(default_factory=list)

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = Dependency()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "dependencies": self.dependencies.to_dict() if self.dependencies else None,
            "lean_structure": self.lean_structure.__dict__ if self.lean_structure else None,
            "properties": [prop.to_dict() for prop in self.properties]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Table':
        return cls(
            name=data.get('name'),
            description=data.get('description'),
            dependencies=Dependency.from_dict(data['dependencies']) if data.get('dependencies') else None,
            lean_structure=LeanStructureFile(**data['lean_structure']) if data.get('lean_structure') else None,
            properties=[TableProperty.from_dict(p) for p in data.get('properties', [])]
        )

    def to_markdown(self, show_fields: Dict[str, bool] = None) -> str:
        if show_fields is None:
            show_fields = {
                "description": True,
                "dependencies": False,  # Default to False
                "lean_structure": True,
                "properties": True
            }
            
        lines = [f"## Table: {self.name}"]
        
        if show_fields.get("description", True) and self.description:
            lines.extend([
                "\n### Description",
                "```yaml",
                self.description,
                "```"
            ])
            
        if show_fields.get("dependencies", True) and self.dependencies and any([
            self.dependencies.tables,
            self.dependencies.processes,
            self.dependencies.apis
        ]):
            lines.append("\n### Dependencies")
            if self.dependencies.tables:
                lines.extend([
                    "#### Tables:",
                    ", ".join(self.dependencies.tables)
                ])
            if self.dependencies.processes:
                lines.extend([
                    "#### Processes:",
                    ", ".join(self.dependencies.processes)
                ])
            if self.dependencies.apis:
                lines.extend([
                    "#### APIs:",
                    ", ".join([f"{d['service']}.{d['api']}" for d in self.dependencies.apis])
                ])
                
        if show_fields.get("lean_structure", True) and self.lean_structure:
            lines.extend([
                "\n### Lean Structure",
                self.lean_structure.to_markdown()
            ])
            
        if show_fields.get("properties", True) and self.properties:
            lines.append("\n### Properties")
            for prop in self.properties:
                lines.extend([
                    f"\n#### Property Description",
                    prop.description or "No description"
                ])
                for thm in prop.theorems:
                    lines.extend([
                        f"\n##### Theorem Description for API: {thm.api_name}",
                        thm.description or "No description",
                        "\n###### Positive Theorem:",
                        thm.theorem.to_markdown() if thm.theorem else "Not defined",
                        "\n###### Negative Theorem:",
                        thm.theorem_negative.to_markdown() if thm.theorem_negative else "Not defined"
                    ])
                    
        return "\n".join(lines)

    @staticmethod
    def get_markdown_structure(show_fields: Dict[str, bool] = None) -> str:
        if show_fields is None:
            show_fields = {
                "description": True,
                "dependencies": False,
                "lean_structure": True,
                "properties": True
            }
            
        lines = ["## Table: <name>"]
        
        if show_fields.get("description", True):
            lines.extend([
                "\n### Description",
                "```yaml",
                "<table description>",
                "```"
            ])
            
        if show_fields.get("dependencies", False):
            lines.extend([
                "\n### Dependencies",
                "#### Tables:",
                "<table1, table2, ...>",
                "#### Processes:",
                "<process1, process2, ...>",
                "#### APIs:",
                "<service1.api1, service2.api2, ...>"
            ])
            
        if show_fields.get("lean_structure", True):
            lines.extend([
                "\n### Lean Structure",
                "<lean structure code>"
            ])
            
        if show_fields.get("properties", True):
            lines.extend([
                "\n### Properties",
                "#### Property Description",
                "<property description>",
                "##### Theorem for API: <api_name>",
                "<theorem description>",
                "###### Positive Theorem:",
                "<theorem code>",
                "###### Negative Theorem:",
                "<theorem code>"
            ])
            
        return "\n".join(lines)

@dataclass
class Process:
    name: Optional[str] = None
    code: Optional[str] = None
    dependencies: Optional[Dependency] = None
    lean_function: Optional[LeanFunctionFile] = None

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = Dependency()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "code": self.code,
            "dependencies": self.dependencies.to_dict() if self.dependencies else None,
            "lean_function": self.lean_function.__dict__ if self.lean_function else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Process':
        return cls(
            name=data.get('name'),
            code=data.get('code'),
            dependencies=Dependency.from_dict(data['dependencies']) if data.get('dependencies') else None,
            lean_function=LeanFunctionFile(**data['lean_function']) if data.get('lean_function') else None
        )

    def to_markdown(self, show_fields: Dict[str, bool] = None) -> str:
        if show_fields is None:
            show_fields = {
                "code": True,
                "dependencies": False,  # Default to False
                "lean_function": True
            }
            
        lines = [f"## Process: {self.name}"]
        
        if show_fields.get("code", True) and self.code:
            lines.extend([
                "\n### Implementation",
                "```scala",
                self.code,
                "```"
            ])
            
        if show_fields.get("dependencies", True) and self.dependencies and any([
            self.dependencies.tables,
            self.dependencies.processes,
            self.dependencies.apis
        ]):
            lines.append("\n### Dependencies")
            if self.dependencies.tables:
                lines.extend([
                    "#### Tables:",
                    ", ".join(self.dependencies.tables)
                ])
            if self.dependencies.processes:
                lines.extend([
                    "#### Processes:",
                    ", ".join(self.dependencies.processes)
                ])
            if self.dependencies.apis:
                lines.extend([
                    "#### APIs:",
                    ", ".join([f"{d['service']}.{d['api']}" for d in self.dependencies.apis])
                ])
                
        if show_fields.get("lean_function", True) and self.lean_function:
            lines.extend([
                "\n### Lean Function",
                self.lean_function.to_markdown()
            ])
            
        return "\n".join(lines)

    @staticmethod
    def get_markdown_structure(show_fields: Dict[str, bool] = None) -> str:
        if show_fields is None:
            show_fields = {
                "code": True,
                "dependencies": False,
                "lean_function": True
            }
            
        lines = ["## Process: <name>"]
        
        if show_fields.get("code", True):
            lines.extend([
                "\n### Implementation",
                "```scala",
                "<process implementation>",
                "```"
            ])
            
        if show_fields.get("dependencies", False):
            lines.extend([
                "\n### Dependencies",
                "#### Tables:",
                "<table1, table2, ...>",
                "#### Processes:",
                "<process1, process2, ...>",
                "#### APIs:",
                "<service1.api1, service2.api2, ...>"
            ])
            
        if show_fields.get("lean_function", True):
            lines.extend([
                "\n### Lean Function",
                "<lean function code>"
            ])
            
        return "\n".join(lines)

@dataclass
class Service:
    """Service information"""
    name: Optional[str] = None
    apis: List[APIFunction] = field(default_factory=list)
    tables: List[Table] = field(default_factory=list)
    processes: List[Process] = field(default_factory=list)
    table_topological_order: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "apis": [api.to_dict() for api in self.apis],
            "tables": [table.to_dict() for table in self.tables],
            "processes": [process.to_dict() for process in self.processes],
            "table_topological_order": self.table_topological_order
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Service':
        return cls(
            name=data.get('name'),
            apis=[APIFunction.from_dict(a) for a in data.get('apis', [])],
            tables=[Table.from_dict(t) for t in data.get('tables', [])],
            processes=[Process.from_dict(p) for p in data.get('processes', [])],
            table_topological_order=data.get('table_topological_order', [])
        )

    def sort_tables(self) -> List[str]:
        """Sort tables based on dependencies and set table_topological_order"""
        # Build dependency graph
        graph = defaultdict(set)
        table_nodes = set()
        
        # Add all tables as nodes
        for table in self.tables:
            table_node = (table.name, table.dependencies.tables)
            table_nodes.add(table_node)
            
            # Add dependencies
            for dep in table.dependencies.tables:
                dep_node = (dep, table.name)
                graph[table_node].add(dep_node)

        # Topological sort
        sorted_tables = []
        visited = set()
        temp_visited = set()

        def visit(node):
            if node in temp_visited:
                raise ValueError(f"Circular dependency detected involving {node}")
            if node in visited:
                return
            
            temp_visited.add(node)

            for dep in graph[node]:
                if dep in table_nodes:
                    visit(dep)
            temp_visited.remove(node)
            visited.add(node)
            sorted_tables.append(node)

        # Visit all nodes
        for node in table_nodes:
            if node not in visited:
                visit(node)

        # Store the result and return it
        self.table_topological_order = list(reversed(sorted_tables))
        return self.table_topological_order

@dataclass
class ProjectStructure:
    """Complete project structure"""
    name: Optional[str] = None
    base_path: Optional[Path] = None
    lean_project_name: Optional[str] = None
    lean_project_path: Optional[Path] = None
    services: List[Service] = field(default_factory=list)
    api_topological_order: List[Tuple[str, str]] = field(default_factory=list)  # List of (service_name, api_name)

    def sort_apis(self) -> List[Tuple[str, str]]:
        """Sort all APIs across services based on dependencies
        
        Returns:
            List of (service_name, api_name) tuples in dependency order
        """
        # Build dependency graph
        graph = defaultdict(set)
        api_nodes = set()
        
        # Add all APIs as nodes
        for service in self.services:
            for api in service.apis:
                api_node = (service.name, api.name)
                api_nodes.add(api_node)
                
                # Add dependencies
                if api.dependencies:
                    for dep in api.dependencies.apis:
                        dep_node = (dep['service'], dep['api'])
                        graph[api_node].add(dep_node)

        # Topological sort
        sorted_apis = []
        visited = set()
        temp_visited = set()

        def visit(node):
            if node in temp_visited:
                raise ValueError(f"Circular dependency detected involving {node}")
            if node in visited:
                return
            
            temp_visited.add(node)
            for dep in graph[node]:
                if dep in api_nodes:  # Only visit if dep is a valid API
                    visit(dep)
            temp_visited.remove(node)
            visited.add(node)
            sorted_apis.append(node)

        # Visit all nodes
        for node in api_nodes:
            if node not in visited:
                visit(node)

        # Store the result and return it
        self.api_topological_order = list(reversed(sorted_apis))
        return self.api_topological_order

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "base_path": str(self.base_path) if self.base_path else None,
            "lean_project_name": self.lean_project_name,
            "lean_project_path": str(self.lean_project_path) if self.lean_project_path else None,
            "services": [service.to_dict() for service in self.services],
            "api_topological_order": self.api_topological_order
        }

    @classmethod
    def load(cls, path: Path) -> 'ProjectStructure':
        """Load project structure from JSON file"""
        with open(path) as f:
            data = json.load(f)
        
        # Convert paths if they exist
        if data.get('base_path'):
            data['base_path'] = Path(data['base_path'])
        if data.get('lean_project_path'):
            data['lean_project_path'] = Path(data['lean_project_path'])
        
        return cls(
            name=data.get('name'),
            base_path=data.get('base_path'),
            lean_project_name=data.get('lean_project_name'),
            lean_project_path=data.get('lean_project_path'),
            services=[Service.from_dict(s) for s in data.get('services', [])],
            api_topological_order=data.get('api_topological_order', [])
        )

    def save(self, path: Path) -> None:
        """Save project structure to JSON file"""
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False) 

    # Init project
    def _parse_service(self, service_name: str, doc_dir: Path, code_dir: Path) -> Service:
        """Parse a service directory to extract APIs, Tables and Processes"""
        service = Service(name=service_name)
        
        # Parse APIs
        api_root = code_dir / "src/main/scala/Impl" / service_name
        for planner_file in api_root.glob("*MessagePlanner.scala"):
            if not planner_file.is_file():
                continue
                
            api_name = planner_file.name.replace("MessagePlanner.scala", "")
            
            # Get planner code
            planner_code = planner_file.read_text()
                
            # Get message code
            message_code = None
            message_path = code_dir / "src/main/scala/APIs" / service_name / f"{api_name}Message.scala"
            if message_path.exists():
                message_code = message_path.read_text()
                
            service.apis.append(APIFunction(
                name=api_name,
                planner_code=planner_code,
                message_code=message_code
            ))
        
        # Parse Tables
        table_root = doc_dir / f"{service_name}-TableRoot"
        for table_dir in table_root.glob("*"):
            if not table_dir.is_dir():
                continue
                
            table_name = table_dir.name
            
            # Get table description
            description = None
            yaml_path = table_dir / f"{table_name}.yaml"
            if yaml_path.exists():
                description = yaml_path.read_text()
                
            service.tables.append(Table(
                name=table_name,
                description=description
            ))
        
        # Parse Processes
        # TODO: for now no process is parsed
        
        return service

    def load_source_repository(self) -> Tuple[bool, str]:
        """Load source code repository structure"""
        try:
            doc_path = self.base_path / self.name / self.name
            code_path = self.base_path / f"{self.name}Code"
            print(doc_path)
            print(code_path)
            print(self.name)

            # Parse each service directory
            for service_dir in doc_path.glob("*Service"):
                print(service_dir)
                if not service_dir.is_dir():
                    continue
                    
                service_name = service_dir.name
                service = self._parse_service(
                    service_name,
                    service_dir,
                    code_path / service_name
                )
                self.services.append(service)
                
            return True, "Source repository loaded successfully"
            
        except Exception as e:
            return False, f"Failed to load source repository: {str(e)}"

    def init_lean_repository(self, logger: Logger=None) -> Tuple[bool, str]:
        """Initialize Lean repository structure"""
        try:
            # Initialize project using manager
            success, message = LeanProjectManager.init_project(
                self.lean_project_path.parent,
                self.lean_project_name,
                with_mathlib=True
            )
            if not success and logger:
                logger.warning(f"Failed to initialize Lean repository: {message}")
                
            # Create Basic.lean
            basic_path = LeanProjectStructure.get_basic_path(self.lean_project_name)
            basic_file = LeanProjectStructure.to_file_path(self.lean_project_path, basic_path)
            basic_file.parent.mkdir(parents=True, exist_ok=True)
            basic_file.write_text("")
            
            # Create entry file
            entry_path = LeanProjectStructure.get_entry_path(self.lean_project_name)
            entry_file = LeanProjectStructure.to_file_path(self.lean_project_path, entry_path)
            entry_file.parent.mkdir(parents=True, exist_ok=True)
            entry_file.write_text(f"import {self.lean_project_name}.Basic")
            
            # Update and build
            success, message = LeanProjectManager._run_lake_update(self.lean_project_path)
            if not success:
                return False, message
                
            success, message = LeanProjectManager._run_lake_build(self.lean_project_path)
            if not success:
                return False, message
                
            return True, "Lean repository initialized successfully"
            
        except Exception as e:
            return False, f"Failed to initialize Lean repository: {str(e)}" 
        
