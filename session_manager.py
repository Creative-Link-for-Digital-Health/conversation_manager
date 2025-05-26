"""
Session Manager Module
Handles session and conversation tracking for the chat application.
"""

from datetime import datetime
from typing import Dict, Optional, List

class SessionManager:
    """
    Manages user sessions and conversations.
    In production, this would interface with a database instead of in-memory storage.
    """
    
    def __init__(self):
        # In-memory storage for demo purposes TODO change me to REDIS implementation!!!
        self.sessions: Dict[str, dict] = {}
        self.conversations: Dict[str, dict] = {}
    
    def initialize_session(self, session_id: str, session_start_time: str) -> dict:
        """
        Initialize a new session.
        
        Args:
            session_id: Unique identifier for the session
            session_start_time: ISO timestamp when session started
            
        Returns:
            dict: Session data
        """
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                'session_id': session_id,
                'start_time': session_start_time,
                'created_at': datetime.now().isoformat(),
                'conversation_count': 0,
                'message_count': 0,
                'conversations': []
            }
            print(f"Initialized new session: {session_id}")
        return self.sessions[session_id]
    
    def initialize_conversation(self, conversation_id: str, conversation_start_time: str, session_id: str) -> dict:
        """
        Initialize a new conversation within a session.
        
        Args:
            conversation_id: Unique identifier for the conversation
            conversation_start_time: ISO timestamp when conversation started
            session_id: Session this conversation belongs to
            
        Returns:
            dict: Conversation data
        """
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = {
                'conversation_id': conversation_id,
                'session_id': session_id,
                'start_time': conversation_start_time,
                'created_at': datetime.now().isoformat(),
                'messages': [],
                'message_count': 0
            }
            
            # Update session conversation count
            if session_id in self.sessions:
                self.sessions[session_id]['conversation_count'] += 1
                self.sessions[session_id]['conversations'].append(conversation_id)
            
            print(f"Initialized new conversation: {conversation_id} for session: {session_id}")
        return self.conversations[conversation_id]
    
    def add_message_to_conversation(self, conversation_id: str, message: str, response: str, session_id: str) -> None:
        """
        Add a message and response to the conversation history.
        
        Args:
            conversation_id: Conversation to add message to
            message: User's message
            response: AI's response
            session_id: Session this conversation belongs to
        """
        if conversation_id in self.conversations:
            self.conversations[conversation_id]['messages'].append({
                'timestamp': datetime.now().isoformat(),
                'user_message': message,
                'ai_response': response
            })
            self.conversations[conversation_id]['message_count'] += 1
            
            # Update session message count
            if session_id in self.sessions:
                self.sessions[session_id]['message_count'] += 1
    
    def get_session(self, session_id: str) -> Optional[dict]:
        """
        Get session data by ID.
        
        Args:
            session_id: Session identifier
            
        Returns:
            dict or None: Session data if found
        """
        return self.sessions.get(session_id)
    
    def get_conversation(self, conversation_id: str) -> Optional[dict]:
        """
        Get conversation data by ID.
        
        Args:
            conversation_id: Conversation identifier
            
        Returns:
            dict or None: Conversation data if found
        """
        return self.conversations.get(conversation_id)
    
    def get_conversation_messages(self, conversation_id: str, limit: int = 10) -> List[dict]:
        """
        Get recent messages from a conversation for context.
        
        Args:
            conversation_id: Conversation identifier
            limit: Maximum number of messages to return
            
        Returns:
            list: Recent messages
        """
        if conversation_id in self.conversations:
            return self.conversations[conversation_id]['messages'][-limit:]
        return []
    
    def get_session_stats(self) -> dict:
        """
        Get overall statistics about sessions and conversations.
        
        Returns:
            dict: Statistics summary
        """
        return {
            'total_sessions': len(self.sessions),
            'total_conversations': len(self.conversations),
            'total_messages': sum(session['message_count'] for session in self.sessions.values())
        }
    
    def cleanup_old_sessions(self, max_age_hours: int = 24) -> int:
        """
        Clean up old sessions (for demo purposes).
        In production, this would be handled by database TTL or background jobs.
        
        Args:
            max_age_hours: Maximum age of sessions to keep
            
        Returns:
            int: Number of sessions cleaned up
        """
        from datetime import datetime, timedelta
        
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        sessions_to_remove = []
        conversations_to_remove = []
        
        for session_id, session_data in self.sessions.items():
            session_created = datetime.fromisoformat(session_data['created_at'])
            if session_created < cutoff_time:
                sessions_to_remove.append(session_id)
                # Also remove associated conversations
                conversations_to_remove.extend(session_data['conversations'])
        
        # Remove old sessions and conversations
        for session_id in sessions_to_remove:
            del self.sessions[session_id]
        
        for conv_id in conversations_to_remove:
            if conv_id in self.conversations:
                del self.conversations[conv_id]
        
        cleaned_count = len(sessions_to_remove)
        if cleaned_count > 0:
            print(f"Cleaned up {cleaned_count} old sessions and {len(conversations_to_remove)} conversations")
        
        return cleaned_count