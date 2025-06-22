import os
from datetime import datetime
from typing import Optional, List, Dict, Any
import threading
from functools import wraps

class LocalLogger:
    """
    Dummy logger that doesn't use DuckDB, to avoid the locking issues
    """
    
    def __init__(self, db_path: str = "chat_logs.db"):
        self.db_path = db_path
        print(f"Initialized dummy logger (DuckDB disabled) for path: {db_path}")
        # No database initialization
    
    def log_message(self, session_id: str, conversation_id: str, message: str, role: str):
        """Log a single message - thread-safe"""
        print(f"DUMMY LOG: {role} in {conversation_id}: {message[:50]}...")
        return True
    
    def log_conversation_turn(self, session_id: str, conversation_id: str, 
                            user_message: str, assistant_message: str):
        """Log both user and assistant messages in one transaction"""
        print(f"DUMMY LOG: Conversation turn in {conversation_id}")
        print(f"  User: {user_message[:50]}...")
        print(f"  Assistant: {assistant_message[:50]}...")
        return True
    
    def get_conversation(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Get all messages for a conversation"""
        return []  # No data stored
    
    def get_session_conversations(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all messages for a session"""
        return []  # No data stored
    
    def export_to_csv(self, output_path: str, where_clause: str = ""):
        """Export messages to CSV with optional filtering"""
        print(f"DUMMY EXPORT: Would export to {output_path}")
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get basic statistics about logged conversations"""
        return {
            'total_messages': 0,
            'unique_sessions': 0, 
            'unique_conversations': 0,
            'earliest_message': None,
            'latest_message': None,
            'note': 'Dummy logger - no actual data'
        }