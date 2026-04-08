"""Logging decorators for the Travel AI Assistant System.

This module provides decorators for automatic logging of function execution,
including execution time tracking and performance monitoring.
"""

import functools
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


def log_execution_time(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that logs function execution time in milliseconds.
    
    This decorator wraps a function and automatically logs its execution time
    when it completes. The execution time is logged at INFO level with the
    function name and duration in milliseconds.
    
    Args:
        func: The function to wrap with execution time logging
    
    Returns:
        A wrapped function that logs its execution time
    
    Example:
        @log_execution_time
        def search_flights(departure: str, arrival: str):
            # Database query here
            pass
        
        # Logs: "Function search_flights executed in 125.34ms"
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.time()
        
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            end_time = time.time()
            execution_time_ms = (end_time - start_time) * 1000
            
            logger.info(
                f"Function {func.__name__} executed in {execution_time_ms:.2f}ms",
                extra={
                    "function": func.__name__,
                    "execution_time_ms": execution_time_ms,
                }
            )
    
    return wrapper
