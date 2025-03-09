from enum import Enum, auto
from pathlib import Path
from typing import Optional
import asyncio
import argparse
import json

from src.pipelines.base import PipelineBase
from src.types.project import ProjectStructure
# from src.prove.api_theorem_prover import APITheoremProver
from src.prove.api_theorem_prover_v2 import APITheoremProver
from src.prove.table_theorem_prover import TableTheoremProver
from src.prove.api_negative_theorem_generator import APINegativeTheoremGenerator
from src.prove.table_negative_theorem_generator import TableNegativeTheoremGenerator

class ProveState(Enum):
    """Prove pipeline states"""
    INIT = 0
    API_THEOREMS = 1
    API_NEGATIVE_GENERATION = 2
    API_NEGATIVE_THEOREMS = 3
    TABLE_THEOREMS = 4
    TABLE_NEGATIVE_GENERATION = 5
    TABLE_NEGATIVE_THEOREMS = 6
    COMPLETED = 7

    def __le__(self, other):
        if not isinstance(other, ProveState):
            return NotImplemented
        return self.value <= other.value

    def __lt__(self, other):
        if not isinstance(other, ProveState):
            return NotImplemented
        return self.value < other.value


class ProvePipeline(PipelineBase):
    """Pipeline for proving theorems"""

    def __init__(self,
                 project_name: str,
                 theorem_output_path: str,
                 output_base_path: str,
                 model: str = "qwen-max-latest",
                 max_theorem_retries: int = 3,
                 max_examples: int = 5,
                 max_global_attempts: int = 3,
                 log_level: str = "INFO",
                 log_model_io: bool = False,
                 continue_from: bool = False,
                 start_state: Optional[str] = None):
        """Initialize prove pipeline"""
        super().__init__(
            project_name=project_name,
            output_base_path=output_base_path,
            pipeline_dir="prove",
            log_level=log_level,
            log_model_io=log_model_io,
            continue_from=continue_from,
            start_state=start_state
        )
        
        self.theorem_output_path = theorem_output_path
        self.model = model
        self.max_theorem_retries = max_theorem_retries
        self.max_examples = max_examples
        self.max_global_attempts = max_global_attempts

    @property
    def state_enum(self) -> type[Enum]:
        return ProveState

    def _print_project_brief(self, project: ProjectStructure) -> None:
        """Log project summary"""
        self.logger.info(f"Project: {self.project_name}")
        self.logger.info(f"Theorem output path: {self.theorem_output_path}")
        self.logger.info(f"Output base path: {self.output_path}")
        
        for service in project.services:
            self.logger.info(f"Service: {service.name}")
            api_theorems = sum(len(api.theorems) for api in service.apis)
            all_table_theorems = [theorem for table in service.tables for property in table.properties for theorem in property.theorems]
            table_theorems = len(all_table_theorems)
            self.logger.info(f"Number of API theorems: {api_theorems}")
            self.logger.info(f"Number of table theorems: {table_theorems}")

    async def run(self) -> bool:
        """Run the complete prove pipeline"""
        self.logger.info(f"Starting prove pipeline for project: {self.project_name}")
        
        # Determine starting state
        start_state = self.validate_continuation()
        self.logger.info(f"Starting from state: {start_state.name}")
        
        # Load theorem project structure
        project = None
        if start_state == ProveState.INIT:
            self.save_state(ProveState.INIT)
            self.logger.info("1. Loading theorem project structure...")
            with open(self.theorem_output_path) as f:
                project = ProjectStructure.from_dict(json.load(f))
            self._print_project_brief(project)
            self.save_output(ProveState.INIT, project.to_dict())
            self.logger.info("Project structure loaded successfully")

        # Prove API theorems
        if start_state <= ProveState.API_THEOREMS:
            self.save_state(ProveState.API_THEOREMS)
            self.logger.info("2. Proving API theorems...")
            if not project:
                project = ProjectStructure.from_dict(self.load_output(ProveState.INIT))
            
            prover = APITheoremProver(
                model=self.model,
                max_retries=self.max_theorem_retries,
                max_examples=self.max_examples,
                max_global_attempts=self.max_global_attempts
            )
            project = await prover.prove(project, negative=False, logger=self.logger)
            self.save_output(ProveState.API_THEOREMS, project.to_dict())
            self.logger.info("API theorems proved")

        # Generate API negative theorems
        if start_state <= ProveState.API_NEGATIVE_GENERATION:
            self.save_state(ProveState.API_NEGATIVE_GENERATION)
            self.logger.info("3. Generating API negative theorems...")
            if not project:
                project = ProjectStructure.from_dict(self.load_output(ProveState.API_THEOREMS))
            
            generator = APINegativeTheoremGenerator(
                model=self.model,
                max_retries=self.max_theorem_retries
            )
            project = await generator.generate(project, logger=self.logger)
            self.save_output(ProveState.API_NEGATIVE_GENERATION, project.to_dict())
            self.logger.info("API negative theorems generated")

        # Prove API negative theorems
        if start_state <= ProveState.API_NEGATIVE_THEOREMS:
            self.save_state(ProveState.API_NEGATIVE_THEOREMS)
            self.logger.info("4. Proving API negative theorems...")
            if not project:
                project = ProjectStructure.from_dict(self.load_output(ProveState.API_NEGATIVE_GENERATION))
            
            prover = APITheoremProver(
                model=self.model,
                max_retries=self.max_theorem_retries,
                max_examples=self.max_examples,
                max_global_attempts=self.max_global_attempts
            )
            project = await prover.prove(project, negative=True, logger=self.logger)
            self.save_output(ProveState.API_NEGATIVE_THEOREMS, project.to_dict())
            self.logger.info("API negative theorems proved")

        # Prove table theorems
        if start_state <= ProveState.TABLE_THEOREMS:
            self.save_state(ProveState.TABLE_THEOREMS)
            self.logger.info("5. Proving table theorems...")
            if not project:
                project = ProjectStructure.from_dict(self.load_output(ProveState.API_NEGATIVE_THEOREMS))
            
            prover = TableTheoremProver(
                model=self.model,
                max_retries=self.max_theorem_retries,
                max_examples=self.max_examples,
                max_global_attempts=self.max_global_attempts
            )
            project = await prover.prove(project, negative=False, logger=self.logger)
            self.save_output(ProveState.TABLE_THEOREMS, project.to_dict())
            self.logger.info("Table theorems proved")

        # Generate table negative theorems
        if start_state <= ProveState.TABLE_NEGATIVE_GENERATION:
            self.save_state(ProveState.TABLE_NEGATIVE_GENERATION)
            self.logger.info("6. Generating table negative theorems...")
            if not project:
                project = ProjectStructure.from_dict(self.load_output(ProveState.TABLE_THEOREMS))
            
            generator = TableNegativeTheoremGenerator(
                model=self.model,
                max_retries=self.max_theorem_retries
            )
            project = await generator.generate(project, logger=self.logger)
            self.save_output(ProveState.TABLE_NEGATIVE_GENERATION, project.to_dict())
            self.logger.info("Table negative theorems generated")

        # Prove table negative theorems
        if start_state <= ProveState.TABLE_NEGATIVE_THEOREMS:
            self.save_state(ProveState.TABLE_NEGATIVE_THEOREMS)
            self.logger.info("7. Proving table negative theorems...")
            if not project:
                project = ProjectStructure.from_dict(self.load_output(ProveState.TABLE_NEGATIVE_GENERATION))
            
            prover = TableTheoremProver(
                model=self.model,
                max_retries=self.max_theorem_retries,
                max_examples=self.max_examples,
                max_global_attempts=self.max_global_attempts
            )
            project = await prover.prove(project, negative=True, logger=self.logger)
            self.save_output(ProveState.TABLE_NEGATIVE_THEOREMS, project.to_dict())
            self.logger.info("Table negative theorems proved")

        self.save_state(ProveState.COMPLETED)
        if not project:
            project = ProjectStructure.from_dict(self.load_output(ProveState.TABLE_NEGATIVE_THEOREMS))
        self.save_output(ProveState.COMPLETED, project.to_dict())

        self.logger.info("Prove pipeline completed successfully")
        return True
    
def main():
    """Command line interface"""
    parser = argparse.ArgumentParser(description="Run the prove pipeline")
    
    # Project settings
    parser.add_argument("--project-name", required=True,
                      help="Name of the project")
    parser.add_argument("--theorem-output-path", 
                      default=None,
                      help="Path to theorem generation output (default: outputs/<project>/theorem_generation/completed.json)")
    parser.add_argument("--output-base-path", default="outputs",
                      help="Base path for output files")
    
    # Model settings
    parser.add_argument("--model", default="qwen-max-latest",
                      help="Model to use for proving")
    parser.add_argument("--max-theorem-retries", type=int, default=3,
                      help="Maximum retries for each theorem")
    parser.add_argument("--max-examples", type=int, default=5,
                      help="Maximum number of example proofs to collect")
    parser.add_argument("--max-global-attempts", type=int, default=3,
                      help="Maximum global attempts with new examples")
    
    # Logging settings
    parser.add_argument("--log-level", default="INFO",
                      choices=["DEBUG", "MODEL_INPUT", "MODEL_OUTPUT", "INFO", "WARNING", "ERROR", "CRITICAL"],
                      help="Set the logging level")
    parser.add_argument("--log-model-io", action="store_true",
                      help="Enable logging of model inputs and outputs")
    
    # Pipeline control
    parser.add_argument("--continue", dest="continue_from", action="store_true",
                      help="Continue from last saved state")
    parser.add_argument("--start-state", 
                      choices=[s.name for s in ProveState],
                      help="Start from specific state (requires --continue)")
    
    args = parser.parse_args()
    
    if args.start_state and not args.continue_from:
        parser.error("--start-state requires --continue")

    # Set default theorem output path if not provided
    if not args.theorem_output_path:
        args.theorem_output_path = f"{args.output_base_path}/{args.project_name}/theorem_generation/completed.json"

    pipeline = ProvePipeline(
        project_name=args.project_name,
        theorem_output_path=args.theorem_output_path,
        output_base_path=args.output_base_path,
        model=args.model,
        max_theorem_retries=args.max_theorem_retries,
        max_examples=args.max_examples,
        max_global_attempts=args.max_global_attempts,
        log_level=args.log_level,
        log_model_io=args.log_model_io,
        continue_from=args.continue_from,
        start_state=args.start_state
    )
    
    success = asyncio.run(pipeline.run())
    exit(0 if success else 1)

if __name__ == "__main__":
    main() 