import duckdb
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import threading
from functools import wraps

class LocalLogger:
    def __init__(self, db_path: str = "chat_logs.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._initialize_db()
    
    def _initialize_db(self):
        """Initialize database with migrations table and run any pending migrations"""
        with self._get_connection() as conn:
            # Create migrations tracking table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS _migrations (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Run migrations
            self._run_migrations(conn)
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections - ensures they're always closed"""
        conn = duckdb.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()
    
    def _run_migrations(self, conn):
        """Run all pending migrations"""
        migrations = [
            {
                'id': 1,
                'name': 'initial_schema',
                'sql': """
                    CREATE TABLE IF NOT EXISTS chat_messages (
                        session_id VARCHAR NOT NULL,
                        conversation_id VARCHAR NOT NULL,
                        message TEXT NOT NULL,
                        role VARCHAR NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
            },
            # Add future migrations here
        ]
        
        for migration in migrations:
            if not self._migration_applied(conn, migration['id']):
                print(f"Running migration: {migration['name']}")
                conn.execute(migration['sql'])
                conn.execute("""
                    INSERT INTO _migrations (id, name) VALUES (?, ?)
                """, [migration['id'], migration['name']])
                print(f"Migration {migration['name']} completed")
    
    def _migration_applied(self, conn, migration_id: int) -> bool:
        """Check if a migration has already been applied"""
        result = conn.execute("""
            SELECT COUNT(*) FROM _migrations WHERE id = ?
        """, [migration_id]).fetchone()
        return result[0] > 0
    
    def log_message(self, session_id: str, conversation_id: str, message: str, role: str):
        """Log a single message - thread-safe"""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO chat_messages (session_id, conversation_id, message, role)
                    VALUES (?, ?, ?, ?)
                """, [session_id, conversation_id, message, role])
    
    def log_conversation_turn(self, session_id: str, conversation_id: str, 
                            user_message: str, assistant_message: str):
        """Log both user and assistant messages in one transaction"""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("BEGIN TRANSACTION")
                try:
                    conn.execute("""
                        INSERT INTO chat_messages (session_id, conversation_id, message, role)
                        VALUES (?, ?, ?, ?)
                    """, [session_id, conversation_id, user_message, "user"])
                    
                    conn.execute("""
                        INSERT INTO chat_messages (session_id, conversation_id, message, role)
                        VALUES (?, ?, ?, ?)
                    """, [session_id, conversation_id, assistant_message, "assistant"])
                    
                    conn.execute("COMMIT")
                except Exception as e:
                    conn.execute("ROLLBACK")
                    raise e
    
    def get_conversation(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Get all messages for a conversation"""
        with self._get_connection() as conn:
            return conn.execute("""
                SELECT session_id, conversation_id, message, role, created_at
                FROM chat_messages 
                WHERE conversation_id = ?
                ORDER BY created_at
            """, [conversation_id]).fetchdf().to_dict('records')
    
    def get_session_conversations(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all messages for a session"""
        with self._get_connection() as conn:
            return conn.execute("""
                SELECT session_id, conversation_id, message, role, created_at
                FROM chat_messages 
                WHERE session_id = ?
                ORDER BY created_at
            """, [session_id]).fetchdf().to_dict('records')
    
    def export_to_csv(self, output_path: str, where_clause: str = ""):
        """Export messages to CSV with optional filtering"""
        with self._get_connection() as conn:
            query = f"""
                COPY (
                    SELECT session_id, conversation_id, message, role, created_at
                    FROM chat_messages
                    {f'WHERE {where_clause}' if where_clause else ''}
                    ORDER BY created_at
                ) TO '{output_path}' (HEADER, DELIMITER ',')
            """
            conn.execute(query)
            print(f"Exported to {output_path}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get basic statistics about logged conversations"""
        with self._get_connection() as conn:
            stats = conn.execute("""
                SELECT 
                    COUNT(*) as total_messages,
                    COUNT(DISTINCT session_id) as unique_sessions,
                    COUNT(DISTINCT conversation_id) as unique_conversations,
                    MIN(created_at) as earliest_message,
                    MAX(created_at) as latest_message
                FROM chat_messages
            """).fetchone()
            
            return {
                'total_messages': stats[0],
                'unique_sessions': stats[1], 
                'unique_conversations': stats[2],
                'earliest_message': stats[3],
                'latest_message': stats[4]
            }
