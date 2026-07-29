import logging
import sys
import time
from functools import wraps

def setup_logger(name="pipeline_logger"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers if setup_logger is called multiple times
    if not logger.handlers:
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(module)s:%(lineno)d | %(message)s'
        )

        # File Handler
        file_handler = logging.FileHandler("pipeline_execution.log", mode='a')
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)

        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger

logger = setup_logger()

def log_latency(step_name):
    """
    Decorator to log the execution time of a function/step.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            logger.info(f"STARTED step: {step_name}")
            try:
                result = func(*args, **kwargs)
                latency = time.time() - start_time
                logger.info(f"COMPLETED step: {step_name} | Latency: {latency:.4f} seconds")
                return result
            except Exception as e:
                latency = time.time() - start_time
                logger.error(f"FAILED step: {step_name} | Latency: {latency:.4f} seconds | Error: {str(e)}", exc_info=True)
                raise
        return wrapper
    return decorator
