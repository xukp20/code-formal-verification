from logging import Logger, INFO, DEBUG, StreamHandler, FileHandler, Formatter, addLevelName
import logging
from typing import Optional
from pathlib import Path

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


def get_logger(name: str, 
              log_level: str = "INFO", 
              log_model_io: bool = False,
              log_file: Optional[str] = None) -> Logger:
    """
    Get a logger with optional file output for warnings and errors
    
    Args:
        name: Logger name
        log_level: Logging level (DEBUG, INFO, etc.)
        log_model_io: Whether to log model I/O
        log_file: Optional path to log file for warnings and errors
    """
    logger = Logger(name)
    level = getattr(logging, log_level.upper())
    logger.setLevel(level)

    if log_model_io:
        logger.setLevel(min(level, MODEL_INPUT))

    # Console handler with original formatting
    stream_handler = StreamHandler()
    stream_handler.setLevel(level)
    console_formatter = Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    stream_handler.setFormatter(console_formatter)
    logger.addHandler(stream_handler)

    # File handler for warnings and errors if log_file is provided
    if log_file:
        # Create directory if it doesn't exist
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = FileHandler(log_file, mode='a')
        file_handler.setLevel(logging.WARNING)  # Only log WARNING and above
        file_formatter = Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger