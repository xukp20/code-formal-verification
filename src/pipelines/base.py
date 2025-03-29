from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any
import json
import datetime
from abc import ABC, abstractmethod

from src.utils.model_logger import get_logger, Logger

class PipelineBase(ABC):
    """Base class for pipelines with state management"""
    
    def __init__(self, 
                 project_name: str,
                 output_base_path: str,
                 pipeline_dir: str,
                 log_level: str = "INFO",
                 log_model_io: bool = False,
                 continue_from: bool = False,
                 start_state: Optional[str] = None,
                 end_state: Optional[str] = None):
        """Initialize pipeline
        
        Args:
            project_name: Name of the project
            output_base_path: Base path for outputs
            pipeline_dir: Directory name for this pipeline's outputs
            log_level: Logging level
            log_model_io: Whether to log model inputs/outputs
            continue_from: Whether to continue from last state
            start_state: Specific state to start from (requires continue_from)
            end_state: Specific state to end at (optional)
        """
        self.project_name = project_name
        self.output_path = Path(output_base_path) / project_name / pipeline_dir
        self.continue_from = continue_from
        self.start_state = self._parse_state(start_state) if start_state else None
        self.end_state = self._parse_state(end_state) if end_state else None
        
        # Create output directory
        self.output_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize logger with log file
        log_file = self.output_path / "log.txt"
        self.logger = get_logger(
            name=f"{pipeline_dir}_pipeline",
            log_level=log_level,
            log_model_io=log_model_io,
            log_file=str(log_file)
        )
        
        self.logger.info(f"Pipeline initialized. Logs will be saved to: {log_file}")

    @property
    @abstractmethod
    def state_enum(self) -> type[Enum]:
        """Return the Enum class used for pipeline states"""
        pass

    def _parse_state(self, state_name: str) -> Enum:
        """Parse state name into enum value"""
        try:
            return self.state_enum[state_name]
        except KeyError:
            raise ValueError(f"Invalid state name: {state_name}")

    def save_state(self, state: Enum) -> None:
        """Save current pipeline state"""
        state_file = self.output_path / "pipeline_state.json"
        with open(state_file, 'w') as f:
            json.dump({
                "state": state.name,
                "timestamp": str(datetime.datetime.now())
            }, f)

    def get_current_state(self) -> Optional[Enum]:
        """Get the current pipeline state from saved state file"""
        state_file = self.output_path / "pipeline_state.json"
        if not state_file.exists():
            return None
            
        try:
            with open(state_file) as f:
                data = json.load(f)
            return self.state_enum[data["state"]]
        except Exception as e:
            self.logger.error(f"Failed to load pipeline state: {e}")
            return None

    def validate_continuation(self) -> Enum:
        """Validate and determine the starting state"""
        current_state = self.get_current_state()
        
        if not self.continue_from:
            return list(self.state_enum)[0]  # First state
            
        if not current_state:
            raise ValueError("No saved state found but continuation was requested")
            
        if self.start_state:
            if self.start_state > current_state:
                raise ValueError(
                    f"Cannot start from {self.start_state.name} as pipeline only "
                    f"reached {current_state.name}"
                )
            return self.start_state
            
        return current_state

    def should_continue(self, current_state: Enum) -> bool:
        """Check if pipeline should continue to next state
        
        Args:
            current_state: Current pipeline state
            
        Returns:
            True if pipeline should continue, False if it should stop
        """
        if self.end_state is None:
            return True
        return current_state <= self.end_state

    def save_output(self, state: Enum, data: Any) -> None:
        """Save pipeline output for a state"""
        output_file = self.output_path / f"{state.name.lower()}.json"
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def load_output(self, state: Enum) -> Any:
        """Load pipeline output for a state"""
        output_file = self.output_path / f"{state.name.lower()}.json"
        if not output_file.exists():
            raise ValueError(f"No output file found for state: {state.name}")
            
        with open(output_file) as f:
            return json.load(f)

    @abstractmethod
    async def run(self) -> bool:
        """Run the pipeline"""
        pass 