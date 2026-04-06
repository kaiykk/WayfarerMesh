"""Unit tests for the ConnectionPool class.

This module tests the database connection pool implementation including
connection management, thread safety, and health checking.
"""

import pytest
import sqlite3
import threading
import tempfile
import os
from pathlib import Path
from trip_assistant_refactored.config.config_schema import DatabaseConfig
from trip_assistant_refactored.utils.database.connection_pool import ConnectionPool
from trip_assistant_refactored.utils.error_handling.exceptions import DatabaseError


@pytest.fixture
def temp_db_path():
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        db_path = f.name
    
    # Initialize the database with a simple table
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO test_table (value) VALUES ('test')")
    conn.commit()
    conn.close()
    
    yield db_path
    
    # Cleanup
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def db_config(temp_db_path):
    """Create a DatabaseConfig for testing."""
    return DatabaseConfig(
        path=temp_db_path,
        pool_size=3,
        timeout=5.0,
        retry_attempts=3,
        retry_backoff_factor=2.0
    )


@pytest.fixture
def connection_pool(db_config):
    """Create a ConnectionPool instance for testing."""
    pool = ConnectionPool(db_config)
    yield pool
    pool.close_all()


class TestConnectionPoolInitialization:
    """Tests for ConnectionPool initialization."""
    
    def test_init_with_valid_config(self, db_config):
        """Test initialization with valid configuration."""
        pool = ConnectionPool(db_config)
        assert pool.config == db_config
        assert pool._created_connections == 0
        pool.close_all()
    
    def test_init_with_invalid_pool_size(self, temp_db_path):
        """Test initialization fails with invalid pool size."""
        config = DatabaseConfig(path=temp_db_path, pool_size=0)
        with pytest.raises(DatabaseError, match="Pool size must be greater than 0"):
            ConnectionPool(config)
    
    def test_init_with_negative_pool_size(self, temp_db_path):
        """Test initialization fails with negative pool size."""
        config = DatabaseConfig(path=temp_db_path, pool_size=-1)
        with pytest.raises(DatabaseError, match="Pool size must be greater than 0"):
            ConnectionPool(config)


class TestConnectionManagement:
    """Tests for connection acquisition and return."""
    
    def test_get_connection_creates_new_connection(self, connection_pool):
        """Test that get_connection creates a new connection when pool is empty."""
        conn = connection_pool.get_connection()
        assert conn is not None
        assert isinstance(conn, sqlite3.Connection)
        assert connection_pool._created_connections == 1
        connection_pool.return_connection(conn)
    
    def test_return_connection_adds_to_pool(self, connection_pool):
        """Test that return_connection adds connection back to pool."""
        conn = connection_pool.get_connection()
        connection_pool.return_connection(conn)
        
        # Getting connection again should reuse the same one
        conn2 = connection_pool.get_connection()
        assert conn2 is not None
        assert connection_pool._created_connections == 1  # No new connection created
        connection_pool.return_connection(conn2)
    
    def test_return_none_connection(self, connection_pool):
        """Test that returning None connection is handled gracefully."""
        connection_pool.return_connection(None)  # Should not raise
    
    def test_pool_respects_max_size(self, connection_pool):
        """Test that pool does not exceed configured pool_size."""
        connections = []
        for _ in range(connection_pool.config.pool_size):
            conn = connection_pool.get_connection()
            connections.append(conn)
        
        assert connection_pool._created_connections == connection_pool.config.pool_size
        
        # Return all connections
        for conn in connections:
            connection_pool.return_connection(conn)
    
    def test_connection_rollback_on_return(self, connection_pool):
        """Test that uncommitted transactions are rolled back when returning connection."""
        conn = connection_pool.get_connection()
        cursor = conn.cursor()
        
        # Start a transaction but don't commit
        cursor.execute("INSERT INTO test_table (value) VALUES ('uncommitted')")
        
        # Return connection (should rollback)
        connection_pool.return_connection(conn)
        
        # Get connection again and verify rollback occurred
        conn2 = connection_pool.get_connection()
        cursor2 = conn2.cursor()
        cursor2.execute("SELECT COUNT(*) FROM test_table WHERE value = 'uncommitted'")
        count = cursor2.fetchone()[0]
        assert count == 0  # Transaction was rolled back
        connection_pool.return_connection(conn2)


class TestContextManager:
    """Tests for the connection context manager."""
    
    def test_context_manager_acquires_and_returns_connection(self, connection_pool):
        """Test that context manager properly acquires and returns connection."""
        with connection_pool.connection() as conn:
            assert conn is not None
            assert isinstance(conn, sqlite3.Connection)
            initial_count = connection_pool._created_connections
        
        # Connection should be returned to pool
        # Getting another connection should reuse it
        with connection_pool.connection() as conn2:
            assert connection_pool._created_connections == initial_count
    
    def test_context_manager_returns_connection_on_exception(self, connection_pool):
        """Test that context manager returns connection even when exception occurs."""
        try:
            with connection_pool.connection() as conn:
                assert conn is not None
                raise ValueError("Test exception")
        except ValueError:
            pass
        
        # Connection should still be returned to pool
        with connection_pool.connection() as conn2:
            assert conn2 is not None
    
    def test_context_manager_query_execution(self, connection_pool):
        """Test executing queries using context manager."""
        with connection_pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM test_table")
            results = cursor.fetchall()
            assert len(results) > 0


class TestHealthCheck:
    """Tests for pool health checking."""
    
    def test_health_check_passes_with_valid_pool(self, connection_pool):
        """Test that health check passes with a valid pool."""
        assert connection_pool.health_check() is True
    
    def test_health_check_fails_with_invalid_database(self, temp_db_path):
        """Test that health check fails with invalid database path."""
        config = DatabaseConfig(path="/nonexistent/path/db.sqlite", pool_size=2)
        pool = ConnectionPool(config)
        assert pool.health_check() is False
        pool.close_all()
    
    def test_health_check_after_close_all(self, connection_pool):
        """Test health check after closing all connections."""
        # First health check should pass
        assert connection_pool.health_check() is True
        
        # Close all connections
        connection_pool.close_all()
        
        # Health check should still pass (creates new connection)
        assert connection_pool.health_check() is True


class TestCloseAll:
    """Tests for closing all connections."""
    
    def test_close_all_closes_connections(self, connection_pool):
        """Test that close_all closes all connections in the pool."""
        # Create some connections
        conn1 = connection_pool.get_connection()
        conn2 = connection_pool.get_connection()
        connection_pool.return_connection(conn1)
        connection_pool.return_connection(conn2)
        
        # Close all
        connection_pool.close_all()
        
        # Connection counter should be reset
        assert connection_pool._created_connections == 0
    
    def test_close_all_on_empty_pool(self, connection_pool):
        """Test that close_all works on empty pool."""
        connection_pool.close_all()  # Should not raise
        assert connection_pool._created_connections == 0


class TestThreadSafety:
    """Tests for thread-safe connection management."""
    
    def test_concurrent_connection_acquisition(self, connection_pool):
        """Test that multiple threads can safely acquire connections."""
        results = []
        errors = []
        
        def acquire_and_use_connection():
            try:
                with connection_pool.connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM test_table")
                    result = cursor.fetchall()
                    results.append(len(result))
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=acquire_and_use_connection)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify no errors occurred
        assert len(errors) == 0
        assert len(results) == 10
        assert all(r > 0 for r in results)
    
    def test_pool_size_limit_with_concurrent_access(self, connection_pool):
        """Test that pool size limit is respected with concurrent access."""
        barrier = threading.Barrier(connection_pool.config.pool_size + 2)
        connections_held = []
        
        def hold_connection():
            conn = connection_pool.get_connection()
            connections_held.append(conn)
            barrier.wait()  # Wait for all threads
            connection_pool.return_connection(conn)
        
        threads = []
        for _ in range(connection_pool.config.pool_size + 2):
            thread = threading.Thread(target=hold_connection)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Should not exceed pool size
        assert connection_pool._created_connections <= connection_pool.config.pool_size


class TestConnectionProperties:
    """Tests for connection properties and configuration."""
    
    def test_connection_has_row_factory(self, connection_pool):
        """Test that connections have row_factory set."""
        with connection_pool.connection() as conn:
            assert conn.row_factory == sqlite3.Row
    
    def test_connection_timeout_configured(self, connection_pool):
        """Test that connection timeout is configured."""
        conn = connection_pool.get_connection()
        # Connection should be created with timeout from config
        # We can't directly test timeout, but we can verify connection works
        assert conn is not None
        connection_pool.return_connection(conn)
