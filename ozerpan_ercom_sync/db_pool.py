import queue
import threading
from contextlib import contextmanager
from typing import Any, Dict, Optional

import frappe
import pymysql
from pymysql.cursors import DictCursor

config = frappe.conf


class DatabaseConnectionPool:
    """
    A thread-safe database connection pool for PyMySQL.
    """

    def __init__(
        self,
        host: str = config["ercom_db_host"],
        user: str = config["ercom_db_user"],
        password: str = config["ercom_db_password"],
        database: str = config["ercom_db_name"],
        port: int = 3306,
        max_connections: int = 10,
        **kwargs,
    ):
        """
        Initialize the connection pool.

        Args:
            host: Database host
            user: Database user
            password: Database password
            database: Database name
            port: Database port (default: 3306)
            max_connections: Maximum number of connections in the pool (default: 10)
            **kwargs: Additional connection parameters for PyMySQL
        """
        self.connection_params = {
            "host": host,
            "user": user,
            "password": password,
            "database": database,
            "port": port,
            "cursorclass": DictCursor,
            **kwargs,
        }
        self.max_connections = max_connections
        self.pool: queue.Queue = queue.Queue(maxsize=max_connections)
        self.active_connections = 0
        self.lock = threading.Lock()

        # Pre-populate the pool with initial connections
        for _ in range(max_connections // 2):
            self._add_connection()

    def _create_connection(self) -> pymysql.Connection:
        """Create a new database connection."""
        try:
            return pymysql.connect(**self.connection_params)
        except Exception as e:
            raise Exception(f"Failed to create database connection: {str(e)}")

    def _add_connection(self) -> None:
        """Add a new connection to the pool."""
        try:
            with self.lock:
                if self.active_connections < self.max_connections:
                    conn = self._create_connection()
                    if isinstance(conn, pymysql.Connection):
                        self.pool.put(conn)
                        self.active_connections += 1
        except Exception as e:
            raise Exception(f"Failed to add connection to pool: {str(e)}")

    def _validate_connection(self, conn: pymysql.Connection) -> bool:
        """Check if the connection is still valid."""
        if not isinstance(conn, pymysql.Connection):
            return False
        try:
            conn.ping(reconnect=False)
            return True
        except:
            return False

    @contextmanager
    def get_connection(self) -> pymysql.Connection:
        """
        Get a database connection from the pool.

        Returns:
            A context manager yielding a database connection.

        Usage:
            with pool.get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT * FROM table")
                    results = cursor.fetchall()
        """
        connection = None
        try:
            connection = self.pool.get(timeout=5)

            # Validate the connection and create a new one if necessary
            if not self._validate_connection(connection):
                if isinstance(connection, pymysql.Connection):
                    try:
                        connection.close()
                    except:
                        pass
                connection = self._create_connection()

            yield connection

            # Only return the connection to the pool if it's still valid
            if self._validate_connection(connection):
                self.pool.put(connection)
            else:
                if isinstance(connection, pymysql.Connection):
                    try:
                        connection.close()
                    except:
                        pass
                with self.lock:
                    self.active_connections -= 1

        except queue.Empty:
            # If the pool is empty, create a new connection
            self._add_connection()
            # Try again with the new connection
            with self.get_connection() as new_connection:
                yield new_connection
        except Exception as e:
            # If there's an error with the connection, close it and reduce active count
            if connection and isinstance(connection, pymysql.Connection):
                try:
                    connection.close()
                except:
                    pass
                with self.lock:
                    self.active_connections -= 1
            raise Exception(f"Database connection error: {str(e)}")

    def execute_query(
        self, query: str, params: Optional[Dict[str, Any]] = None, fetch_all: bool = True
    ) -> Any:
        """
        Execute a SQL query and return the results.

        Args:
            query: SQL query string
            params: Query parameters (optional)
            fetch_all: If True, returns all rows; if False, returns one row

        Returns:
            Query results as a list of dictionaries or a single dictionary
        """
        with self.get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params or {})
                if fetch_all:
                    return cursor.fetchall()
                return cursor.fetchone()

    def execute_many(self, query: str, params: list) -> int:
        """
        Execute the same SQL query with different parameters many times.

        Args:
            query: SQL query string
            params: List of parameter dictionaries

        Returns:
            Number of affected rows
        """
        with self.get_connection() as connection:
            with connection.cursor() as cursor:
                affected_rows = cursor.executemany(query, params)
                connection.commit()
                return affected_rows

    def close_all(self) -> None:
        """Close all connections in the pool."""
        with self.lock:
            while not self.pool.empty():
                try:
                    conn = self.pool.get_nowait()
                    if isinstance(conn, pymysql.Connection):
                        try:
                            conn.close()
                        except:
                            pass
                except queue.Empty:
                    break
            self.active_connections = 0


# Example query execution
# def get_data():
#     pool = DatabaseConnectionPool()
#     results = pool.execute_query(
#         "SELECT * FROM users WHERE active = %(active)s", params={"active": True}
#     )
#     print("Active users:", results)
