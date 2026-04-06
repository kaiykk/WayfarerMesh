"""Database connection pool implementation for SQLite.

This module provides a thread-safe connection pool for managing SQLite database
connections with automatic retry and health checking capabilities.
"""

import sqlite3
import queue
import threading
from contextlib import contextmanager
from typing import Generator, Optional
from trip_assistant_refactored.config.config_schema import DatabaseConfig
from trip_assistant_refactored.utils.error_handling.exceptions import DatabaseError


class ConnectionPool:
    """
    Manages a pool of SQLite database connections with automatic retry and logging.
    
    This class provides thread-safe connection pooling using queue.Queue to manage
    available connections. Connections are created lazily up to the configured pool size.
    
    Attributes:
        config: Database configuration containing path, pool size, and timeout settings
        _pool: Queue containing available database connections
        _lock: Thread lock for connection creation
        _created_connections: Counter for total connections created
    """
    
    def __init__(self, config: DatabaseConfig) -> None:
        """Initialize connection pool with configuration.
        
        Args:
            config: DatabaseConfig instance with pool_size, path, and timeout settings
            
        Raises:
            DatabaseError: If configuration is invalid
        """
        if config.pool_size <= 0:
            raise DatabaseError("Pool size must be greater than 0")
        
        self.config = config
        self._pool: queue.Queue = queue.Queue(maxsize=config.pool_size)
        self._lock = threading.Lock()
        self._created_connections = 0
        
    def _create_connection(self) -> sqlite3.Connection:
        """Create a new SQLite database connection.
        
        Returns:
            A new SQLite connection object
            
        Raises:
            DatabaseError: If connection creation fails
        """
        try:
            conn = sqlite3.connect(
                self.config.path,
                timeout=self.config.timeout,
                check_same_thread=False
            )
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to create database connection: {e}")
    
    def get_connection(self) -> sqlite3.Connection:
        """Get a connection from the pool (blocks if pool is exhausted).
        
        If no connections are available in the pool and the maximum pool size
        has not been reached, a new connection is created. Otherwise, this method
        blocks until a connection becomes available.
        
        Returns:
            A SQLite connection object from the pool
            
        Raises:
            DatabaseError: If connection creation or retrieval fails
        """
        try:
            # Try to get an existing connection from the pool (non-blocking)
            return self._pool.get_nowait()
        except queue.Empty:
            # No connections available, try to create a new one
            with self._lock:
                if self._created_connections < self.config.pool_size:
                    self._created_connections += 1
                    return self._create_connection()
            
            # Pool is at max capacity, block until a connection is available
            return self._pool.get(block=True)
    
    def return_connection(self, conn: sqlite3.Connection) -> None:
        """Return a connection to the pool.
        
        Args:
            conn: The SQLite connection to return to the pool
            
        Raises:
            DatabaseError: If the connection cannot be returned to the pool
        """
        if conn is None:
            return
        
        try:
            # Rollback any uncommitted transactions before returning
            conn.rollback()
            self._pool.put_nowait(conn)
        except queue.Full:
            # Pool is full, close the connection instead
            try:
                conn.close()
            except sqlite3.Error:
                pass  # Ignore errors when closing
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to return connection to pool: {e}")
    
    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for automatic connection handling.
        
        Automatically acquires a connection from the pool and returns it
        when the context exits, even if an exception occurs.
        
        Yields:
            A SQLite connection object from the pool
            
        Example:
            with pool.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM flights")
                results = cursor.fetchall()
        """
        conn = self.get_connection()
        try:
            yield conn
        finally:
            self.return_connection(conn)
    
    def close_all(self) -> None:
        """Close all connections in the pool (called on shutdown).
        
        This method drains the connection pool and closes all connections.
        It should be called during application shutdown to clean up resources.
        """
        closed_count = 0
        
        # Drain the pool and close all connections
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
                closed_count += 1
            except queue.Empty:
                break
            except sqlite3.Error:
                # Ignore errors when closing connections
                pass
        
        # Reset the connection counter
        with self._lock:
            self._created_connections = 0
    
    def health_check(self) -> bool:
        """Verify pool health by testing a connection.
        
        Attempts to acquire a connection and execute a simple query to verify
        that the database is accessible and the pool is functioning correctly.
        
        Returns:
            True if the health check passes, False otherwise
        """
        try:
            with self.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                return result is not None and result[0] == 1
        except (DatabaseError, sqlite3.Error):
            return False
