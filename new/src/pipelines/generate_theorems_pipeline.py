from enum import Enum, auto
from pathlib import Path
from typing import Optional
import asyncio
import argparse
import json

from src.pipelines.base import PipelineBase
from src.types.project import ProjectStructure
from src.generate_theorems.api_requirement_generator import APIRequirementGenerator
from src.generate_theorems.table_property_analyzer import TablePropertyAnalyzer
from src.generate_theorems.api_theorem_formalizer import APITheoremFormalizer
from src.generate_theorems.table_theorem_formalizer import TableTheoremFormalizer

class TheoremGenerationState(Enum):
    """Theorem generation pipeline states"""
    INIT = 0
    API_REQUIREMENTS = 1
    TABLE_PROPERTIES = 2
    API_THEOREMS = 3
    TABLE_THEOREMS = 4
    COMPLETED = 5

    def __le__(self, other):
        if not isinstance(other, TheoremGenerationState):
            return NotImplemented
        return self.value <= other.value

    def __lt__(self, other):
        if not isinstance(other, TheoremGenerationState):
            return NotImplemented
        return self.value < other.value


class TheoremGenerationPipeline(PipelineBase):
    """Pipeline for generating and formalizing theorems"""

    def __init__(self,
                 project_name: str,
                 formalize_output_path: str,
                 output_base_path: str,
                 model: str = "qwen-max",
                 api_theorem_retries: int = 3,
                 table_theorem_retries: int = 3,
                 doc_path: Optional[str] = None,
                 log_level: str = "INFO",
                 log_model_io: bool = False,
                 continue_from: bool = False,
                 start_state: Optional[str] = None):
        """Initialize theorem generation pipeline"""
        super().__init__(
            project_name=project_name,
            output_base_path=output_base_path,
            pipeline_dir="theorem_generation",
            log_level=log_level,
            log_model_io=log_model_io,
            continue_from=continue_from,
            start_state=start_state
        )
        
        self.formalize_output_path = formalize_output_path
        self.model = model
        self.api_theorem_retries = api_theorem_retries
        self.table_theorem_retries = table_theorem_retries
        self.doc_path = doc_path

    @property
    def state_enum(self) -> type[Enum]:
        return TheoremGenerationState

    def _print_project_brief(self, project: ProjectStructure) -> None:
        """Log project summary"""
        self.logger.info(f"Project: {self.project_name}")
        self.logger.info(f"Formalize output path: {self.formalize_output_path}")
        self.logger.info(f"Output base path: {self.output_path}")
        
        for service in project.services:
            self.logger.info(f"Service: {service.name}")
            self.logger.info(f"Number of tables: {len(service.tables)}")
            self.logger.info(f"Number of APIs: {len(service.apis)}")

    async def run(self) -> bool:
        """Run the complete theorem generation pipeline"""
        self.logger.info(f"Starting theorem generation pipeline for project: {self.project_name}")
        
        # Determine starting state
        start_state = self.validate_continuation()
        self.logger.info(f"Starting from state: {start_state.name}")
        
        # Load formalized project structure
        project = None
        if start_state == TheoremGenerationState.INIT:
            self.save_state(TheoremGenerationState.INIT)
            self.logger.info("1. Loading formalized project structure...")
            try:
                with open(self.formalize_output_path) as f:
                    project = ProjectStructure.from_dict(json.load(f))
                self._print_project_brief(project)
                self.save_output(TheoremGenerationState.INIT, project.to_dict())
                self.logger.info("Project structure loaded successfully")
            except Exception as e:
                self.logger.error(f"Failed to load project structure: {e}")
                return False

        # Generate API requirements
        if start_state <= TheoremGenerationState.API_REQUIREMENTS:
            self.save_state(TheoremGenerationState.API_REQUIREMENTS)
            self.logger.info("2. Generating API requirements...")
            if not project:
                project = ProjectStructure.from_dict(self.load_output(TheoremGenerationState.INIT))
            
            generator = APIRequirementGenerator(model=self.model)
            project = await generator.generate(project, self.doc_path, self.logger)
            self.save_output(TheoremGenerationState.API_REQUIREMENTS, project.to_dict())
            self.logger.info("API requirements generated")

        # Analyze table properties
        if start_state <= TheoremGenerationState.TABLE_PROPERTIES:
            self.save_state(TheoremGenerationState.TABLE_PROPERTIES)
            self.logger.info("3. Analyzing table properties...")
            if not project:
                project = ProjectStructure.from_dict(self.load_output(TheoremGenerationState.API_REQUIREMENTS))
            
            analyzer = TablePropertyAnalyzer(model=self.model)
            project = await analyzer.analyze(project, self.logger)
            self.save_output(TheoremGenerationState.TABLE_PROPERTIES, project.to_dict())
            self.logger.info("Table properties analyzed")

        # Formalize API theorems
        if start_state <= TheoremGenerationState.API_THEOREMS:
            self.save_state(TheoremGenerationState.API_THEOREMS)
            self.logger.info("4. Formalizing API theorems...")
            if not project:
                project = ProjectStructure.from_dict(self.load_output(TheoremGenerationState.TABLE_PROPERTIES))
            
            formalizer = APITheoremFormalizer(
                model=self.model,
                max_retries=self.api_theorem_retries
            )
            project = await formalizer.formalize(project, self.logger)
            self.save_output(TheoremGenerationState.API_THEOREMS, project.to_dict())
            self.logger.info("API theorems formalized")

        # Formalize table theorems
        if start_state <= TheoremGenerationState.TABLE_THEOREMS:
            self.save_state(TheoremGenerationState.TABLE_THEOREMS)
            self.logger.info("5. Formalizing table theorems...")
            if not project:
                project = ProjectStructure.from_dict(self.load_output(TheoremGenerationState.API_THEOREMS))
            
            formalizer = TableTheoremFormalizer(
                model=self.model,
                max_retries=self.table_theorem_retries
            )
            project = await formalizer.formalize(project, self.logger)
            self.save_output(TheoremGenerationState.TABLE_THEOREMS, project.to_dict())
            self.logger.info("Table theorems formalized")

        self.save_state(TheoremGenerationState.COMPLETED)

        if not project:
            project = ProjectStructure.from_dict(self.load_output(TheoremGenerationState.TABLE_THEOREMS))
        self.save_output(TheoremGenerationState.COMPLETED, project.to_dict())

        self.logger.info("Theorem generation pipeline completed successfully")
        return True
    
def main():
    """Command line interface"""
    parser = argparse.ArgumentParser(description="Run the theorem generation pipeline")
    
    # Project settings
    parser.add_argument("--project-name", required=True,
                      help="Name of the project")
    parser.add_argument("--formalize-output-path", 
                      default=None,
                      help="Path to formalization output (default: outputs/<project>/formalization/completed.json)")
    parser.add_argument("--output-base-path", default="outputs",
                      help="Base path for output files")
    parser.add_argument("--project-base-path", default="source_code",
                      help="Base path for project files")
    parser.add_argument("--doc-path", default=None,
                      help="Path to API documentation (default: <project-base-path>/<project-name>/doc.md)")
    
    # Model settings
    parser.add_argument("--model", default="qwen-max",
                      help="Model to use for analysis and formalization")
    parser.add_argument("--api-theorem-retries", type=int, default=5,
                      help="Maximum retries for API theorem formalizer")
    parser.add_argument("--table-theorem-retries", type=int, default=5,
                      help="Maximum retries for table theorem formalizer")
    
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
                      choices=[s.name for s in TheoremGenerationState],
                      help="Start from specific state (requires --continue)")
    
    args = parser.parse_args()
    
    if args.start_state and not args.continue_from:
        parser.error("--start-state requires --continue")

    # Set default formalize output path if not provided
    if not args.formalize_output_path:
        args.formalize_output_path = f"{args.output_base_path}/{args.project_name}/formalization/completed.json"

    if not args.doc_path:
        args.doc_path = f"{args.project_base_path}/{args.project_name}/doc.md"
    else:
        args.doc_path = Path(args.doc_path)
        if not args.doc_path.exists():
            parser.error(f"Documentation file does not exist: {args.doc_path}")

    pipeline = TheoremGenerationPipeline(
        project_name=args.project_name,
        formalize_output_path=args.formalize_output_path,
        output_base_path=args.output_base_path,
        model=args.model,
        doc_path=args.doc_path,
        api_theorem_retries=args.api_theorem_retries,
        table_theorem_retries=args.table_theorem_retries,
        log_level=args.log_level,
        log_model_io=args.log_model_io,
        continue_from=args.continue_from,
        start_state=args.start_state
    )
    
    success = asyncio.run(pipeline.run())
    exit(0 if success else 1)

if __name__ == "__main__":
    main() 