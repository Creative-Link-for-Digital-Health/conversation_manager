"""
Session Manager Module with Redis Backend
Handles session and conversation tracking for the chat application using Redis for persistence.
"""

import json
import redis
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Union
import logging
from contextlib import contextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RedisSessionManager:
    """
    Manages user sessions and conversations using Redis for persistence.
    Provides scalable, distributed session management with automatic expiration.
    """
    
    def __init__(self, 
                 redis_host: str = 'localhost', 
                 redis_port: int = 6379, 
                 redis_db: int = 0,
                 redis_password: Optional[str] = None,
                 key_prefix: str = 'chat_app',
                 default_session_ttl: int = 86400,  # 24 hours in seconds
                 default_conversation_ttl: int = 86400):
        """
        Initialize Redis Session Manager.
        
        Args:
            redis_host: Redis server hostname
            redis_port: Redis server port
            redis_db: Redis database number
            redis_password: Redis password (if required)
            key_prefix: Prefix for all Redis keys
            default_session_ttl: Default session TTL in seconds
            default_conversation_ttl: Default conversation TTL in seconds
        """
        self.key_prefix = key_prefix
        self.default_session_ttl = default_session_ttl
        self.default_conversation_ttl = default_conversation_ttl
        
        # Initialize Redis connection pool
        self.redis_pool = redis.ConnectionPool(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True,
            max_connections=20
        )
        
        # Test connection
        self._test_connection()
    
    def _test_connection(self) -> None:
        """Test Redis connection and log status."""
        try:
            with self._get_redis_client() as client:
                client.ping()
            logger.info("Redis connection established successfully")
        except redis.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    @contextmanager
    def _get_redis_client(self):
        """Context manager for Redis client with error handling."""
        client = redis.Redis(connection_pool=self.redis_pool)
        try:
            yield client
        except redis.RedisError as e:
            logger.error(f"Redis operation failed: {e}")
            raise
    
    def _session_key(self, session_id: str) -> str:
        """Generate Redis key for session data."""
        return f"{self.key_prefix}:session:{session_id}"
    
    def _conversation_key(self, conversation_id: str) -> str:
        """Generate Redis key for conversation data."""
        return f"{self.key_prefix}:conversation:{conversation_id}"
    
    def _session_conversations_key(self, session_id: str) -> str:
        """Generate Redis key for session's conversation list."""
        return f"{self.key_prefix}:session:{session_id}:conversations"
    
    def _stats_key(self) -> str:
        """Generate Redis key for global stats."""
        return f"{self.key_prefix}:stats"
    
    def _serialize_data(self, data: dict) -> str:
        """Serialize data to JSON string."""
        return json.dumps(data, default=str)
    
    def _deserialize_data(self, data: str) -> dict:
        """Deserialize JSON string to dict."""
        return json.loads(data) if data else {}
    
    def initialize_session(self, session_id: str, session_start_time: str, ttl: Optional[int] = None) -> dict:
        """
        Initialize a new session in Redis.
        
        Args:
            session_id: Unique identifier for the session
            session_start_time: ISO timestamp when session started
            ttl: Time-to-live in seconds (uses default if None)
            
        Returns:
            dict: Session data
        """
        session_key = self._session_key(session_id)
        conversations_key = self._session_conversations_key(session_id)
        ttl = ttl or self.default_session_ttl
        
        with self._get_redis_client() as client:
            # Check if session already exists
            if client.exists(session_key):
                existing_data = self._deserialize_data(client.get(session_key))
                logger.info(f"Session {session_id} already exists, returning existing data")
                return existing_data
            
            session_data = {
                'session_id': session_id,
                'start_time': session_start_time,
                'created_at': datetime.now().isoformat(),
                'conversation_count': 0,
                'message_count': 0,
                'conversations': []
            }
            
            # Use pipeline for atomic operations
            pipe = client.pipeline()
            pipe.set(session_key, self._serialize_data(session_data), ex=ttl)
            pipe.expire(conversations_key, ttl)  # Initialize conversations list with TTL
            
            # Update global stats
            pipe.hincrby(self._stats_key(), 'total_sessions', 1)
            
            pipe.execute()
            
            logger.info(f"Initialized new session: {session_id} with TTL: {ttl}s")
            return session_data
    
    def initialize_conversation(self, 
                              conversation_id: str, 
                              conversation_start_time: str, 
                              session_id: str, 
                              system_prompt: Optional[str] = None,
                              ttl: Optional[int] = None) -> dict:
        """
        Initialize a new conversation within a session.
        
        Args:
            conversation_id: Unique identifier for the conversation
            conversation_start_time: ISO timestamp when conversation started
            session_id: Parent session identifier
            system_prompt: Optional system prompt to start with
            ttl: Time-to-live in seconds (uses default if None)
            
        Returns:
            dict: Conversation data
        """
        conversation_key = self._conversation_key(conversation_id)
        session_key = self._session_key(session_id)
        conversations_key = self._session_conversations_key(session_id)
        ttl = ttl or self.default_conversation_ttl
        
        with self._get_redis_client() as client:
            # Check if conversation already exists
            if client.exists(conversation_key):
                existing_data = self._deserialize_data(client.get(conversation_key))
                logger.info(f"Conversation {conversation_id} already exists")
                return existing_data
            
            # Start with system message if provided
            initial_messages = []
            if system_prompt:
                initial_messages.append({
                    'role': 'system',
                    'content': system_prompt,
                    'timestamp': datetime.now().isoformat()
                })
            
            conversation_data = {
                'conversation_id': conversation_id,
                'session_id': session_id,
                'start_time': conversation_start_time,
                'created_at': datetime.now().isoformat(),
                'messages': initial_messages,
                'message_count': len(initial_messages)
            }
            
            # Use pipeline for atomic operations
            pipe = client.pipeline()
            
            # Store conversation data
            pipe.set(conversation_key, self._serialize_data(conversation_data), ex=ttl)
            
            # Add conversation to session's conversation list
            pipe.lpush(conversations_key, conversation_id)
            pipe.expire(conversations_key, ttl)
            
            # Update session data
            if client.exists(session_key):
                session_data = self._deserialize_data(client.get(session_key))
                session_data['conversation_count'] += 1
                session_data['conversations'].append(conversation_id)
                pipe.set(session_key, self._serialize_data(session_data), ex=ttl)
            
            # Update global stats
            pipe.hincrby(self._stats_key(), 'total_conversations', 1)
            
            pipe.execute()
            
            logger.info(f"Initialized new conversation: {conversation_id} for session: {session_id}")
            return conversation_data
    
    def add_message_to_conversation(self, 
                                  conversation_id: str, 
                                  message: str, 
                                  response: str, 
                                  session_id: str) -> None:
        """
        Add a message and response to the conversation history.
        
        Args:
            conversation_id: Conversation identifier
            message: User message
            response: Assistant response
            session_id: Session identifier
        """
        conversation_key = self._conversation_key(conversation_id)
        session_key = self._session_key(session_id)
        
        with self._get_redis_client() as client:
            conversation_data = self._deserialize_data(client.get(conversation_key))
            
            if not conversation_data:
                logger.warning(f"Conversation {conversation_id} not found")
                return
            
            # Add user message and assistant response
            timestamp = datetime.now().isoformat()
            
            conversation_data['messages'].extend([
                {
                    'role': 'user',
                    'content': message,
                    'timestamp': timestamp
                },
                {
                    'role': 'assistant',
                    'content': response,
                    'timestamp': timestamp
                }
            ])
            
            conversation_data['message_count'] += 2
            
            # Use pipeline for atomic operations
            pipe = client.pipeline()
            
            # Update conversation (preserve existing TTL)
            pipe.set(conversation_key, self._serialize_data(conversation_data), keepttl=True)
            
            # Update session message count
            if client.exists(session_key):
                session_data = self._deserialize_data(client.get(session_key))
                session_data['message_count'] += 2
                pipe.set(session_key, self._serialize_data(session_data), keepttl=True)
            
            # Update global stats
            pipe.hincrby(self._stats_key(), 'total_messages', 2)
            
            pipe.execute()
            
            logger.debug(f"Added message pair to conversation {conversation_id}")
    
    def get_session(self, session_id: str) -> Optional[dict]:
        """
        Get session data by ID.
        
        Args:
            session_id: Session identifier
            
        Returns:
            dict or None: Session data if found
        """
        session_key = self._session_key(session_id)
        
        with self._get_redis_client() as client:
            session_data = client.get(session_key)
            return self._deserialize_data(session_data) if session_data else None
    
    def get_conversation(self, conversation_id: str) -> Optional[dict]:
        """
        Get conversation data by ID.
        
        Args:
            conversation_id: Conversation identifier
            
        Returns:
            dict or None: Conversation data if found
        """
        conversation_key = self._conversation_key(conversation_id)
        
        with self._get_redis_client() as client:
            conversation_data = client.get(conversation_key)
            return self._deserialize_data(conversation_data) if conversation_data else None
    
    def get_conversation_messages(self, conversation_id: str, limit: int = 10) -> List[dict]:
        """
        Get recent messages from a conversation for context.
        
        Args:
            conversation_id: Conversation identifier
            limit: Maximum number of messages to return
            
        Returns:
            list: Recent messages
        """
        conversation_data = self.get_conversation(conversation_id)
        if conversation_data and 'messages' in conversation_data:
            return conversation_data['messages'][-limit:]
        return []
    
    def get_session_conversations(self, session_id: str) -> List[str]:
        """
        Get list of conversation IDs for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            list: List of conversation IDs
        """
        conversations_key = self._session_conversations_key(session_id)
        
        with self._get_redis_client() as client:
            return client.lrange(conversations_key, 0, -1)
    
    def get_session_stats(self) -> dict:
        """
        Get overall statistics about sessions and conversations.
        
        Returns:
            dict: Statistics summary
        """
        stats_key = self._stats_key()
        
        with self._get_redis_client() as client:
            stats = client.hgetall(stats_key)
            return {
                'total_sessions': int(stats.get('total_sessions', 0)),
                'total_conversations': int(stats.get('total_conversations', 0)),
                'total_messages': int(stats.get('total_messages', 0))
            }
    
    def cleanup_old_sessions(self, max_age_hours: int = 24) -> int:
        """
        Clean up old sessions and conversations.
        
        Note: With Redis TTL, most cleanup happens automatically.
        This method manually cleans up any sessions older than specified age.
        
        Args:
            max_age_hours: Maximum age of sessions to keep
            
        Returns:
            int: Number of sessions cleaned up
        """
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        cutoff_timestamp = cutoff_time.isoformat()
        
        cleaned_count = 0
        
        with self._get_redis_client() as client:
            # Use SCAN to iterate through session keys
            session_pattern = f"{self.key_prefix}:session:*"
            
            for key in client.scan_iter(match=session_pattern):
                if not key.endswith(':conversations'):  # Skip conversation lists
                    session_data = client.get(key)
                    if session_data:
                        data = self._deserialize_data(session_data)
                        created_at = data.get('created_at', '')
                        
                        if created_at < cutoff_timestamp:
                            session_id = data.get('session_id')
                            if session_id:
                                # Delete session and its conversations
                                pipe = client.pipeline()
                                pipe.delete(key)  # Delete session
                                pipe.delete(self._session_conversations_key(session_id))
                                
                                # Delete associated conversations
                                for conv_id in data.get('conversations', []):
                                    pipe.delete(self._conversation_key(conv_id))
                                
                                pipe.execute()
                                cleaned_count += 1
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} old sessions")
        
        return cleaned_count
    
    def extend_session_ttl(self, session_id: str, additional_seconds: int = 3600) -> bool:
        """
        Extend the TTL of a session and its conversations.
        
        Args:
            session_id: Session identifier
            additional_seconds: Additional seconds to add to TTL
            
        Returns:
            bool: True if successful, False if session not found
        """
        session_key = self._session_key(session_id)
        conversations_key = self._session_conversations_key(session_id)
        
        with self._get_redis_client() as client:
            if not client.exists(session_key):
                return False
            
            # Extend session and conversations list TTL
            pipe = client.pipeline()
            pipe.expire(session_key, client.ttl(session_key) + additional_seconds)
            pipe.expire(conversations_key, client.ttl(conversations_key) + additional_seconds)
            
            # Extend all conversation TTLs
            conversation_ids = client.lrange(conversations_key, 0, -1)
            for conv_id in conversation_ids:
                conv_key = self._conversation_key(conv_id)
                current_ttl = client.ttl(conv_key)
                if current_ttl > 0:
                    pipe.expire(conv_key, current_ttl + additional_seconds)
            
            pipe.execute()
            
            logger.info(f"Extended TTL for session {session_id} by {additional_seconds} seconds")
            return True
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session and all its conversations.
        
        Args:
            session_id: Session identifier
            
        Returns:
            bool: True if successful, False if session not found
        """
        session_key = self._session_key(session_id)
        conversations_key = self._session_conversations_key(session_id)
        
        with self._get_redis_client() as client:
            session_data = self.get_session(session_id)
            if not session_data:
                return False
            
            pipe = client.pipeline()
            
            # Delete session and conversations list
            pipe.delete(session_key)
            pipe.delete(conversations_key)
            
            # Delete all conversations
            for conv_id in session_data.get('conversations', []):
                pipe.delete(self._conversation_key(conv_id))
            
            # Update stats
            pipe.hincrby(self._stats_key(), 'total_sessions', -1)
            pipe.hincrby(self._stats_key(), 'total_conversations', 
                        -len(session_data.get('conversations', [])))
            pipe.hincrby(self._stats_key(), 'total_messages', 
                        -session_data.get('message_count', 0))
            
            pipe.execute()
            
            logger.info(f"Deleted session {session_id} and its conversations")
            return True
    
    def debug_redis_contents(self, detailed: bool = False) -> dict:
        """
        Debug method to inspect all Redis contents for this application.
        
        Args:
            detailed: If True, includes full content of each key
            
        Returns:
            dict: Redis contents summary
        """
        with self._get_redis_client() as client:
            # Get all keys for this app
            pattern = f"{self.key_prefix}:*"
            all_keys = list(client.scan_iter(match=pattern))
            
            contents = {
                'total_keys': len(all_keys),
                'sessions': {},
                'conversations': {},
                'stats': {},
                'other_keys': {}
            }
            
            for key in all_keys:
                key_type = client.type(key)
                ttl = client.ttl(key)
                
                key_info = {
                    'type': key_type,
                    'ttl': ttl,
                    'ttl_readable': f"{ttl // 3600}h {(ttl % 3600) // 60}m {ttl % 60}s" if ttl > 0 else "No expiration" if ttl == -1 else "Expired"
                }
                
                if detailed:
                    if key_type == 'string':
                        key_info['content'] = self._deserialize_data(client.get(key))
                    elif key_type == 'list':
                        key_info['content'] = client.lrange(key, 0, -1)
                    elif key_type == 'hash':
                        key_info['content'] = client.hgetall(key)
                
                # Categorize keys
                if ':session:' in key and not key.endswith(':conversations'):
                    session_id = key.split(':session:')[1]
                    contents['sessions'][session_id] = key_info
                elif ':conversation:' in key:
                    conv_id = key.split(':conversation:')[1]
                    contents['conversations'][conv_id] = key_info
                elif ':stats' in key:
                    contents['stats'] = key_info
                elif ':conversations' in key:
                    session_id = key.split(':session:')[1].replace(':conversations', '')
                    if session_id not in contents['sessions']:
                        contents['sessions'][session_id] = {}
                    contents['sessions'][session_id]['conversations_list'] = key_info
                else:
                    contents['other_keys'][key] = key_info
            
            return contents
    
    def print_redis_summary(self):
        """Print a human-readable summary of Redis contents."""
        contents = self.debug_redis_contents(detailed=False)
        
        print(f"\n=== Redis Contents Summary (Prefix: {self.key_prefix}) ===")
        print(f"Total Keys: {contents['total_keys']}")
        
        print(f"\nSessions ({len(contents['sessions'])}): ")
        for session_id, info in contents['sessions'].items():
            print(f"  📱 {session_id}: TTL={info.get('ttl_readable', 'N/A')}")
            if 'conversations_list' in info:
                conv_list = info['conversations_list']
                print(f"     └── Conversations list: TTL={conv_list.get('ttl_readable', 'N/A')}")
        
        print(f"\nConversations ({len(contents['conversations'])}): ")
        for conv_id, info in contents['conversations'].items():
            print(f"  💬 {conv_id}: TTL={info.get('ttl_readable', 'N/A')}")
        
        if contents['stats']:
            print(f"\nStats: TTL={contents['stats'].get('ttl_readable', 'N/A')}")
        
        if contents['other_keys']:
            print(f"\nOther Keys ({len(contents['other_keys'])}): ")
            for key, info in contents['other_keys'].items():
                print(f"  🔑 {key}: {info['type']}, TTL={info.get('ttl_readable', 'N/A')}")
    
    def export_redis_data(self, filename: str = None) -> str:
        """
        Export all Redis data to a JSON file for backup/inspection.
        
        Args:
            filename: Output filename (auto-generated if None)
            
        Returns:
            str: Filename of exported data
        """
        import json
        from datetime import datetime
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"redis_export_{self.key_prefix}_{timestamp}.json"
        
        contents = self.debug_redis_contents(detailed=True)
        
        with open(filename, 'w') as f:
            json.dump(contents, f, indent=2, default=str)
        
        print(f"Redis data exported to: {filename}")
        return filename

    def health_check(self) -> dict:
        """
        Perform a health check on the Redis connection and return status.
        
        Returns:
            dict: Health status information
        """
        try:
            with self._get_redis_client() as client:
                # Test basic operations
                test_key = f"{self.key_prefix}:health_check"
                client.set(test_key, "ok", ex=10)
                value = client.get(test_key)
                client.delete(test_key)
                
                # Get Redis info
                info = client.info()
                
                return {
                    'status': 'healthy',
                    'redis_version': info.get('redis_version'),
                    'connected_clients': info.get('connected_clients'),
                    'used_memory_human': info.get('used_memory_human'),
                    'test_result': value == 'ok'
                }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e)
            }


# Backward compatibility alias
SessionManager = RedisSessionManager