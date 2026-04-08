"""Query executor with retry logic, logging, and performance tracking.

This module provides the QueryExecutor class for executing database queries
with automatic retry on transient errors, execution time logging, and
comprehensive error handling.
"""

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

from trip_assistant_refactored.utils.database.connection_pool import ConnectionPool
from trip_assistant_refactored.utils.error_handling.exceptions import DatabaseError
from trip_assistant_refactored.utils.error_handling.retry import retry_on_error

logger = logging.getLogger(__name__)


class QueryExecutor:
    """
    Executes database queries with retry logic, logging, and performance tracking.
    
    This class provides methods for executing individual queries and transactions
    with automatic retry on transient database errors, execution time logging,
    and comprehensive error handling.
    
    Attributes:
        pool: ConnectionPool instance for managing database connections
    """
    
    def __init__(self, pool: ConnectionPool) -> None:
        """Initialize query executor with connection pool.
        
        Args:
            pool: ConnectionPool instance for database connections
        """
        self.pool = pool


    @retry_on_error(
        max_attempts=3,
        backoff_factor=2.0,
        exceptions=(sqlite3.OperationalError, sqlite3.DatabaseError)
    )
    def execute_query(
        self,
        query: str,
        params: Tuple[Any, ...] = (),
        fetch: bool = True
    ) -> List[Dict[str, Any]]:
        """Execute a query with automatic retry and logging.
        
        This method executes a SQL query with the provided parameters, automatically
        retrying on transient database errors. Execution time is logged for
        performance monitoring.
        
        Args:
            query: SQL query string to execute
            params: Tuple of parameters for the query (default: empty tuple)
            fetch: Whether to fetch and return results (default: True)
                   Set to False for INSERT, UPDATE, DELETE operations
        
        Returns:
            List of dictionaries for SELECT queries (when fetch=True)
            Empty list for non-SELECT queries (when fetch=False)
        
        Raises:
            DatabaseError: If query execution fails after all retry attempts
        
        Example:
            results = executor.execute_query(
                "SELECT * FROM flights WHERE departure_airport = ?",
                ("JFK",)
            )
        """
        start_time = time.time()
        
        try:
            logger.debug(
                f"Executing query: {query[:100]}... with params: {params}",
                extra={"query": query, "params": params}
            )
            
            with self.pool.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                
                if fetch:
                    rows = cursor.fetchall()
                    # Convert sqlite3.Row objects to dictionaries
                    results = [dict(row) for row in rows]
                    
                    logger.debug(
                        f"Query returned {len(results)} rows",
                        extra={"row_count": len(results)}
                    )
                    
                    return results
                else:
                    # For INSERT, UPDATE, DELETE operations, commit the transaction
                    conn.commit()
                    return []
        
        except (sqlite3.Error, Exception) as e:
            logger.error(
                f"Query execution failed: {e}",
                extra={"query": query, "params": params, "error": str(e)},
                exc_info=True
            )
            raise DatabaseError(f"Query execution failed: {e}")
        
        finally:
            end_time = time.time()
            execution_time_ms = (end_time - start_time) * 1000
            
            logger.info(
                f"Query executed in {execution_time_ms:.2f}ms",
                extra={
                    "query": query[:100],
                    "execution_time_ms": execution_time_ms,
                }
            )


    @retry_on_error(
        max_attempts=3,
        backoff_factor=2.0,
        exceptions=(sqlite3.OperationalError, sqlite3.DatabaseError)
    )
    def execute_transaction(
        self,
        queries: List[Tuple[str, Tuple[Any, ...]]]
    ) -> None:
        """Execute multiple queries in a transaction with rollback on error.
        
        This method executes a list of queries as a single atomic transaction.
        If any query fails, all changes are rolled back. Execution time is logged
        for performance monitoring.
        
        Args:
            queries: List of (query, params) tuples to execute in transaction
        
        Raises:
            DatabaseError: If any query in the transaction fails
        
        Example:
            executor.execute_transaction([
                ("INSERT INTO flights (flight_no, ...) VALUES (?, ...)", ("TX100", ...)),
                ("INSERT INTO flights (flight_no, ...) VALUES (?, ...)", ("TX200", ...))
            ])
        """
        start_time = time.time()
        
        try:
            logger.debug(
                f"Executing transaction with {len(queries)} queries",
                extra={"query_count": len(queries)}
            )
            
            with self.pool.connection() as conn:
                cursor = conn.cursor()
                
                for query, params in queries:
                    logger.debug(
                        f"Transaction query: {query[:100]}... with params: {params}",
                        extra={"query": query, "params": params}
                    )
                    cursor.execute(query, params)
                
                # Commit the transaction
                conn.commit()
                
                logger.info(
                    f"Transaction completed successfully with {len(queries)} queries",
                    extra={"query_count": len(queries)}
                )
        
        except (sqlite3.Error, Exception) as e:
            logger.error(
                f"Transaction failed: {e}",
                extra={"query_count": len(queries), "error": str(e)},
                exc_info=True
            )
            raise DatabaseError(f"Transaction execution failed: {e}")
        
        finally:
            end_time = time.time()
            execution_time_ms = (end_time - start_time) * 1000
            
            logger.info(
                f"Transaction executed in {execution_time_ms:.2f}ms",
                extra={
                    "query_count": len(queries),
                    "execution_time_ms": execution_time_ms,
                }
            )
