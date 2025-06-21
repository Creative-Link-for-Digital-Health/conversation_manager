import toml
import os
import logging
from datetime import datetime, timezone
from redcap import Project, RedcapError
import uuid
from typing import Optional, Dict, Any
import time
from functools import wraps

class RedCAPLogger:
    def __init__(self, config_path: str = None):
        """
        Initialize REDCap logger from TOML config file or environment variables
        
        Args:
            config_path: Path to TOML configuration file (optional if using env vars)
        """
        self.logger = logging.getLogger(__name__)
        self.project = None
        self.config = self._load_config(config_path)
        
        # Initialize REDCap connection
        self._initialize_redcap()
        
        # Validate connection
        if not self._test_connection():
            raise ConnectionError("Failed to establish REDCap connection")

    def _load_config(self, config_path: str = None) -> Dict[str, Any]:
        """Load configuration from file or environment variables"""
        
        # Try environment variables first (production-friendly)
        api_url = os.getenv('REDCAP_API_URL')
        api_token = os.getenv('REDCAP_API_TOKEN')
        
        if api_url and api_token:
            self.logger.info("Loading REDCap config from environment variables")
            return {
                'REDCAP': {
                    'API_URL': api_url,
                    'API_TOKEN': api_token
                }
            }
        
        # Fall back to TOML file
        if config_path and os.path.exists(config_path):
            self.logger.info(f"Loading REDCap config from {config_path}")
            with open(config_path, 'r') as f:
                return toml.load(f)
        
        raise ValueError("No REDCap configuration found in environment or config file")

    def _initialize_redcap(self):
        """Initialize REDCap project connection"""
        try:
            self.project = Project(
                self.config['REDCAP']['API_URL'], 
                self.config['REDCAP']['API_TOKEN']
            )
            self.logger.info("REDCap connection initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize REDCap connection: {e}")
            raise

    def _test_connection(self) -> bool:
        """Test REDCap connection by fetching project info"""
        try:
            # Simple test - get project info
            project_info = self.project.export_project_info()
            self.logger.info(f"REDCap connection test successful. Project: {project_info.get('project_title', 'Unknown')}")
            return True
        except Exception as e:
            self.logger.error(f"REDCap connection test failed: {e}")
            return False

    def _retry_on_failure(max_retries: int = 3, delay: float = 1.0):
        """Decorator for retrying failed operations"""
        def decorator(func):
            @wraps(func)
            def wrapper(self, *args, **kwargs):
                last_exception = None
                
                for attempt in range(max_retries):
                    try:
                        return func(self, *args, **kwargs)
                    except Exception as e:
                        last_exception = e
                        if attempt < max_retries - 1:
                            self.logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                            time.sleep(delay * (2 ** attempt))  # Exponential backoff
                        else:
                            self.logger.error(f"All {max_retries} attempts failed. Last error: {e}")
                
                raise last_exception
            return wrapper
        return decorator

    @_retry_on_failure(max_retries=3)
    def log_message(self, session_id: str, conversation_id: str, message: str, role: str, 
                   metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Log a message to REDCap with retry logic
        
        Args:
            session_id: Unique session identifier
            conversation_id: Unique conversation identifier  
            message: The message content
            role: Message role (user/assistant/system)
            metadata: Optional additional data to log
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.project:
            self.logger.error("REDCap project not initialized")
            return False

        # Input validation
        if not all([session_id, conversation_id, message, role]):
            self.logger.error("Missing required parameters for logging")
            return False

        # Prepare record data
        record_data = {
            'record_id': str(uuid.uuid4()),
            'session_id': str(session_id),
            'conversation_id': str(conversation_id),
            'message': str(message)[:32000],  # REDCap field length limit
            'role': str(role).lower(),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'message_length': len(message)
        }

        # Add metadata if provided
        if metadata:
            # Flatten metadata and add prefix to avoid field conflicts
            for key, value in metadata.items():
                safe_key = f"meta_{key}"[:100]  # Ensure field name isn't too long
                record_data[safe_key] = str(value)[:1000]  # Limit value length

        try:
            # Log the attempt
            self.logger.debug(f"Logging message to REDCap: session={session_id}, conv={conversation_id}, role={role}")
            
            # Import to REDCap
            response = self.project.import_records([record_data])
            
            # Check response
            success = response.get('count', 0) > 0
            
            if success:
                self.logger.debug(f"Successfully logged message. REDCap response: {response}")
            else:
                self.logger.warning(f"REDCap import may have failed. Response: {response}")
                
            return success
            
        except RedcapError as e:
            self.logger.error(f"REDCap API error: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error logging to REDCap: {e}")
            return False

    def log_session_start(self, session_id: str, user_metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Log session start event
        
        Args:
            session_id: Unique session identifier
            user_metadata: Optional user/session metadata
            
        Returns:
            bool: True if successful, False otherwise
        """
        metadata = {'event_type': 'session_start'}
        if user_metadata:
            metadata.update(user_metadata)
            
        return self.log_message(
            session_id=session_id,
            conversation_id=f"{session_id}_session",
            message="Session started",
            role="system",
            metadata=metadata
        )

    def log_session_end(self, session_id: str, session_stats: Optional[Dict[str, Any]] = None) -> bool:
        """
        Log session end event
        
        Args:
            session_id: Unique session identifier
            session_stats: Optional session statistics
            
        Returns:
            bool: True if successful, False otherwise
        """
        metadata = {'event_type': 'session_end'}
        if session_stats:
            metadata.update(session_stats)
            
        return self.log_message(
            session_id=session_id,
            conversation_id=f"{session_id}_session",
            message="Session ended",
            role="system",
            metadata=metadata
        )

    def log_error(self, session_id: str, conversation_id: str, error_message: str, 
                  error_type: str = "application_error") -> bool:
        """
        Log application errors
        
        Args:
            session_id: Unique session identifier
            conversation_id: Unique conversation identifier
            error_message: The error message
            error_type: Type of error
            
        Returns:
            bool: True if successful, False otherwise
        """
        return self.log_message(
            session_id=session_id,
            conversation_id=conversation_id,
            message=f"ERROR: {error_message}",
            role="system",
            metadata={
                'event_type': 'error',
                'error_type': error_type
            }
        )

    def get_session_logs(self, session_id: str) -> Optional[list]:
        """
        Retrieve all logs for a specific session
        
        Args:
            session_id: Session identifier to retrieve
            
        Returns:
            list: List of records or None if error
        """
        try:
            records = self.project.export_records(
                filter_logic=f"[session_id] = '{session_id}'"
            )
            return records
        except Exception as e:
            self.logger.error(f"Error retrieving session logs: {e}")
            return None

    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on REDCap connection
        
        Returns:
            dict: Health check results
        """
        health_status = {
            'status': 'unknown',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'errors': []
        }
        
        try:
            # Test connection
            if self._test_connection():
                health_status['status'] = 'healthy'
            else:
                health_status['status'] = 'unhealthy'
                health_status['errors'].append('Connection test failed')
                
        except Exception as e:
            health_status['status'] = 'error'
            health_status['errors'].append(str(e))
            
        return health_status