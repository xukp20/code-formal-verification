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

from src.utils.parse_project.parser import ProjectStructure
from src.pipeline.theorem.api.generator import APIRequirementGenerator
from src.pipeline.theorem.api.types import APIRequirementGenerationInfo
from src.pipeline.api.types import APIFormalizationInfo
from src.pipeline.theorem.table.analyzer import TablePropertiesAnalyzer
from src.pipeline.theorem.table.types import TablePropertiesInfo
from src.pipeline.theorem.api.theorem_types import APITheoremGenerationInfo
from src.pipeline.theorem.api.formalizer import APITheoremFormalizer
from src.pipeline.theorem.table.formalizer import DBTheoremFormalizer
from src.pipeline.theorem.table.theorem_types import TableTheoremGenerationInfo

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
    API_REQUIREMENTS = 0
    TABLE_PROPERTIES = 1
    API_THEOREMS = 2
    TABLE_THEOREMS = 3
    COMPLETED = 4

    def __le__(self, other):
        if not isinstance(other, PipelineState):
            return NotImplemented
        return self.value <= other.value

    def __lt__(self, other):
        if not isinstance(other, PipelineState):
            return NotImplemented
        return self.value < other.value

class TheoremGenerationPipeline:
    """Complete theorem generation pipeline for a project"""
    
    def __init__(self, 
                 project_name: str,
                 project_base_path: str,
                 doc_path: str,
                 output_base_path: str,
                 model: str = "qwen-max-latest",
                 log_level: str = "INFO",
                 log_model_io: bool = False,
                 continue_from: str = None,
                 start_state: str = None,
                 api_theorem_max_retries: int = 5):
        self.project_name = project_name
        self.project_base_path = project_base_path
        self.doc_path = Path(doc_path)
        self.output_path = Path(output_base_path) / project_name / "theorem_generation"
        self.model = model
        self.continue_from = continue_from
        self.start_state = PipelineState[start_state] if start_state else None
        self.api_theorem_max_retries = api_theorem_max_retries


        # Create output directory
        self.output_path.mkdir(parents=True, exist_ok=True)
        
        self._init_logger(log_level, log_model_io)

    def _init_logger(self, log_level: str, log_model_io: bool):
        """Initialize logger"""
        self.logger = Logger("theorem_generation_pipeline")
        level = getattr(logging, log_level.upper())
        self.logger.setLevel(level)

        if log_model_io:
            self.logger.setLevel(min(level, MODEL_INPUT))

        stream_handler = StreamHandler()
        stream_handler.setLevel(level)
        formatter = Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        stream_handler.setFormatter(formatter)
        self.logger.addHandler(stream_handler)

    def _save_state(self, state: PipelineState):
        """Save current pipeline state"""
        state_file = self.output_path / "pipeline_state.json"
        with open(state_file, 'w') as f:
            json.dump({
                "state": state.name,
                "timestamp": str(datetime.datetime.now())
            }, f)

    def _get_current_state(self) -> Optional[PipelineState]:
        """Get the current pipeline state from saved state file"""
        state_file = self.output_path / "pipeline_state.json"
        if not state_file.exists():
            return None
        try:
            with open(state_file) as f:
                data = json.load(f)
            current_state = PipelineState[data["state"]]
            # Move to the next state since the current state is completed
            next_state_value = current_state.value + 1
            if next_state_value < len(PipelineState):
                return PipelineState(next_state_value)
            return PipelineState.COMPLETED
        except Exception as e:
            self.logger.error(f"Failed to load pipeline state: {e}")
            return None

    def _validate_continuation(self) -> PipelineState:
        """Validate and determine the starting state"""
        current_state = self._get_current_state()
        
        if not self.continue_from:
            return PipelineState.API_REQUIREMENTS
            
        if not current_state:
            raise ValueError("No saved state found but continuation was requested")
            
        if self.start_state:
            if self.start_state > current_state:
                raise ValueError(f"Cannot start from {self.start_state.name} as pipeline only reached {current_state.name}")
            return self.start_state
            
        return current_state

    async def _run_api_requirements(self) -> APIRequirementGenerationInfo:
        """Run API requirements generation step"""
        self.logger.info("1. Generating API requirements...")
        generator = APIRequirementGenerator(model=self.model)
        api_requirements = await generator.run(
            formalization_info=APIFormalizationInfo.load(Path(self.project_base_path) / self.project_name / "formalization" / "api_formalization.json"),
            doc_path=self.doc_path,
            output_path=self.output_path,
            logger=self.logger
        )
        self._save_state(PipelineState.API_REQUIREMENTS)
        self.logger.info("API requirements generated and saved")
        return api_requirements

    async def _run_table_properties(self, requirements_info: APIRequirementGenerationInfo) -> TablePropertiesInfo:
        """Run table properties analysis step"""
        self.logger.info("2. Analyzing table properties...")
        analyzer = TablePropertiesAnalyzer(model=self.model)
        table_properties = await analyzer.run(
            requirements_info=requirements_info,
            output_path=self.output_path,
            logger=self.logger
        )
        self._save_state(PipelineState.TABLE_PROPERTIES)
        self.logger.info("Table properties analyzed and saved")
        return table_properties

    async def _run_api_theorems(self, properties_info: TablePropertiesInfo) -> APITheoremGenerationInfo:
        """Run API theorem generation step"""
        self.logger.info("Starting API theorem generation")
        
        # Convert previous step info to theorem generation info
        theorem_info = APITheoremGenerationInfo.from_properties(properties_info)
        
        # Create formalizer
        formalizer = APITheoremFormalizer(
            model=self.model,
            max_retries=self.api_theorem_max_retries
        )
        
        # Run formalization
        result = await formalizer.run(
            info=theorem_info,
            output_path=self.output_path,
            logger=self.logger
        )
        
        self.logger.info("API theorem generation completed")
        return result

    async def _run_table_theorems(self, theorem_info: APITheoremGenerationInfo) -> TableTheoremGenerationInfo:
        """Run database theorem generation step"""
        self.logger.info("Starting database theorem generation")
        
        # Create formalizer
        formalizer = DBTheoremFormalizer(
            model=self.model,
            max_retries=self.api_theorem_max_retries
        )
        
        theorem_info = TableTheoremGenerationInfo.from_api_theorem_generation_info(theorem_info)
        # Run formalization
        result = await formalizer.run(
            info=theorem_info,
            output_path=self.output_path,
            logger=self.logger
        )
        
        self.logger.info("Database theorem generation completed")
        return result

    async def run(self):
        """Run the complete theorem generation pipeline"""
        self.logger.info(f"Starting theorem generation pipeline for project: {self.project_name}")
        
        # Determine starting state
        start_state = self._validate_continuation()
        self.logger.info(f"Starting from state: {start_state.name}")
        
        # Load formalization results first
        self.logger.info("Loading formalization results...")
        formalization_path = Path(self.project_base_path) / self.project_name / "formalization" / "api_formalization.json"
        if not formalization_path.exists():
            raise FileNotFoundError(f"Formalization results not found at: {formalization_path}")
        
        formalization_info = APIFormalizationInfo.load(formalization_path)
        self.logger.info("Formalization results loaded successfully")
        
        # 1. Generate API requirements
        api_requirements = None
        if start_state <= PipelineState.API_REQUIREMENTS:
            api_requirements = await self._run_api_requirements()
        else:
            api_requirements = APIRequirementGenerationInfo.load(self.output_path / "api_requirements.json")
        
        # 2. Analyze table properties
        table_properties = None
        if start_state <= PipelineState.TABLE_PROPERTIES:
            table_properties = await self._run_table_properties(api_requirements)
        else:
            table_properties = TablePropertiesInfo.load(self.output_path / "table_properties.json")
        
        # 3. Generate API theorems
        theorem_info = None
        if start_state <= PipelineState.API_THEOREMS:
            theorem_info = await self._run_api_theorems(table_properties)
        else:
            theorem_info = APITheoremGenerationInfo.load(self.output_path / "api_theorems.json")
        
        # 4. Generate DB theorems
        if start_state <= PipelineState.TABLE_THEOREMS:
            theorem_info = await self._run_table_theorems(theorem_info)
        
        self._save_state(PipelineState.COMPLETED)
        self.logger.info("Theorem generation pipeline completed successfully")
        return True


def main():
    parser = argparse.ArgumentParser(description="Run the complete theorem generation pipeline")
    
    parser.add_argument("--project-name", required=True,
                      help="Name of the project to analyze")
    parser.add_argument("--project-base-path", default=None,
                      help="Base path containing formalization results")
    parser.add_argument("--doc-path", required=True,
                      help="Path to the project documentation file")
    parser.add_argument("--output-base-path", default="outputs",
                      help="Base path for output files")
    parser.add_argument("--model", default="qwen-max-latest",
                      help="Model to use for analysis")
    parser.add_argument("--log-level", default="INFO",
                      choices=["DEBUG", "MODEL_INPUT", "MODEL_OUTPUT", "INFO", "WARNING", "ERROR", "CRITICAL"],
                      help="Set the logging level")
   
    parser.add_argument("--api-theorem-max-retries", type=int, default=5,
                      help="Maximum number of retries for API theorem formalization")
   
    parser.add_argument("--log-model-io", action="store_true",
                      help="Enable logging of model inputs and outputs")
    parser.add_argument("--continue", dest="continue_from", action="store_true",
                      help="Continue from last saved state")
    parser.add_argument("--start-state", choices=[s.name for s in PipelineState],
                      help="Start from specific state (requires --continue)")
    
    args = parser.parse_args()

    if not args.project_base_path:
        args.project_base_path = args.output_base_path
        
    if args.start_state and not args.continue_from:
        parser.error("--start-state requires --continue")
    
    pipeline = TheoremGenerationPipeline(
        project_name=args.project_name,
        project_base_path=args.project_base_path,
        doc_path=args.doc_path,
        output_base_path=args.output_base_path,
        model=args.model,
        log_level=args.log_level,
        log_model_io=args.log_model_io,
        continue_from=args.continue_from,
        start_state=args.start_state,
        api_theorem_max_retries=args.api_theorem_max_retries
    )
    
    success = asyncio.run(pipeline.run())
    exit(0 if success else 1)

if __name__ == "__main__":
    main() 