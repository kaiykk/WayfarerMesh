"""Retry mechanism with exponential backoff for the Travel AI Assistant System.

This module provides a decorator for retrying failed operations with exponential
backoff, supporting configurable max attempts, exception types, and backoff factors.
"""

import functools
import logging
import time
from typing import Any, Callable, Sequence, Type, Union

from .exceptions import TravelAssistantError

logger = logging.getLogger(__name__)


def retry_on_error(
    max_attempts: int = 3,
    backoff_factor: float = 2.0,
    exceptions: Union[Type[Exception], Sequence[Type[Exception]]] = (Exception,),
    on_retry: Callable[[int, Exception, float], None] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that retries a function with exponential backoff on failure.
    
    This decorator wraps a function and automatically retries it if it raises
    an exception of the specified type(s). Between each retry, it waits using
    exponential backoff: delay = backoff_factor ^ (attempt - 1).
    
    Args:
        max_attempts: Maximum number of attempts (including the first attempt).
                      Must be at least 1. Default is 3.
        backoff_factor: Multiplier for exponential backoff delay. Default is 2.0.
        exceptions: Exception type(s) to catch and retry on. Can be a single
                    exception class or a tuple of exception classes. Default
                    catches all exceptions.
        on_retry: Optional callback function called before each retry attempt.
                  Receives (attempt_number, exception, delay) as arguments.
    
    Returns:
        A decorator function that wraps the decorated function with retry logic.
    
    Raises:
        The last exception raised if all retry attempts fail.
    
    Example:
        @retry_on_error(max_attempts=3, backoff_factor=2.0)
        def connect_to_database():
            return database.connect()
        
        # With custom exceptions
        @retry_on_error(
            max_attempts=5,
            backoff_factor=1.5,
            exceptions=(ConnectionError, TimeoutError)
        )
        def fetch_data():
            return api.get("/data")
        
        # With retry callback
        def log_retry(attempt, error, delay):
            logger.warning(f"Retry {attempt} after {delay}s: {error}")
        
        @retry_on_error(max_attempts=3, on_retry=log_retry)
        def unstable_operation():
            pass
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if backoff_factor <= 0:
        raise ValueError("backoff_factor must be positive")
    
    # Convert single exception to tuple for consistent handling
    if isinstance(exceptions, type) and issubclass(exceptions, Exception):
        exception_types: Sequence[Type[Exception]] = (exceptions,)
    elif isinstance(exceptions, tuple):
        exception_types = exceptions
    else:
        raise TypeError(
            "exceptions must be an Exception class or a tuple of Exception classes"
        )
    
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exception_types as e:
                    last_exception = e
                    
                    # If this was the last attempt, re-raise the exception
                    if attempt == max_attempts:
                        logger.error(
                            f"Function {func.__name__} failed after {max_attempts} "
                            f"attempts. Last error: {e}"
                        )
                        raise
                    
                    # Calculate delay using exponential backoff
                    delay = backoff_factor ** (attempt - 1)
                    
                    # Log retry attempt
                    logger.warning(
                        f"Function {func.__name__} failed (attempt {attempt}/"
                        f"{max_attempts}): {e}. Retrying in {delay:.2f}s..."
                    )
                    
                    # Call optional retry callback
                    if on_retry is not None:
                        on_retry(attempt, e, delay)
                    
                    # Wait before retrying
                    time.sleep(delay)
            
            # This should never be reached, but just in case
            raise last_exception
        
        return wrapper
    
    return decorator