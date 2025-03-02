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

from src.pipeline.prove.api.prover import APIProver
from src.pipeline.prove.api.types import APIProverInfo
from src.pipeline.theorem.table.theorem_types import TableTheoremGenerationInfo
from src.pipeline.prove.table.prover import TableTheoremProver

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
    API_PROOFS = 0
    TABLE_PROOFS = 1
    COMPLETED = 2

    def __le__(self, other):
        if not isinstance(other, PipelineState):
            return NotImplemented
        return self.value <= other.value
    
    def __ge__(self, other):
        if not isinstance(other, PipelineState):
            return NotImplemented
        return self.value >= other.value
    
    def __gt__(self, other):
        if not isinstance(other, PipelineState):
            return NotImplemented
        return self.value > other.value
    
    def __lt__(self, other):
        if not isinstance(other, PipelineState):
            return NotImplemented
        return self.value < other.value

    def __eq__(self, other):
        if not isinstance(other, PipelineState):
            return NotImplemented
        return self.value == other.value
    

class TheoremProvingPipeline:
    """Complete theorem proving pipeline for a project"""
    
    def __init__(self, 
                 project_name: str,
                 project_base_path: str,
                 output_base_path: str,
                 model: str = "qwen-max-latest",
                 log_level: str = "INFO",
                 log_model_io: bool = False,
                 continue_from: str = None,
                 start_state: str = None,
                 api_prover_max_retries: int = 5,
                 api_prover_max_theorem_retries: int = 4,
                 table_prover_max_retries: int = 5,
                 table_prover_max_theorem_retries: int = 4):
        self.project_name = project_name
        self.project_base_path = project_base_path
        self.output_base_path = Path(output_base_path)
        self.output_path = self.output_base_path / project_name / "prove"
        self.model = model
        self.continue_from = continue_from
        self.start_state = PipelineState[start_state] if start_state else None
        self.api_prover_max_retries = api_prover_max_retries
        self.api_prover_max_theorem_retries = api_prover_max_theorem_retries
        self.table_prover_max_retries = table_prover_max_retries
        self.table_prover_max_theorem_retries = table_prover_max_theorem_retries

        # Create output directory
        self.output_path.mkdir(parents=True, exist_ok=True)
        
        self._init_logger(log_level, log_model_io)

    def _init_logger(self, log_level: str, log_model_io: bool):
        """Initialize logger"""
        self.logger = Logger("theorem_proving_pipeline")
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
            return PipelineState.API_PROOFS
            
        if not current_state:
            raise ValueError("No saved state found but continuation was requested")
            
        if self.start_state:
            if self.start_state > current_state:
                raise ValueError(f"Cannot start from {self.start_state.name} as pipeline only reached {current_state.name}")
            return self.start_state
            
        return current_state

    async def _run_api_proofs(self, theorem_info: TableTheoremGenerationInfo) -> APIProverInfo:
        """Run API theorem proving step"""
        self.logger.info("Starting API theorem proving")
        
        # Convert theorem info to prover info
        prover_info = APIProverInfo.from_theorem_info(theorem_info)
        
        # Create prover
        prover = APIProver(
            model=self.model,
            max_retries=self.api_prover_max_retries
        )
        
        # Run proving
        result = await prover.run(
            prover_info=prover_info,
            output_path=self.output_path,
            logger=self.logger,
            max_theorem_retries=self.api_prover_max_theorem_retries
        )
        
        self._save_state(PipelineState.API_PROOFS)
        self.logger.info("API theorem proving completed")
        return result

    async def _run_table_proofs(self, prover_info: APIProverInfo) -> APIProverInfo:
        """Run table theorem proving step"""
        self.logger.info("Starting table theorem proving")
        
        # Create prover
        prover = TableTheoremProver(
            model=self.model,
            max_retries=self.table_prover_max_retries
        )
        
        # Run proving
        result = await prover.run(
            prover_info=prover_info,
            output_path=self.output_path,
            logger=self.logger,
            max_theorem_retries=self.table_prover_max_theorem_retries
        )
        
        self._save_state(PipelineState.TABLE_PROOFS)
        self.logger.info("Table theorem proving completed")
        return result

    async def run(self):
        """Run the complete theorem proving pipeline"""
        self.logger.info(f"Starting theorem proving pipeline for project: {self.project_name}")
        
        # Determine starting state
        start_state = self._validate_continuation()
        self.logger.info(f"Starting from state: {start_state.name}")
        
        # Load theorem generation results first
        self.logger.info("Loading theorem generation results...")
        theorem_path = self.output_base_path / self.project_name / "theorem_generation" / "table_theorems.json"
        if not theorem_path.exists():
            raise FileNotFoundError(f"Theorem generation results not found at: {theorem_path}")
        
        theorem_info = TableTheoremGenerationInfo.load(theorem_path)
        self.logger.info("Theorem generation results loaded successfully")
        
        # Run API theorem proving
        if start_state <= PipelineState.API_PROOFS:
            prover_info = await self._run_api_proofs(theorem_info)
        else:
            # Load previous API proving results
            prover_info = APIProverInfo.load(self.output_path / "api_proofs.json")
        
        # Run table theorem proving
        if start_state <= PipelineState.TABLE_PROOFS:
            prover_info = await self._run_table_proofs(prover_info)
        
        self._save_state(PipelineState.COMPLETED)
        self.logger.info("Theorem proving pipeline completed successfully")
        return True
            

def main():
    parser = argparse.ArgumentParser(description="Run the complete theorem proving pipeline")
    
    parser.add_argument("--project-name", required=True,
                      help="Name of the project to prove")
    parser.add_argument("--project-base-path", default="source_code",
                      help="Base path containing theorem generation results")
    parser.add_argument("--output-base-path", default="outputs",
                      help="Base path for output files")
    parser.add_argument("--model", default="qwen-max-latest",
                      help="Model to use for proving")
    parser.add_argument("--log-level", default="INFO",
                      choices=["DEBUG", "MODEL_INPUT", "MODEL_OUTPUT", "INFO", "WARNING", "ERROR", "CRITICAL"],
                      help="Set the logging level")
    parser.add_argument("--api-prover-max-retries", type=int, default=5,
                      help="Maximum number of retries for API theorem proving")
    parser.add_argument("--api-prover-max-theorem-retries", type=int, default=2,
                        help="Maximum number of retries for individual theorems in API theorem proving")
    parser.add_argument("--log-model-io", action="store_true",
                      help="Enable logging of model inputs and outputs")
    parser.add_argument("--continue", dest="continue_from", action="store_true",
                      help="Continue from last saved state")
    parser.add_argument("--start-state", choices=[s.name for s in PipelineState],
                      help="Start from specific state (requires --continue)")
    parser.add_argument("--table-prover-max-retries", type=int, default=5,
                      help="Maximum number of retries for table theorem proving")
    parser.add_argument("--table-prover-max-theorem-retries", type=int, default=2,
                        help="Maximum number of retries for individual theorems in table theorem proving")
    
    args = parser.parse_args()

    if args.start_state and not args.continue_from:
        parser.error("--start-state requires --continue")
    
    pipeline = TheoremProvingPipeline(
        project_name=args.project_name,
        project_base_path=args.project_base_path,
        output_base_path=args.output_base_path,
        model=args.model,
        log_level=args.log_level,
        log_model_io=args.log_model_io,
        continue_from=args.continue_from,
        start_state=args.start_state,
        api_prover_max_retries=args.api_prover_max_retries,
        api_prover_max_theorem_retries=args.api_prover_max_theorem_retries,
        table_prover_max_retries=args.table_prover_max_retries,
        table_prover_max_theorem_retries=args.table_prover_max_theorem_retries
    )
    
    success = asyncio.run(pipeline.run())
    exit(0 if success else 1)

if __name__ == "__main__":
    main() 