from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from pathlib import Path
import json

from src.pipeline.prove.api.types import APIProverInfo
from src.utils.parse_project.parser import ProjectStructure

@dataclass
class TableProverInfo(APIProverInfo):
    """Information about table theorem proving progress"""
    
    def save(self, output_path: Path) -> None:
        """Save table prover info to output directory"""
        save_path = output_path / "table_proofs.json"
        with open(save_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls, path: Path) -> 'TableProverInfo':
        """Load table prover info from file"""
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)
    
    @classmethod
    def from_api_prover_info(cls, api_prover_info: APIProverInfo) -> 'TableProverInfo':
        """Create table prover info from API prover info"""
        return cls(
            project=api_prover_info.project,
            dependencies=api_prover_info.dependencies,
            topological_order=api_prover_info.topological_order,
            formalized_tables=api_prover_info.formalized_tables,
            api_table_dependencies=api_prover_info.api_table_dependencies,
            api_dependencies=api_prover_info.api_dependencies,
            api_topological_order=api_prover_info.api_topological_order,
            formalized_apis=api_prover_info.formalized_apis,
            api_docs=api_prover_info.api_docs,
            api_requirements=api_prover_info.api_requirements,
            table_properties=api_prover_info.table_properties,
            formalized_theorem_apis=api_prover_info.formalized_theorem_apis,
            formalized_theorem_tables=api_prover_info.formalized_theorem_tables,
            table_theorem_dependencies=api_prover_info.table_theorem_dependencies
        ) 