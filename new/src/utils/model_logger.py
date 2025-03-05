from logging import Logger, INFO, DEBUG, StreamHandler, Formatter, addLevelName
import logging

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


def get_logger(name: str, log_level: str = "INFO", log_model_io: bool = False) -> Logger:
    logger = Logger(name)
    level = getattr(logging, log_level.upper())
    logger.setLevel(level)

    if log_model_io:
        logger.setLevel(min(level, MODEL_INPUT))

    stream_handler = StreamHandler()
    stream_handler.setLevel(level)
    formatter = Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger