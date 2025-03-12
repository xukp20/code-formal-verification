from enum import Enum, auto
from pathlib import Path
from typing import Optional
import asyncio
import argparse

from src.pipelines.base import PipelineBase
from src.types.project import ProjectStructure
from src.formalize.table_dependency_analyzer import TableDependencyAnalyzer
from src.formalize.table_formalizer import TableFormalizer
from src.formalize.api_table_dependency_analyzer import APITableDependencyAnalyzer
from src.formalize.api_dependency_analyzer import APIDependencyAnalyzer
from src.formalize.api_formalizer import APIFormalizer
from src.formalize.init_project import init_project

class FormalizationState(Enum):
    """Formalization pipeline states"""
    INIT = 0
    TABLE_DEPENDENCY = 1
    TABLE_FORMALIZATION = 2
    API_TABLE_DEPENDENCY = 3
    API_DEPENDENCY = 4
    API_FORMALIZATION = 5
    COMPLETED = 6

    def __le__(self, other):
        if not isinstance(other, FormalizationState):
            return NotImplemented
        return self.value <= other.value

    def __lt__(self, other):
        if not isinstance(other, FormalizationState):
            return NotImplemented
        return self.value < other.value


class FormalizationPipeline(PipelineBase):
    """Pipeline for formalizing project structure into Lean 4"""

    def __init__(self,
                 project_name: str,
                 project_base_path: str,
                 lean_base_path: str,
                 output_base_path: str,
                 model: str = "qwen-max-latest",
                 table_formalizer_retries: int = 3,
                 api_formalizer_retries: int = 5,
                 max_workers: int = 1,
                 log_level: str = "INFO",
                 log_model_io: bool = False,
                 continue_from: bool = False,
                 start_state: Optional[str] = None,
                 add_mathlib: bool = False):
        """Initialize formalization pipeline"""
        super().__init__(
            project_name=project_name,
            output_base_path=output_base_path,
            pipeline_dir="formalization",
            log_level=log_level,
            log_model_io=log_model_io,
            continue_from=continue_from,
            start_state=start_state
        )
        
        self.project_base_path = project_base_path
        self.lean_base_path = lean_base_path
        self.model = model
        self.table_formalizer_retries = table_formalizer_retries
        self.api_formalizer_retries = api_formalizer_retries
        self.max_workers = max_workers
        self.add_mathlib = add_mathlib

    @property
    def state_enum(self) -> type[Enum]:
        return FormalizationState

    def _print_project_brief(self, project: ProjectStructure) -> None:
        """Log project summary"""
        self.logger.info(f"Project: {self.project_name}")
        self.logger.info(f"Project base path: {self.project_base_path}")
        self.logger.info(f"Lean base path: {self.lean_base_path}")
        self.logger.info(f"Output base path: {self.output_path}")
        
        for service in project.services:
            self.logger.info(f"Service: {service.name}")
            self.logger.info(f"Number of tables: {len(service.tables)}")
            self.logger.info(f"Number of APIs: {len(service.apis)}")

    async def run(self) -> bool:
        """Run the complete formalization pipeline"""
        self.logger.info(f"Starting formalization pipeline for project: {self.project_name}")
        
        # Determine starting state
        start_state = self.validate_continuation()
        self.logger.info(f"Starting from state: {start_state.name}")
        
        # Initialize project structure
        project = None
        if start_state == FormalizationState.INIT:
            self.save_state(FormalizationState.INIT)
            self.logger.info("1. Parsing project structure...")
            success, message, project = init_project(
                project_name=self.project_name,
                base_path=self.project_base_path,
                lean_base_path=self.lean_base_path,
            )
            if not success:
                self.logger.warning(message)
                self.logger.warning("Trying to continue")
            
            self._print_project_brief(project)
            self.save_output(FormalizationState.INIT, project.to_dict())
            self.logger.info("Project structure parsed successfully")

        # Analyze table dependencies
        if start_state <= FormalizationState.TABLE_DEPENDENCY:
            self.save_state(FormalizationState.TABLE_DEPENDENCY)
            self.logger.info("2. Analyzing table dependencies...")
            if not project:
                project = ProjectStructure.from_dict(self.load_output(FormalizationState.INIT))
            
            analyzer = TableDependencyAnalyzer(model=self.model)
            project = await analyzer.analyze(project, self.logger)
            self.save_output(FormalizationState.TABLE_DEPENDENCY, project.to_dict())
            self.logger.info("Table dependencies analyzed")

        # Formalize tables
        if start_state <= FormalizationState.TABLE_FORMALIZATION:
            self.save_state(FormalizationState.TABLE_FORMALIZATION)
            self.logger.info("3. Formalizing tables...")
            if not project:
                project = ProjectStructure.from_dict(self.load_output(FormalizationState.TABLE_DEPENDENCY))
            
            formalizer = TableFormalizer(
                model=self.model,
                max_retries=self.table_formalizer_retries
            )
            project = await formalizer.formalize(project, self.logger)
            self.save_output(FormalizationState.TABLE_FORMALIZATION, project.to_dict())
            self.logger.info("Tables formalized")

        # Analyze API-table dependencies
        if start_state <= FormalizationState.API_TABLE_DEPENDENCY:
            self.save_state(FormalizationState.API_TABLE_DEPENDENCY)
            self.logger.info("4. Analyzing API-table dependencies...")
            if not project:
                project = ProjectStructure.from_dict(self.load_output(FormalizationState.TABLE_FORMALIZATION))
            
            analyzer = APITableDependencyAnalyzer(model=self.model)
            project = await analyzer.analyze(project, self.logger, max_workers=self.max_workers)
            self.save_output(FormalizationState.API_TABLE_DEPENDENCY, project.to_dict())
            self.logger.info("API-table dependencies analyzed")

        # Analyze API-API dependencies
        if start_state <= FormalizationState.API_DEPENDENCY:
            self.save_state(FormalizationState.API_DEPENDENCY)
            self.logger.info("5. Analyzing API-API dependencies...")
            if not project:
                project = ProjectStructure.from_dict(self.load_output(FormalizationState.API_TABLE_DEPENDENCY))
            
            analyzer = APIDependencyAnalyzer(model=self.model)
            project = await analyzer.analyze(project, self.logger, max_workers=self.max_workers)
            self.save_output(FormalizationState.API_DEPENDENCY, project.to_dict())
            self.logger.info("API-API dependencies analyzed")

        # Formalize APIs
        if start_state <= FormalizationState.API_FORMALIZATION:
            self.save_state(FormalizationState.API_FORMALIZATION)
            self.logger.info("6. Formalizing APIs...")
            if not project:
                project = ProjectStructure.from_dict(self.load_output(FormalizationState.API_DEPENDENCY))
            
            formalizer = APIFormalizer(
                model=self.model,
                max_retries=self.api_formalizer_retries
            )
            project = await formalizer.formalize(project, self.logger, max_workers=self.max_workers)
            self.save_output(FormalizationState.API_FORMALIZATION, project.to_dict())
            self.logger.info("APIs formalized")

        self.save_state(FormalizationState.COMPLETED)

        if not project:
            project = ProjectStructure.from_dict(self.load_output(FormalizationState.API_FORMALIZATION))
        self.save_output(FormalizationState.COMPLETED, project.to_dict())

        self.logger.info("Formalization pipeline completed successfully")
        return True
    
def main():
    """Command line interface"""
    parser = argparse.ArgumentParser(description="Run the formalization pipeline")
    
    # Project settings
    parser.add_argument("--project-name", required=True,
                      help="Name of the project to formalize")
    parser.add_argument("--project-base-path", default="source_code",
                      help="Base path of the source code")
    parser.add_argument("--lean-base-path", default="lean_project",
                      help="Base path for Lean project files")
    parser.add_argument("--output-base-path", default="outputs",
                      help="Base path for output files")
    
    # Model settings
    parser.add_argument("--model", default="gpt-4-1106-preview",
                      help="Model to use for analysis and formalization")
    parser.add_argument("--table-formalizer-retries", type=int, default=3,
                      help="Maximum retries for table formalizer")
    parser.add_argument("--api-formalizer-retries", type=int, default=8,
                      help="Maximum retries for API formalizer")
    
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
                      choices=[s.name for s in FormalizationState],
                      help="Start from specific state (requires --continue)")
        
    # Lean settings
    parser.add_argument("--add-mathlib", action="store_true",
                      help="Add mathlib to Lean project")
    
    # Add max_workers argument
    parser.add_argument("--max-workers", type=int, default=1,
                      help="Maximum number of parallel workers")
    
    args = parser.parse_args()
    
    if args.start_state and not args.continue_from:
        parser.error("--start-state requires --continue")

    pipeline = FormalizationPipeline(
        project_name=args.project_name,
        project_base_path=args.project_base_path,
        lean_base_path=args.lean_base_path,
        output_base_path=args.output_base_path,
        model=args.model,
        table_formalizer_retries=args.table_formalizer_retries,
        api_formalizer_retries=args.api_formalizer_retries,
        max_workers=args.max_workers,
        log_level=args.log_level,
        log_model_io=args.log_model_io,
        continue_from=args.continue_from,
        start_state=args.start_state,
        add_mathlib=args.add_mathlib
    )
    
    success = asyncio.run(pipeline.run())
    exit(0 if success else 1)

if __name__ == "__main__":
    main() 