"""
Session Manager Module with Redis Backend and In-memory Fallback
Handles session and conversation tracking for the chat application using Redis for persistence.
Falls back to in-memory storage if Redis is unavailable.
"""

import json
import redis
import socket
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Union, Any
import logging
from contextlib import contextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SessionManager:
    """
    Manages user sessions and conversations using Redis for persistence.
    Provides scalable, distributed session management with automatic expiration.
    Falls back to in-memory storage if Redis is unavailable.
    """
    
    def __init__(self, 
                 redis_host: str = 'localhost', 
                 redis_port: int = 6379, 
                 redis_db: int = 0,
                 redis_password: Optional[str] = None,
                 key_prefix: str = 'chat_app',
                 default_session_ttl: int = 86400,  # 24 hours in seconds
                 default_conversation_ttl: int = 86400,
                 connection_timeout: float = 5.0):  # 5 second timeout
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
            connection_timeout: Timeout for Redis connection in seconds
        """
        self.key_prefix = key_prefix
        self.default_session_ttl = default_session_ttl
        self.default_conversation_ttl = default_conversation_ttl
        self.redis_available = False  # Flag to track Redis availability
        
        # Initialize in-memory storage as fallback
        self.sessions = {}
        self.conversations = {}
        self.stats = {'total_sessions': 0, 'total_conversations': 0, 'total_messages': 0}
        
        # Initialize Redis connection pool with timeouts
        try:
            print(f"Initializing Redis connection pool to {redis_host}:{redis_port}...")
            self.redis_pool = redis.ConnectionPool(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
                decode_responses=True,
                max_connections=20,
                socket_timeout=connection_timeout,
                socket_connect_timeout=connection_timeout
            )
            
            # Test connection
            self._test_connection()
        except Exception as e:
            logger.error(f"Failed to initialize Redis: {e}")
            logger.warning("Continuing with in-memory fallback")
    
    def _test_connection(self) -> None:
        """Test Redis connection and log status."""
        try:
            print("Testing Redis connection...")
            # First try a simple Redis client to see if Redis is running
            test_client = redis.Redis(
                host='localhost', 
                port=6379, 
                decode_responses=True,
                socket_timeout=5.0
            )
            test_client.ping()
            print("Redis ping successful!")
            
            # Now try with the connection pool
            with self._get_redis_client() as client:
                client.ping()
                
            self.redis_available = True
            logger.info("Redis connection established successfully")
            print("Redis connection successful!")
        except redis.exceptions.ConnectionError as e:
            self.redis_available = False
            logger.error(f"Failed to connect to Redis: {e}")
            logger.warning("Continuing without Redis - using in-memory storage")
            print(f"Redis connection failed: {e}. Using in-memory storage.")
        except redis.exceptions.RedisError as e:
            self.redis_available = False
            logger.error(f"Redis error: {e}")
            logger.warning("Continuing without Redis - using in-memory storage")
            print(f"Redis error: {e}. Using in-memory storage.")
        except Exception as e:
            self.redis_available = False
            logger.error(f"Unexpected error testing Redis connection: {e}")
            logger.warning("Continuing without Redis - using in-memory storage")
            print(f"Redis connection error: {e}. Using in-memory storage.")
    
    @contextmanager
    def _get_redis_client(self):
        """Context manager for Redis client with error handling."""
        if not hasattr(self, 'redis_pool'):
            raise redis.ConnectionError("Redis pool not initialized")
            
        try:
            client = redis.Redis(connection_pool=self.redis_pool)
            # Test the connection with a ping
            client.ping()
            yield client
        except redis.ConnectionError as e:
            logger.error(f"Redis connection failed: {e}")
            self.redis_available = False
            raise
        except redis.RedisError as e:
            logger.error(f"Redis operation failed: {e}")
            self.redis_available = False
            raise
        except Exception as e:
            logger.error(f"Unexpected Redis error: {e}")
            self.redis_available = False
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
        Initialize a new session.
        
        Args:
            session_id: Unique identifier for the session
            session_start_time: ISO timestamp when session started
            ttl: Time-to-live in seconds (uses default if None)
            
        Returns:
            dict: Session data
        """
        # Use in-memory storage if Redis is not available
        if not hasattr(self, 'redis_pool') or not self.redis_available:
            return self._initialize_session_in_memory(session_id, session_start_time)
        
        # Try Redis first, fall back to in-memory if it fails
        try:
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
                
        except Exception as e:
            logger.error(f"Redis error in initialize_session: {e}")
            self.redis_available = False  # Mark Redis as unavailable
            return self._initialize_session_in_memory(session_id, session_start_time)
    
    def _initialize_session_in_memory(self, session_id: str, session_start_time: str) -> dict:
        """Initialize a new session in memory."""
        if session_id in self.sessions:
            logger.info(f"Session {session_id} already exists in memory, returning existing data")
            return self.sessions[session_id]
        
        session_data = {
            'session_id': session_id,
            'start_time': session_start_time,
            'created_at': datetime.now().isoformat(),
            'conversation_count': 0,
            'message_count': 0,
            'conversations': []
        }
        
        self.sessions[session_id] = session_data
        self.stats['total_sessions'] += 1
        logger.info(f"Initialized new session in memory: {session_id}")
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
        # Use in-memory storage if Redis is not available
        if not hasattr(self, 'redis_pool') or not self.redis_available:
            return self._initialize_conversation_in_memory(
                conversation_id, conversation_start_time, session_id, system_prompt)
        
        # Try Redis first, fall back to in-memory if it fails
        try:
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
                
        except Exception as e:
            logger.error(f"Redis error in initialize_conversation: {e}")
            self.redis_available = False  # Mark Redis as unavailable
            return self._initialize_conversation_in_memory(
                conversation_id, conversation_start_time, session_id, system_prompt)
    
    def _initialize_conversation_in_memory(self, 
                                        conversation_id: str, 
                                        conversation_start_time: str, 
                                        session_id: str,
                                        system_prompt: Optional[str] = None) -> dict:
        """Initialize a new conversation in memory."""
        if conversation_id in self.conversations:
            logger.info(f"Conversation {conversation_id} already exists in memory, returning existing data")
            return self.conversations[conversation_id]
        
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
        
        self.conversations[conversation_id] = conversation_data
        
        # Update session if it exists
        if session_id in self.sessions:
            self.sessions[session_id]['conversation_count'] += 1
            if 'conversations' not in self.sessions[session_id]:
                self.sessions[session_id]['conversations'] = []
            self.sessions[session_id]['conversations'].append(conversation_id)
        
        self.stats['total_conversations'] += 1
        logger.info(f"Initialized new conversation in memory: {conversation_id} for session: {session_id}")
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
        # Use in-memory storage if Redis is not available
        if not hasattr(self, 'redis_pool') or not self.redis_available:
            self._add_message_to_conversation_in_memory(conversation_id, message, response, session_id)
            return
        
        # Try Redis first, fall back to in-memory if it fails
        try:
            conversation_key = self._conversation_key(conversation_id)
            session_key = self._session_key(session_id)
            
            with self._get_redis_client() as client:
                conversation_data = self._deserialize_data(client.get(conversation_key))
                
                if not conversation_data:
                    logger.warning(f"Conversation {conversation_id} not found in Redis, using in-memory fallback")
                    self._add_message_to_conversation_in_memory(conversation_id, message, response, session_id)
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
                
        except Exception as e:
            logger.error(f"Redis error in add_message_to_conversation: {e}")
            self.redis_available = False  # Mark Redis as unavailable
            self._add_message_to_conversation_in_memory(conversation_id, message, response, session_id)
    
    def _add_message_to_conversation_in_memory(self, 
                                            conversation_id: str, 
                                            message: str, 
                                            response: str, 
                                            session_id: str) -> None:
        """Add a message and response to the conversation history in memory."""
        if conversation_id not in self.conversations:
            logger.warning(f"Conversation {conversation_id} not found in memory")
            # Create a new conversation if it doesn't exist
            self._initialize_conversation_in_memory(conversation_id, datetime.now().isoformat(), session_id)
        
        # Add user message and assistant response
        timestamp = datetime.now().isoformat()
        
        if 'messages' not in self.conversations[conversation_id]:
            self.conversations[conversation_id]['messages'] = []
            
        self.conversations[conversation_id]['messages'].extend([
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
        
        if 'message_count' not in self.conversations[conversation_id]:
            self.conversations[conversation_id]['message_count'] = 0
            
        self.conversations[conversation_id]['message_count'] += 2
        
        # Update session message count
        if session_id in self.sessions:
            if 'message_count' not in self.sessions[session_id]:
                self.sessions[session_id]['message_count'] = 0
            self.sessions[session_id]['message_count'] += 2
        
        self.stats['total_messages'] += 2
        logger.debug(f"Added message pair to conversation {conversation_id} in memory")
    
    def get_session(self, session_id: str) -> Optional[dict]:
        """
        Get session data by ID.
        
        Args:
            session_id: Session identifier
            
        Returns:
            dict or None: Session data if found
        """
        # Use in-memory storage if Redis is not available
        if not hasattr(self, 'redis_pool') or not self.redis_available:
            return self.sessions.get(session_id)
        
        # Try Redis first, fall back to in-memory if it fails
        try:
            session_key = self._session_key(session_id)
            
            with self._get_redis_client() as client:
                session_data = client.get(session_key)
                return self._deserialize_data(session_data) if session_data else None
                
        except Exception as e:
            logger.error(f"Redis error in get_session: {e}")
            self.redis_available = False  # Mark Redis as unavailable
            return self.sessions.get(session_id)
    
    def get_conversation(self, conversation_id: str) -> Optional[dict]:
        """
        Get conversation data by ID.
        
        Args:
            conversation_id: Conversation identifier
            
        Returns:
            dict or None: Conversation data if found
        """
        # Use in-memory storage if Redis is not available
        if not hasattr(self, 'redis_pool') or not self.redis_available:
            return self.conversations.get(conversation_id)
        
        # Try Redis first, fall back to in-memory if it fails
        try:
            conversation_key = self._conversation_key(conversation_id)
            
            with self._get_redis_client() as client:
                conversation_data = client.get(conversation_key)
                return self._deserialize_data(conversation_data) if conversation_data else None
                
        except Exception as e:
            logger.error(f"Redis error in get_conversation: {e}")
            self.redis_available = False  # Mark Redis as unavailable
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
        # Use in-memory storage if Redis is not available
        if not hasattr(self, 'redis_pool') or not self.redis_available:
            session_data = self.sessions.get(session_id, {})
            return session_data.get('conversations', [])
        
        # Try Redis first, fall back to in-memory if it fails
        try:
            conversations_key = self._session_conversations_key(session_id)
            
            with self._get_redis_client() as client:
                return client.lrange(conversations_key, 0, -1)
                
        except Exception as e:
            logger.error(f"Redis error in get_session_conversations: {e}")
            self.redis_available = False  # Mark Redis as unavailable
            session_data = self.sessions.get(session_id, {})
            return session_data.get('conversations', [])
    
    def get_session_stats(self) -> dict:
        """
        Get overall statistics about sessions and conversations.
        
        Returns:
            dict: Statistics summary
        """
        # Use in-memory storage if Redis is not available
        if not hasattr(self, 'redis_pool') or not self.redis_available:
            return self.stats
        
        # Try Redis first, fall back to in-memory if it fails
        try:
            stats_key = self._stats_key()
            
            with self._get_redis_client() as client:
                stats = client.hgetall(stats_key) or {}
                return {
                    'total_sessions': int(stats.get('total_sessions', 0)),
                    'total_conversations': int(stats.get('total_conversations', 0)),
                    'total_messages': int(stats.get('total_messages', 0))
                }
                
        except Exception as e:
            logger.error(f"Redis error in get_session_stats: {e}")
            self.redis_available = False  # Mark Redis as unavailable
            return self.stats
    
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
        # Use in-memory storage if Redis is not available
        if not hasattr(self, 'redis_pool') or not self.redis_available:
            return self._cleanup_old_sessions_in_memory(max_age_hours)
        
        # Try Redis first, fall back to in-memory if it fails
        try:
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
                
        except Exception as e:
            logger.error(f"Redis error in cleanup_old_sessions: {e}")
            self.redis_available = False  # Mark Redis as unavailable
            return self._cleanup_old_sessions_in_memory(max_age_hours)
    
    def _cleanup_old_sessions_in_memory(self, max_age_hours: int = 24) -> int:
        """Clean up old sessions in memory."""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        cutoff_timestamp = cutoff_time.isoformat()
        
        sessions_to_remove = []
        conversations_to_remove = []
        
        for session_id, session_data in self.sessions.items():
            created_at = session_data.get('created_at', '')
            
            if created_at < cutoff_timestamp:
                sessions_to_remove.append(session_id)
                conversations_to_remove.extend(session_data.get('conversations', []))
        
        # Remove sessions
        for session_id in sessions_to_remove:
            del self.sessions[session_id]
        
        # Remove conversations
        for conversation_id in conversations_to_remove:
            if conversation_id in self.conversations:
                del self.conversations[conversation_id]
        
        # Update stats
        self.stats['total_sessions'] -= len(sessions_to_remove)
        self.stats['total_conversations'] -= len(conversations_to_remove)
        
        if sessions_to_remove:
            logger.info(f"Cleaned up {len(sessions_to_remove)} old sessions in memory")
        
        return len(sessions_to_remove)
    
    def health_check(self) -> dict:
        """
        Perform a health check on the Redis connection and return status.
        
        Returns:
            dict: Health status information
        """
        status = {
            'status': 'healthy',
            'backend': 'in-memory',
            'session_count': len(self.sessions),
            'conversation_count': len(self.conversations),
            'total_messages': self.stats.get('total_messages', 0)
        }
        
        if hasattr(self, 'redis_pool'):
            try:
                with self._get_redis_client() as client:
                    # Test basic operations
                    test_key = f"{self.key_prefix}:health_check"
                    client.set(test_key, "ok", ex=10)
                    value = client.get(test_key)
                    client.delete(test_key)
                    
                    # Get Redis info
                    info = client.info()
                    
                    status.update({
                        'backend': 'redis',
                        'redis_available': True,
                        'redis_version': info.get('redis_version'),
                        'connected_clients': info.get('connected_clients'),
                        'used_memory_human': info.get('used_memory_human'),
                        'test_result': value == 'ok'
                    })
                    
                    self.redis_available = True  # Mark Redis as available
            except Exception as e:
                status.update({
                    'backend': 'in-memory (redis fallback)',
                    'redis_available': False,
                    'redis_error': str(e)
                })
                self.redis_available = False  # Mark Redis as unavailable
        
        return status
    
    def print_redis_summary(self):
            """Print a human-readable summary of Redis contents."""
            if not hasattr(self, 'redis_pool') or not self.redis_available:
                print("\n=== Redis not available, using in-memory storage ===")
                print(f"Sessions: {len(self.sessions)}")
                print(f"Conversations: {len(self.conversations)}")
                print(f"Total messages: {self.stats.get('total_messages', 0)}")
                return
                
            try:
                with self._get_redis_client() as client:
                    # Get all keys for this app
                    pattern = f"{self.key_prefix}:*"
                    all_keys = list(client.scan_iter(match=pattern))
                    
                    sessions = []
                    conversations = []
                    other_keys = []
                    
                    for key in all_keys:
                        if ':session:' in key and not key.endswith(':conversations'):
                            sessions.append(key)
                        elif ':conversation:' in key:
                            conversations.append(key)
                        else:
                            other_keys.append(key)
                    
                    print(f"\n=== Redis Contents Summary (Prefix: {self.key_prefix}) ===")
                    print(f"Total Keys: {len(all_keys)}")
                    
                    print(f"\nSessions ({len(sessions)}): ")
                    for session_key in sessions[:5]:  # Show only first 5
                        ttl = client.ttl(session_key)
                        ttl_readable = f"{ttl // 3600}h {(ttl % 3600) // 60}m {ttl % 60}s" if ttl > 0 else "No expiration" if ttl == -1 else "Expired"
                        print(f"  📱 {session_key}: TTL={ttl_readable}")
                    
                    if len(sessions) > 5:
                        print(f"  ... and {len(sessions) - 5} more")
                    
                    print(f"\nConversations ({len(conversations)}): ")
                    for conv_key in conversations[:5]:  # Show only first 5
                        ttl = client.ttl(conv_key)
                        ttl_readable = f"{ttl // 3600}h {(ttl % 3600) // 60}m {ttl % 60}s" if ttl > 0 else "No expiration" if ttl == -1 else "Expired"
                        print(f"  💬 {conv_key}: TTL={ttl_readable}")
                    
                    if len(conversations) > 5:
                        print(f"  ... and {len(conversations) - 5} more")
                    
                    if other_keys:
                        print(f"\nOther Keys ({len(other_keys)}): ")
                        for key in other_keys[:5]:  # Show only first 5
                            key_type = client.type(key)
                            ttl = client.ttl(key)
                            ttl_readable = f"{ttl // 3600}h {(ttl % 3600) // 60}m {ttl % 60}s" if ttl > 0 else "No expiration" if ttl == -1 else "Expired"
                            print(f"  🔑 {key}: {key_type}, TTL={ttl_readable}")
                        
                        if len(other_keys) > 5:
                            print(f"  ... and {len(other_keys) - 5} more")
            
            except Exception as e:
                print(f"Error getting Redis summary: {e}")
                print("Using in-memory storage as fallback")
                print(f"Sessions: {len(self.sessions)}")
                print(f"Conversations: {len(self.conversations)}")
                print(f"Total messages: {self.stats.get('total_messages', 0)}")


def test_redis_connection():
    """
    Standalone function to test Redis connectivity.
    This can be run directly to diagnose Redis connection issues.
    """
    print("Testing direct Redis connection...")
    try:
        # Try simplest possible connection
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        result = r.ping()
        print(f"Basic Redis ping successful: {result}")
        
        # Try setting and getting a value
        r.set('test_key', 'test_value')
        value = r.get('test_key')
        print(f"Redis set/get test: {value == 'test_value'}")
        r.delete('test_key')
        
        print("Redis connection test passed!")
        return True
    except Exception as e:
        print(f"Redis connection test failed: {e}")
        return False

# Run the test function if this script is executed directly
if __name__ == "__main__":
    test_redis_connection()