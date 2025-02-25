import asyncio
import argparse
from pathlib import Path
from logging import Logger, INFO, DEBUG, StreamHandler, Formatter, addLevelName
import os
import logging
import json
from enum import Enum, auto
from typing import Optional
import datetime

from src.utils.parse_project.parser import ProjectStructure, LoadSettings
from src.pipeline.table.types import TableDependencyInfo, TableFormalizationInfo
from src.pipeline.table.analyzer import TableDependencyAnalyzer
from src.pipeline.table.formalizer import TableFormalizer
from src.pipeline.api.types import APIDependencyInfo, APIFormalizationInfo
from src.pipeline.api.table_analyzer import APITableDependencyAnalyzer
from src.pipeline.api.api_analyzer import APIAnalyzer
from src.pipeline.api.formalizer import APIFormalizer

# Define custom log levels
MODEL_INPUT = 15  # Between DEBUG and INFO
MODEL_OUTPUT = 16
addLevelName(MODEL_INPUT, 'MODEL_INPUT')
addLevelName(MODEL_OUTPUT, 'MODEL_OUTPUT')

# Add custom logging methods
def model_input(self, message, *args, **kwargs):
    if self.isEnabledFor(MODEL_INPUT):
        self._log(MODEL_INPUT, message, args, **kwargs)

def model_output(self, message, *args, **kwargs):
    if self.isEnabledFor(MODEL_OUTPUT):
        self._log(MODEL_OUTPUT, message, args, **kwargs)

# Add methods to Logger class
Logger.model_input = model_input
Logger.model_output = model_output

class PipelineState(Enum):
    """Pipeline execution states"""
    INIT = 0
    TABLE_DEPENDENCY = 1
    TABLE_FORMALIZATION = 2
    API_TABLE_DEPENDENCY = 3
    API_DEPENDENCY = 4
    API_FORMALIZATION = 5
    COMPLETED = 6

    def __le__(self, other):
        if not isinstance(other, PipelineState):
            return NotImplemented
        return self.value <= other.value

    def __lt__(self, other):
        if not isinstance(other, PipelineState):
            return NotImplemented
        return self.value < other.value

class FormalizationPipeline:
    """Complete formalization pipeline for a project"""
    
    def __init__(self, 
                 project_name: str,
                 project_base_path: str,
                 lean_base_path: str,
                 output_base_path: str,
                 load_settings: LoadSettings,
                 model: str = "qwen-max-latest",
                 table_formalizer_retries: int = 3,
                 api_formalizer_retries: int = 5,
                 log_level: str = "INFO",
                 log_model_io: bool = False,
                 continue_from: str = None,
                 start_state: str = None):
        self.project_name = project_name
        self.project_base_path = project_base_path
        self.lean_base_path = lean_base_path
        self.output_path = Path(output_base_path) / project_name
        self.model = model
        self.table_formalizer_retries = table_formalizer_retries
        self.api_formalizer_retries = api_formalizer_retries
        self.continue_from = continue_from
        self.start_state = PipelineState[start_state] if start_state else None
        self.load_settings = load_settings
        
        # Create output directory
        self.output_path.mkdir(parents=True, exist_ok=True)
        
        self._init_logger(log_level, log_model_io)

    def _init_logger(self, log_level: str, log_model_io: bool):
        """Initialize logger"""
        self.logger = Logger("formalization_pipeline")
        level = getattr(logging, log_level.upper())
        self.logger.setLevel(level)

        if log_model_io:
            self.logger.setLevel(min(level, MODEL_INPUT))

        stream_handler = StreamHandler()
        stream_handler.setLevel(level)
        formatter = Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        stream_handler.setFormatter(formatter)
        self.logger.addHandler(stream_handler)

    def _print_project_brief(self, project: ProjectStructure):
        """See number of services and numbers of tables and apis in each of them"""
        self.logger.info(f"Project: {self.project_name}")
        self.logger.info(f"Project base path: {self.project_base_path}")
        self.logger.info(f"Lean base path: {self.lean_base_path}")
        self.logger.info(f"Output base path: {self.output_path}")
        
        for service in project.services:
            self.logger.info(f"Service: {service.name}")
            self.logger.info(f"Number of tables: {len(service.tables)}")
            self.logger.info(f"Number of apis: {len(service.apis)}")

    def _save_state(self, state: PipelineState):
        """Save current pipeline state"""
        state_file = self.output_path / "pipeline_state.json"
        with open(state_file, 'w') as f:
            json.dump({
                "state": state.name,
                "timestamp": str(datetime.datetime.now())
            }, f)

    def _load_state(self) -> Optional[PipelineState]:
        """Load saved pipeline state"""
        state_file = self.output_path / "pipeline_state.json"
        if not state_file.exists():
            return None
        try:
            with open(state_file) as f:
                data = json.load(f)
                return PipelineState[data["state"]]
        except Exception as e:
            self.logger.error(f"Failed to load pipeline state: {e}")
            return None

    def _validate_continuation(self) -> PipelineState:
        """Validate and determine the starting state"""
        current_state = self._load_state()
        
        if not self.continue_from:
            return PipelineState.INIT
            
        if not current_state:
            raise ValueError("No saved state found but continuation was requested")
            
        if self.start_state:
            if self.start_state > current_state:
                raise ValueError(f"Cannot start from {self.start_state.name} as pipeline only reached {current_state.name}")
            return self.start_state
            
        return current_state

    async def run(self):
        """Run the complete formalization pipeline"""
        self.logger.info(f"Starting formalization pipeline for project: {self.project_name}")
        
        try:
            # Determine starting state
            start_state = self._validate_continuation()
            self.logger.info(f"Starting from state: {start_state.name}")
            
            # 1. Parse project structure
            project = None
            if start_state <= PipelineState.INIT:
                self.logger.info("1. Parsing project structure...")
                project = ProjectStructure.parse_project(
                    project_name=self.project_name,
                    base_path=self.project_base_path + "/" + self.project_name,
                    lean_base_path=self.lean_base_path
                )
                init_success = project.init_lean()
                if not init_success:
                    self.logger.warning("Failed to initialize Lean project")
                    return False
                self._save_state(PipelineState.INIT)
                self.logger.info("Project structure parsed successfully")

            # 2. Analyze table dependencies
            table_dependency = None
            if start_state <= PipelineState.TABLE_DEPENDENCY:
                self.logger.info("2. Analyzing table dependencies...")
                if not project:
                    project = ProjectStructure.load(self.output_path / "project_structure.json")
                table_analyzer = TableDependencyAnalyzer(model=self.model)
                table_dependency = await table_analyzer.run(project, self.logger)
                table_dependency.save(self.output_path / "table_dependency.json")
                self._save_state(PipelineState.TABLE_DEPENDENCY)
                self.logger.info("Table dependencies analyzed and saved")

            # Continue with similar pattern for other steps...
            # 3. Formalize tables
            table_formalization = None
            if start_state <= PipelineState.TABLE_FORMALIZATION:
                self.logger.info("3. Formalizing tables...")
                if not table_dependency:
                    table_dependency = TableDependencyInfo.load(self.output_path / "table_dependency.json")
                table_formalizer = TableFormalizer(
                    model=self.model,
                    max_retries=self.table_formalizer_retries
                )
                table_formalization = await table_formalizer.run(table_dependency, self.logger)
                table_formalization.save(self.output_path / "table_formalization.json")
                self._save_state(PipelineState.TABLE_FORMALIZATION)
                self.logger.info("Tables formalized and saved")

            # 4. Analyze API-table dependencies
            api_table_dependency = None
            if start_state <= PipelineState.API_TABLE_DEPENDENCY:
                self.logger.info("4. Analyzing API-table dependencies...")
                if not table_formalization:
                    table_formalization = TableFormalizationInfo.load(self.output_path / "table_formalization.json")
                api_table_analyzer = APITableDependencyAnalyzer(model=self.model)
                api_table_dependency = await api_table_analyzer.run(table_formalization, self.logger)
                api_table_dependency.save(self.output_path / "api_table_dependency.json")
                self._save_state(PipelineState.API_TABLE_DEPENDENCY)
                self.logger.info("API-table dependencies analyzed and saved")

            # 5. Analyze API-API dependencies
            api_dependency = None
            if start_state <= PipelineState.API_DEPENDENCY:
                self.logger.info("5. Analyzing API-API dependencies...")
                if not api_table_dependency:
                    api_table_dependency = APIDependencyInfo.load(self.output_path / "api_table_dependency.json")
                api_analyzer = APIAnalyzer(model=self.model)
                api_dependency = await api_analyzer.run(api_table_dependency, self.logger)
                api_dependency.save(self.output_path / "api_dependency.json")
                self._save_state(PipelineState.API_DEPENDENCY)
                self.logger.info("API-API dependencies analyzed and saved")

            # 6. Formalize APIs
            api_formalization = None
            if start_state <= PipelineState.API_FORMALIZATION:
                self.logger.info("6. Formalizing APIs...")
                if not api_dependency:
                    api_dependency = APIDependencyInfo.load(self.output_path / "api_dependency.json")
                api_formalizer = APIFormalizer(
                    model=self.model,
                    max_retries=self.api_formalizer_retries
                )
                api_formalization = await api_formalizer.run(api_dependency, self.logger)
                api_formalization.save(self.output_path / "api_formalization.json")
                self._save_state(PipelineState.API_FORMALIZATION)
                self.logger.info("APIs formalized and saved")

            self._save_state(PipelineState.COMPLETED)
            self.logger.info("Formalization pipeline completed successfully")
            return True

        except Exception as e:
            self.logger.error(f"Pipeline failed: {str(e)}")
            return False

def main():
    parser = argparse.ArgumentParser(description="Run the complete formalization pipeline")
    
    parser.add_argument("--project-name", required=True,
                      help="Name of the project to formalize")
    parser.add_argument("--project-base-path", default="source_code",
                      help="Base path of the source code")
    parser.add_argument("--lean-base-path", default="lean_project",
                      help="Base path for Lean project files")
    parser.add_argument("--output-base-path", default="outputs",
                      help="Base path for output files")
    parser.add_argument("--model", default="qwen-max-latest",
                      help="Model to use for analysis and formalization")
    parser.add_argument("--table-formalizer-retries", type=int, default=3,
                      help="Maximum retries for table formalizer")
    parser.add_argument("--api-formalizer-retries", type=int, default=5,
                      help="Maximum retries for API formalizer")
    parser.add_argument("--log-level", default="INFO",
                      choices=["DEBUG", "MODEL_INPUT", "MODEL_OUTPUT", "INFO", "WARNING", "ERROR", "CRITICAL"],
                      help="Set the logging level")
    parser.add_argument("--log-model-io", action="store_true",
                      help="Enable logging of model inputs and outputs")
    parser.add_argument("--continue", dest="continue_from", action="store_true",
                      help="Continue from last saved state")
    parser.add_argument("--start-state", choices=[s.name for s in PipelineState],
                      help="Start from specific state (requires --continue)")
    
    # Add loading settings arguments
    parser.add_argument("--load-table-code", action="store_true",
                      help="Load table Scala code")
    parser.add_argument("--load-message-description", action="store_true",
                      help="Load API message descriptions")
    parser.add_argument("--load-planner-description", action="store_true",
                      help="Load API planner descriptions")
    parser.add_argument("--load-message-typescript", action="store_true",
                      help="Load API TypeScript message definitions")
    
    args = parser.parse_args()
    
    if args.start_state and not args.continue_from:
        parser.error("--start-state requires --continue")
    
    # Create LoadSettings
    load_settings = LoadSettings(
        table_code=args.load_table_code,
        message_description=args.load_message_description,
        planner_description=args.load_planner_description,
        message_typescript=args.load_message_typescript,
        message_code=True  # Always True for API formalization
    )
    
    pipeline = FormalizationPipeline(
        project_name=args.project_name,
        project_base_path=args.project_base_path,
        lean_base_path=args.lean_base_path,
        output_base_path=args.output_base_path,
        load_settings=load_settings,
        model=args.model,
        table_formalizer_retries=args.table_formalizer_retries,
        api_formalizer_retries=args.api_formalizer_retries,
        log_level=args.log_level,
        log_model_io=args.log_model_io,
        continue_from=args.continue_from,
        start_state=args.start_state
    )
    
    success = asyncio.run(pipeline.run())
    exit(0 if success else 1)

if __name__ == "__main__":
    main() 