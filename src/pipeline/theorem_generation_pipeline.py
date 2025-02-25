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
    API_REQUIREMENTS = 1
    COMPLETED = 2

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
                 start_state: str = None):
        self.project_name = project_name
        self.project_base_path = project_base_path
        self.doc_path = Path(doc_path)
        self.output_path = Path(output_base_path) / project_name / "theorem_generation"
        self.model = model
        self.continue_from = continue_from
        self.start_state = PipelineState[start_state] if start_state else None
        
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
        """Run the complete theorem generation pipeline"""
        self.logger.info(f"Starting theorem generation pipeline for project: {self.project_name}")
        
        try:
            # Determine starting state
            start_state = self._validate_continuation()
            self.logger.info(f"Starting from state: {start_state.name}")
            
            # 1. Load project structure from formalization results
            project = None
            if start_state <= PipelineState.INIT:
                self.logger.info("1. Loading project structure from formalization results...")
                formalization_path = Path(self.project_base_path) / self.project_name / "formalization" / "api_formalization.json"
                with open(formalization_path) as f:
                    data = json.load(f)
                    project = ProjectStructure.from_dict(data["project"])
                self._save_state(PipelineState.INIT)
                self.logger.info("Project structure loaded successfully")

            # 2. Generate API requirements
            api_requirements = None
            if start_state <= PipelineState.API_REQUIREMENTS:
                self.logger.info("2. Generating API requirements...")
                if not project:
                    project = ProjectStructure.load(self.output_path / "project_structure.json")
                generator = APIRequirementGenerator(model=self.model)
                api_requirements = await generator.run(
                    project=project,
                    doc_path=self.doc_path,
                    output_path=self.output_path,
                    logger=self.logger
                )
                self._save_state(PipelineState.API_REQUIREMENTS)
                self.logger.info("API requirements generated and saved")

            self._save_state(PipelineState.COMPLETED)
            self.logger.info("Theorem generation pipeline completed successfully")
            return True

        except Exception as e:
            self.logger.error(f"Pipeline failed: {str(e)}")
            return False

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
        start_state=args.start_state
    )
    
    success = asyncio.run(pipeline.run())
    exit(0 if success else 1)

if __name__ == "__main__":
    main() 