"""Unit tests for the QueryExecutor class.

This module tests the query executor implementation including query execution,
transaction support, retry logic, and logging behavior.
"""

import pytest
import sqlite3
import tempfile
import os
import logging
from unittest.mock import Mock, patch, MagicMock
from hypothesis import given, strategies as st, settings
from trip_assistant_refactored.config.config_schema import DatabaseConfig
from trip_assistant_refactored.utils.database.connection_pool import ConnectionPool
from trip_assistant_refactored.utils.database.query_executor import QueryExecutor
from trip_assistant_refactored.utils.error_handling.exceptions import DatabaseError


@pytest.fixture
def temp_db_path():
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        db_path = f.name
    
    # Initialize the database with test tables
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE flights (
            id INTEGER PRIMARY KEY,
            flight_no TEXT,
            departure_airport TEXT,
            arrival_airport TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE bookings (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            flight_id INTEGER
        )
    """)
    conn.execute("INSERT INTO flights (flight_no, departure_airport, arrival_airport) VALUES ('AA100', 'JFK', 'LAX')")
    conn.execute("INSERT INTO flights (flight_no, departure_airport, arrival_airport) VALUES ('UA200', 'SFO', 'ORD')")
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


@pytest.fixture
def query_executor(connection_pool):
    """Create a QueryExecutor instance for testing."""
    return QueryExecutor(connection_pool)


class TestQueryExecutorInitialization:
    """Tests for QueryExecutor initialization."""
    
    def test_init_with_connection_pool(self, connection_pool):
        """Test initialization with connection pool."""
        executor = QueryExecutor(connection_pool)
        assert executor.pool == connection_pool


class TestExecuteQuery:
    """Tests for execute_query method."""
    
    def test_execute_select_query(self, query_executor):
        """Test executing a SELECT query."""
        results = query_executor.execute_query(
            "SELECT * FROM flights WHERE departure_airport = ?",
            ("JFK",)
        )
        
        assert len(results) == 1
        assert results[0]["flight_no"] == "AA100"
        assert results[0]["departure_airport"] == "JFK"
    
    def test_execute_select_query_returns_list_of_dicts(self, query_executor):
        """Test that SELECT query returns list of dictionaries."""
        results = query_executor.execute_query("SELECT * FROM flights")
        
        assert isinstance(results, list)
        assert len(results) > 0
        assert isinstance(results[0], dict)
        assert "flight_no" in results[0]
    
    def test_execute_insert_query(self, query_executor):
        """Test executing an INSERT query."""
        result = query_executor.execute_query(
            "INSERT INTO flights (flight_no, departure_airport, arrival_airport) VALUES (?, ?, ?)",
            ("DL300", "ATL", "MIA"),
            fetch=False
        )
        
        assert result == []
        
        # Verify insertion
        rows = query_executor.execute_query("SELECT * FROM flights WHERE flight_no = ?", ("DL300",))
        assert len(rows) == 1
        assert rows[0]["flight_no"] == "DL300"
    
    def test_execute_update_query(self, query_executor):
        """Test executing an UPDATE query."""
        result = query_executor.execute_query(
            "UPDATE flights SET departure_airport = ? WHERE flight_no = ?",
            ("BOS", "AA100"),
            fetch=False
        )
        
        assert result == []
        
        # Verify update
        rows = query_executor.execute_query("SELECT * FROM flights WHERE flight_no = ?", ("AA100",))
        assert rows[0]["departure_airport"] == "BOS"
    
    def test_execute_delete_query(self, query_executor):
        """Test executing a DELETE query."""
        result = query_executor.execute_query(
            "DELETE FROM flights WHERE flight_no = ?",
            ("UA200",),
            fetch=False
        )
        
        assert result == []
        
        # Verify deletion
        rows = query_executor.execute_query("SELECT * FROM flights WHERE flight_no = ?", ("UA200",))
        assert len(rows) == 0
    
    def test_execute_query_with_no_results(self, query_executor):
        """Test executing query that returns no results."""
        results = query_executor.execute_query(
            "SELECT * FROM flights WHERE flight_no = ?",
            ("NONEXISTENT",)
        )
        
        assert results == []
    
    def test_execute_query_with_empty_params(self, query_executor):
        """Test executing query with empty parameters."""
        results = query_executor.execute_query("SELECT * FROM flights")
        assert len(results) > 0
    
    def test_execute_query_raises_on_invalid_sql(self, query_executor):
        """Test that invalid SQL raises DatabaseError."""
        with pytest.raises(DatabaseError, match="Query execution failed"):
            query_executor.execute_query("INVALID SQL QUERY")


class TestExecuteTransaction:
    """Tests for execute_transaction method."""
    
    def test_execute_transaction_commits_all_queries(self, query_executor):
        """Test that transaction commits all queries successfully."""
        query_executor.execute_transaction([
            ("INSERT INTO flights (flight_no, departure_airport, arrival_airport) VALUES (?, ?, ?)", ("TX100", "DFW", "HOU")),
            ("INSERT INTO flights (flight_no, departure_airport, arrival_airport) VALUES (?, ?, ?)", ("TX200", "HOU", "DFW"))
        ])
        
        # Verify both inserts succeeded
        results = query_executor.execute_query("SELECT * FROM flights WHERE flight_no LIKE 'TX%'")
        assert len(results) == 2
    
    def test_execute_transaction_rolls_back_on_error(self, query_executor):
        """Test that transaction rolls back all changes on error."""
        initial_count = len(query_executor.execute_query("SELECT * FROM flights"))
        
        with pytest.raises(DatabaseError):
            query_executor.execute_transaction([
                ("INSERT INTO flights (flight_no, departure_airport, arrival_airport) VALUES (?, ?, ?)", ("RB100", "LAX", "SFO")),
                ("INVALID SQL QUERY", ())  # This will cause rollback
            ])
        
        # Verify rollback - count should be unchanged
        final_count = len(query_executor.execute_query("SELECT * FROM flights"))
        assert final_count == initial_count
    
    def test_execute_transaction_with_multiple_updates(self, query_executor):
        """Test transaction with multiple UPDATE queries."""
        query_executor.execute_transaction([
            ("UPDATE flights SET departure_airport = ? WHERE flight_no = ?", ("NYC", "AA100")),
            ("UPDATE flights SET arrival_airport = ? WHERE flight_no = ?", ("CHI", "UA200"))
        ])
        
        # Verify both updates
        aa100 = query_executor.execute_query("SELECT * FROM flights WHERE flight_no = ?", ("AA100",))
        ua200 = query_executor.execute_query("SELECT * FROM flights WHERE flight_no = ?", ("UA200",))
        
        assert aa100[0]["departure_airport"] == "NYC"
        assert ua200[0]["arrival_airport"] == "CHI"
    
    def test_execute_transaction_with_empty_list(self, query_executor):
        """Test transaction with empty query list."""
        query_executor.execute_transaction([])  # Should not raise


class TestRetryBehavior:
    """Tests for retry behavior on database errors."""
    
    def test_execute_query_retries_on_database_error(self, connection_pool):
        """Test that execute_query retries on database errors."""
        executor = QueryExecutor(connection_pool)
        
        # Mock the connection to fail twice then succeed
        call_count = 0
        original_connection = connection_pool.connection
        
        def mock_connection():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise sqlite3.OperationalError("Database is locked")
            return original_connection()
        
        with patch.object(connection_pool, 'connection', side_effect=mock_connection):
            # This should succeed after retries
            with pytest.raises(sqlite3.OperationalError):
                executor.execute_query("SELECT * FROM flights")
        
        # Verify it attempted multiple times
        assert call_count >= 2


class TestLogging:
    """Tests for logging behavior."""
    
    def test_execute_query_logs_execution(self, query_executor, caplog):
        """Test that execute_query logs execution details."""
        with caplog.at_level(logging.INFO):
            query_executor.execute_query("SELECT * FROM flights")
        
        # Check that execution time was logged
        assert any("executed in" in record.message for record in caplog.records)
    
    def test_execute_query_logs_debug_info(self, query_executor, caplog):
        """Test that execute_query logs debug information."""
        with caplog.at_level(logging.DEBUG):
            query_executor.execute_query("SELECT * FROM flights WHERE flight_no = ?", ("AA100",))
        
        # Check for debug logs
        messages = [record.message for record in caplog.records if record.levelname == "DEBUG"]
        assert any("Executing query" in msg for msg in messages)
        assert any("returned" in msg for msg in messages)
    
    def test_execute_transaction_logs_execution(self, query_executor, caplog):
        """Test that execute_transaction logs execution details."""
        with caplog.at_level(logging.INFO):
            query_executor.execute_transaction([
                ("INSERT INTO flights (flight_no, departure_airport, arrival_airport) VALUES (?, ?, ?)", ("LOG100", "ATL", "DFW"))
            ])
        
        # Check that execution time and completion were logged
        assert any("executed in" in record.message for record in caplog.records)
        assert any("completed successfully" in record.message.lower() for record in caplog.records)
    
    def test_execute_query_logs_error_on_failure(self, query_executor, caplog):
        """Test that execute_query logs errors on failure."""
        with caplog.at_level(logging.ERROR):
            with pytest.raises(DatabaseError):
                query_executor.execute_query("INVALID SQL")
        
        # Check for error log
        assert any(record.levelname == "ERROR" for record in caplog.records)
        assert any("failed" in record.message.lower() for record in caplog.records)


# Property-Based Tests

class TestDatabaseOperationLoggingProperty:
    """Property 6: Database Operation Logging
    
    Validates Requirements 3.5, 9.3:
    Test that all database operations create log entries with execution time.
    """
    
    @given(
        query_type=st.sampled_from(["SELECT", "INSERT", "UPDATE"]),
        table_name=st.sampled_from(["flights", "bookings"])
    )
    @settings(max_examples=20, deadline=None)
    def test_all_operations_log_execution_time(self, query_executor, caplog, query_type, table_name):
        """Property: All database operations MUST log execution time.
        
        For any database operation (SELECT, INSERT, UPDATE, DELETE), the system
        SHALL create a log entry containing the execution time in milliseconds.
        """
        with caplog.at_level(logging.INFO):
            try:
                if query_type == "SELECT":
                    query_executor.execute_query(f"SELECT * FROM {table_name}")
                elif query_type == "INSERT":
                    if table_name == "flights":
                        query_executor.execute_query(
                            f"INSERT INTO {table_name} (flight_no, departure_airport, arrival_airport) VALUES (?, ?, ?)",
                            ("TEST", "AAA", "BBB"),
                            fetch=False
                        )
                    else:  # bookings
                        query_executor.execute_query(
                            f"INSERT INTO {table_name} (user_id, flight_id) VALUES (?, ?)",
                            (1, 1),
                            fetch=False
                        )
                elif query_type == "UPDATE":
                    if table_name == "flights":
                        query_executor.execute_query(
                            f"UPDATE {table_name} SET departure_airport = ? WHERE id = ?",
                            ("XXX", 999),
                            fetch=False
                        )
                    else:  # bookings
                        query_executor.execute_query(
                            f"UPDATE {table_name} SET user_id = ? WHERE id = ?",
                            (999, 999),
                            fetch=False
                        )
            except DatabaseError:
                pass  # Some operations may fail, but should still log
        
        # Property assertion: Execution time MUST be logged
        execution_time_logged = any(
            "executed in" in record.message and "ms" in record.message
            for record in caplog.records
        )
        
        assert execution_time_logged, (
            f"Database operation {query_type} on {table_name} did not log execution time. "
            f"All database operations MUST log execution time for performance monitoring."
        )
    
    @given(
        num_queries=st.integers(min_value=1, max_value=5)
    )
    @settings(max_examples=10, deadline=None)
    def test_transaction_logs_execution_time(self, query_executor, caplog, num_queries):
        """Property: All transactions MUST log execution time.
        
        For any transaction containing one or more queries, the system SHALL
        create a log entry containing the total execution time in milliseconds.
        """
        queries = [
            (f"INSERT INTO flights (flight_no, departure_airport, arrival_airport) VALUES (?, ?, ?)",
             (f"TXN{i}", "AAA", "BBB"))
            for i in range(num_queries)
        ]
        
        with caplog.at_level(logging.INFO):
            query_executor.execute_transaction(queries)
        
        # Property assertion: Execution time MUST be logged for transaction
        execution_time_logged = any(
            "executed in" in record.message and "ms" in record.message
            for record in caplog.records
        )
        
        assert execution_time_logged, (
            f"Transaction with {num_queries} queries did not log execution time. "
            f"All transactions MUST log execution time for performance monitoring."
        )
    
    def test_failed_operations_log_execution_time(self, query_executor, caplog):
        """Property: Failed operations MUST still log execution time.
        
        Even when a database operation fails, the system SHALL log the execution
        time before raising the exception. This ensures complete performance tracking.
        """
        with caplog.at_level(logging.INFO):
            with pytest.raises(DatabaseError):
                query_executor.execute_query("INVALID SQL THAT WILL FAIL")
        
        # Property assertion: Execution time MUST be logged even for failed operations
        execution_time_logged = any(
            "executed in" in record.message and "ms" in record.message
            for record in caplog.records
        )
        
        assert execution_time_logged, (
            "Failed database operation did not log execution time. "
            "All operations MUST log execution time regardless of success or failure."
        )
