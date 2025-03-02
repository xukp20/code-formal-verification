from dataclasses import dataclass
from typing import Dict, List, Any, Optional
import json
from pathlib import Path

from src.pipeline.theorem.api.theorem_types import (
    TheoremTableInfo as BaseTheoremTableInfo,
    TheoremAPIInfo as BaseTheoremAPIInfo,
    TheoremServiceInfo as BaseTheoremServiceInfo,
    TheoremProjectStructure as BaseTheoremProjectStructure,
)
from src.pipeline.theorem.table.theorem_types import TableTheoremGenerationInfo

@dataclass
class ProverTableInfo(BaseTheoremTableInfo):
    """Table info with theorem proofs"""
    proved_theorems: List[Optional[str]] = None  # Proved versions of theorems
    
    def __post_init__(self):
        super().__post_init__()
        if self.proved_theorems is None:
            self.proved_theorems = [None] * len(self.lean_theorems)
    
    def to_dict(self) -> Dict[str, Any]:
        base_dict = super().to_dict()
        base_dict["proved_theorems"] = self.proved_theorems
        return base_dict
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProverTableInfo':
        instance = super().from_dict(data)
        instance.proved_theorems = data.get("proved_theorems", [None] * len(instance.lean_theorems))
        return instance

@dataclass
class ProverAPIInfo(BaseTheoremAPIInfo):
    """API info with theorem proofs"""
    proved_theorems: List[Optional[str]] = None  # Proved versions of theorems
    
    def __post_init__(self):
        super().__post_init__()
        if self.proved_theorems is None:
            self.proved_theorems = [None] * len(self.lean_theorems)
    
    def to_dict(self) -> Dict[str, Any]:
        base_dict = super().to_dict()
        base_dict["proved_theorems"] = self.proved_theorems
        return base_dict
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProverAPIInfo':
        instance = super().from_dict(data)
        instance.proved_theorems = data.get("proved_theorems", [None] * len(instance.lean_theorems))
        return instance
    
    def update_test_code(self) -> None:
        """Update lean_test_code based on current theorems and proofs"""
        if not self.lean_prefix:
            return
            
        code_parts = [self.lean_prefix]
        
        for idx, theorem in enumerate(self.lean_theorems):
            if idx < len(self.proved_theorems) and self.proved_theorems[idx]:
                code_parts.append(self.proved_theorems[idx])
            else:
                code_parts.append(theorem)
                
        self.lean_test_code = "\n\n".join(code_parts)

@dataclass
class ProverServiceInfo(BaseTheoremServiceInfo):
    """Service info with prover types"""
    apis: List[ProverAPIInfo]
    tables: List[ProverTableInfo]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProverServiceInfo':
        return cls(
            name=data["name"],
            apis=[ProverAPIInfo.from_dict(api) for api in data["apis"]],
            tables=[ProverTableInfo.from_dict(table) for table in data["tables"]],
            init_code=data.get("init_code")
        )

@dataclass
class ProverProjectStructure(BaseTheoremProjectStructure):
    """Project structure with theorem proving support"""
    services: List[ProverServiceInfo]
    
    @classmethod
    def from_project(cls, project: BaseTheoremProjectStructure) -> 'ProverProjectStructure':
        return cls(
            name=project.name,
            base_path=project.base_path,
            services=[ProverServiceInfo.from_dict(service.to_dict()) for service in project.services],
            lean_base_path=project.lean_base_path,
            lean_project_name=project.lean_project_name,
            lean_project_path=project.lean_project_path,
            package_path=project.package_path
        )
    
    def set_theorem_proof(self, kind: str, service_name: str, name: str, idx: int, proof: str) -> None:
        """Set proof for a theorem"""
        if kind == "api":
            api = self._find_api(service_name, name)
            if api:
                api.proved_theorems[idx] = proof
                api.update_test_code()
        elif kind == "table":
            table = self._find_table(name)
            if table:
                table.proved_theorems[idx] = proof
                table.update_test_code()
    
    def del_theorem_proof(self, kind: str, service_name: str, name: str, idx: int) -> None:
        """Delete proof for a theorem"""
        if kind == "api":
            api = self._find_api(service_name, name)
            if api:
                api.proved_theorems[idx] = None
                api.update_test_code()
        elif kind == "table":
            table = self._find_table(name)
            if table:
                table.proved_theorems[idx] = None
                table.update_test_code()

    def concat_test_lean_code(self, kind: str, service_name: str, name: str):
        """Concatenate test lean code for an API or table"""
        if kind == "api":
            api = self._find_api(service_name, name)
            if api:
                code_parts = [api.lean_prefix]
                for idx, theorem in enumerate(api.lean_theorems):
                    if idx < len(api.proved_theorems) and api.proved_theorems[idx]:
                        code_parts.append(api.proved_theorems[idx])
                    else:
                        code_parts.append(theorem)
                return "\n\n".join(code_parts)
        elif kind == "table":
            table = self._find_table(name)
            if table:
                code_parts = [table.lean_prefix]
                for idx, theorem in enumerate(table.lean_theorems):
                    if idx < len(table.proved_theorems) and table.proved_theorems[idx]:
                        code_parts.append(table.proved_theorems[idx])
                    else:
                        code_parts.append(theorem)
                return "\n\n".join(code_parts)
        return None

@dataclass
class APIProverInfo(TableTheoremGenerationInfo):
    """Information about API theorem proving"""
    project: ProverProjectStructure  # Override project type with prover version
    
    def __post_init__(self):
        super().__post_init__()
        if self.project and not isinstance(self.project, ProverProjectStructure):
            # Convert project to ProverProjectStructure if needed
            self.project = ProverProjectStructure.from_project(self.project)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'APIProverInfo':
        instance = super().from_dict(data)
        instance.project = ProverProjectStructure.from_dict(data["project"])
        return cls(
            **instance.__dict__
        )
    
    @classmethod
    def from_theorem_info(cls, theorem_info: TableTheoremGenerationInfo) -> 'APIProverInfo':
        """Create from theorem generation info"""
        return cls(
            project=ProverProjectStructure.from_project(theorem_info.project),
            dependencies=theorem_info.dependencies,
            topological_order=theorem_info.topological_order,
            formalized_tables=theorem_info.formalized_tables,
            api_table_dependencies=theorem_info.api_table_dependencies,
            api_dependencies=theorem_info.api_dependencies,
            api_topological_order=theorem_info.api_topological_order,
            formalized_apis=theorem_info.formalized_apis,
            api_docs=theorem_info.api_docs,
            api_requirements=theorem_info.api_requirements,
            table_properties=theorem_info.table_properties,
            formalized_theorem_apis=theorem_info.formalized_theorem_apis,
            formalized_theorem_tables=theorem_info.formalized_theorem_tables,
            table_theorem_dependencies=theorem_info.table_theorem_dependencies
        )
    
    def save(self, output_path: Path) -> None:
        """Save prover info to output directory"""
        save_path = output_path / "api_proofs.json"
        with open(save_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls, path: Path) -> 'APIProverInfo':
        """Load prover info from file"""
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data) 