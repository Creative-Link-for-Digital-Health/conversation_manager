import duckdb
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

class ChatLogger:
    def __init__(self, db_path: str = "chat_logs.db"):
        self.db_path = db_path
        self.conn = duckdb.connect(db_path)
        self._initialize_db()
    
    def _initialize_db(self):
        """Initialize database with migrations table and run any pending migrations"""
        # Create migrations tracking table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                id INTEGER PRIMARY KEY,
                name VARCHAR,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Run migrations
        self._run_migrations()
    
    def _run_migrations(self):
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
            # {
            #     'id': 2,
            #     'name': 'add_token_count',
            #     'sql': 'ALTER TABLE chat_messages ADD COLUMN token_count INTEGER'
            # },
        ]
        
        for migration in migrations:
            if not self._migration_applied(migration['id']):
                print(f"Running migration: {migration['name']}")
                self.conn.execute(migration['sql'])
                self.conn.execute("""
                    INSERT INTO _migrations (id, name) VALUES (?, ?)
                """, [migration['id'], migration['name']])
                print(f"Migration {migration['name']} completed")
    
    def _migration_applied(self, migration_id: int) -> bool:
        """Check if a migration has already been applied"""
        result = self.conn.execute("""
            SELECT COUNT(*) FROM _migrations WHERE id = ?
        """, [migration_id]).fetchone()
        return result[0] > 0
    
    def log_message(self, session_id: str, conversation_id: str, message: str, role: str):
        """Log a single message"""
        self.conn.execute("""
            INSERT INTO chat_messages (session_id, conversation_id, message, role)
            VALUES (?, ?, ?, ?)
        """, [session_id, conversation_id, message, role])
    
    def log_conversation_turn(self, session_id: str, conversation_id: str, 
                            user_message: str, assistant_message: str):
        """Log both user and assistant messages in one call"""
        self.log_message(session_id, conversation_id, user_message, "user")
        self.log_message(session_id, conversation_id, assistant_message, "assistant")
    
    def get_conversation(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Get all messages for a conversation"""
        return self.conn.execute("""
            SELECT session_id, conversation_id, message, role, created_at
            FROM chat_messages 
            WHERE conversation_id = ?
            ORDER BY created_at
        """, [conversation_id]).fetchdf().to_dict('records')
    
    def get_session_conversations(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all messages for a session"""
        return self.conn.execute("""
            SELECT session_id, conversation_id, message, role, created_at
            FROM chat_messages 
            WHERE session_id = ?
            ORDER BY created_at
        """, [session_id]).fetchdf().to_dict('records')
    
    def export_to_csv(self, output_path: str, where_clause: str = ""):
        """Export messages to CSV with optional filtering"""
        query = f"""
            COPY (
                SELECT session_id, conversation_id, message, role, created_at
                FROM chat_messages
                {f'WHERE {where_clause}' if where_clause else ''}
                ORDER BY created_at
            ) TO '{output_path}' (HEADER, DELIMITER ',')
        """
        self.conn.execute(query)
        print(f"Exported to {output_path}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get basic statistics about logged conversations"""
        stats = self.conn.execute("""
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
    
    def close(self):
        """Close database connection"""
        self.conn.close()

# Example usage
if __name__ == "__main__":
    # Initialize logger
    logger = ChatLogger("chat_logs.db")
    
    # Log some example conversations
    logger.log_conversation_turn(
        session_id="session_001",
        conversation_id="conv_001", 
        user_message="Hello, how are you?",
        assistant_message="I'm doing well, thank you! How can I help you today?"
    )
    
    logger.log_conversation_turn(
        session_id="session_001",
        conversation_id="conv_001",
        user_message="Can you explain Python decorators?",
        assistant_message="Python decorators are a way to modify or enhance functions..."
    )
    
    # Get conversation
    conv = logger.get_conversation("conv_001")
    print("Conversation:", conv)
    
    # Get stats
    stats = logger.get_stats()
    print("Stats:", stats)
    
    # Export to CSV
    logger.export_to_csv("chat_export.csv")
    
    # Export with filtering
    logger.export_to_csv("recent_chats.csv", "created_at > '2024-01-01'")
    
    logger.close()