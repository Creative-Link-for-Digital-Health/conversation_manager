"""
REDCap Logging Library for Conversation Research Data
Uses PyCap library for robust REDCap integration
"""

import json
import uuid
import datetime
from typing import Dict, Any, List, Optional
import logging
import time

try:
    from redcap import Project
    PYCAP_AVAILABLE = True
except ImportError:
    PYCAP_AVAILABLE = False

class REDCapLogger:
    """
    REDCap integration for logging conversation research data using PyCap
    """
    
    def __init__(self, api_url: str, api_token: str, project_id: str = None):
        """
        Initialize REDCap logger with PyCap
        
        Args:
            api_url: REDCap API endpoint URL
            api_token: REDCap API token for the project
            project_id: Optional project identifier for logging
        """
        if not PYCAP_AVAILABLE:
            raise ImportError("PyCap not available. Install with: pip install pycap")
        
        self.api_url = api_url.rstrip('/')
        self.api_token = api_token
        self.project_id = project_id
        
        # Initialize PyCap project
        try:
            self.project = Project(api_url, api_token)
            self._test_connection()
            logging.info("✅ REDCap connection established with PyCap")
        except Exception as e:
            logging.error(f"❌ REDCap initialization failed: {e}")
            raise
    
    def _test_connection(self) -> bool:
        """Test REDCap connection using PyCap"""
        try:
            # Test connection by getting project info
            project_info = self.project.export_project_info()
            if project_info:
                logging.info(f"✅ Connected to REDCap project: {project_info.get('project_title', 'Unknown')}")
                return True
            else:
                logging.error("❌ REDCap connection test failed")
                return False
        except Exception as e:
            logging.error(f"❌ REDCap connection error: {e}")
            return False
    
    def get_project_metadata(self) -> Optional[List[Dict]]:
        """Get project metadata/field definitions"""
        try:
            metadata = self.project.export_metadata()
            return metadata
        except Exception as e:
            logging.error(f"Error getting project metadata: {e}")
            return None
    
    def log_conversation_start(self, conversation_data: Dict[str, Any]) -> Optional[str]:
        """
        Log the start of a new conversation
        
        Args:
            conversation_data: Dictionary containing conversation metadata
            
        Returns:
            REDCap record ID if successful
        """
        try:
            # Generate record ID
            record_id = conversation_data.get('conversation_id', str(uuid.uuid4()))
            
            # Prepare conversation start record
            record = {
                'record_id': record_id,
                'redcap_event_name': 'conversation_start_arm_1',  # Adjust based on your REDCap setup
                'conversation_id': conversation_data.get('conversation_id'),
                'participant_id': conversation_data.get('participant_id', ''),
                'session_start_time': conversation_data.get('created_at', datetime.datetime.now().isoformat()),
                'scenario_name': conversation_data.get('scenario_config', ''),
                'prompt_uuid': conversation_data.get('prompt_uuid', ''),
                'rag_enabled': 1 if conversation_data.get('rag_enabled', False) else 0,
                'conversation_title': conversation_data.get('title', ''),
                'conversation_start_complete': 1  # Mark this event as complete
            }
            
            # Submit to REDCap using PyCap
            response = self.project.import_records([record])
            
            if response.get('count', 0) > 0:
                logging.info(f"✅ Conversation start logged to REDCap: {record_id}")
                return record_id
            else:
                logging.error("❌ Failed to log conversation start to REDCap")
                return None
                
        except Exception as e:
            logging.error(f"Error logging conversation start: {e}")
            return None
    
    def log_message(self, message_data: Dict[str, Any], conversation_id: str) -> bool:
        """
        Log a single message to REDCap
        
        Args:
            message_data: Message data including content, sender, metadata
            conversation_id: Parent conversation ID
            
        Returns:
            True if successful
        """
        try:
            # Generate unique message record ID
            message_id = message_data.get('id', str(uuid.uuid4()))
            
            # Prepare message record
            record = {
                'record_id': f"{conversation_id}_msg_{message_id}",
                'redcap_event_name': 'messages_arm_1',  # Adjust based on your REDCap setup
                'conversation_id': conversation_id,
                'message_id': message_id,
                'message_timestamp': message_data.get('timestamp', datetime.datetime.now().isoformat()),
                'sender': message_data.get('sender', ''),
                'message_content': message_data.get('message', ''),
                'message_length': len(message_data.get('message', '')),
                'response_time': message_data.get('response_time', 0) or 0,
                'provider_used': message_data.get('provider', ''),
                'message_complete': 1  # Mark this event as complete
            }
            
            # Add RAG-specific data if available
            rag_data = message_data.get('rag_data')
            if rag_data:
                record.update({
                    'rag_query': rag_data.get('query', ''),
                    'rag_results_count': rag_data.get('results_count', 0),
                    'rag_context_length': rag_data.get('context_length', 0),
                    'rag_sources': json.dumps(rag_data.get('retrieved_sources', [])) if rag_data.get('retrieved_sources') else '',
                    'rag_search_timestamp': rag_data.get('search_timestamp', '')
                })
            
            # Submit to REDCap using PyCap
            response = self.project.import_records([record])
            
            if response.get('count', 0) > 0:
                logging.debug(f"✅ Message logged to REDCap: {message_id}")
                return True
            else:
                logging.error(f"❌ Failed to log message to REDCap: {message_id}")
                return False
                
        except Exception as e:
            logging.error(f"Error logging message: {e}")
            return False
    
    def log_conversation_batch(self, conversation_id: str, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Log multiple messages in a batch operation
        
        Args:
            conversation_id: Conversation identifier
            messages: List of message dictionaries
            
        Returns:
            Summary of batch operation
        """
        try:
            records = []
            
            for message in messages:
                message_id = message.get('id', str(uuid.uuid4()))
                
                record = {
                    'record_id': f"{conversation_id}_msg_{message_id}",
                    'redcap_event_name': 'messages_arm_1',
                    'conversation_id': conversation_id,
                    'message_id': message_id,
                    'message_timestamp': message.get('timestamp', ''),
                    'sender': message.get('sender', ''),
                    'message_content': message.get('message', ''),
                    'message_length': len(message.get('message', '')),
                    'response_time': message.get('response_time', 0) or 0,
                    'provider_used': message.get('provider', ''),
                    'message_complete': 1
                }
                
                # Add RAG data if available
                rag_data = message.get('rag_data')
                if rag_data:
                    record.update({
                        'rag_query': rag_data.get('query', ''),
                        'rag_results_count': rag_data.get('results_count', 0),
                        'rag_context_length': rag_data.get('context_length', 0),
                        'rag_sources': json.dumps(rag_data.get('retrieved_sources', [])) if rag_data.get('retrieved_sources') else '',
                        'rag_search_timestamp': rag_data.get('search_timestamp', '')
                    })
                
                records.append(record)
            
            # Submit batch to REDCap using PyCap
            response = self.project.import_records(records)
            
            if response.get('count', 0) > 0:
                logging.info(f"✅ Batch logged {len(messages)} messages to REDCap")
                return {
                    'success': True,
                    'messages_logged': response.get('count', 0),
                    'conversation_id': conversation_id
                }
            else:
                logging.error("❌ Failed to log message batch to REDCap")
                return {
                    'success': False,
                    'error': 'REDCap import failed'
                }
                
        except Exception as e:
            logging.error(f"Error in batch logging: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def log_conversation_end(self, conversation_id: str, end_data: Dict[str, Any]) -> bool:
        """
        Log conversation completion/termination
        
        Args:
            conversation_id: Conversation identifier
            end_data: Final conversation statistics and metadata
            
        Returns:
            True if successful
        """
        try:
            record = {
                'record_id': f"{conversation_id}_end",
                'redcap_event_name': 'conversation_end_arm_1',
                'conversation_id': conversation_id,
                'session_end_time': datetime.datetime.now().isoformat(),
                'total_messages': end_data.get('message_count', 0),
                'session_duration': end_data.get('duration_seconds', 0),
                'total_user_words': end_data.get('user_word_count', 0),
                'total_ai_words': end_data.get('ai_word_count', 0),
                'avg_response_time': end_data.get('avg_response_time', 0),
                'rag_retrievals_total': end_data.get('total_rag_retrievals', 0),
                'completion_status': end_data.get('status', 'completed'),
                'conversation_end_complete': 1  # Mark this event as complete
            }
            
            # Submit to REDCap using PyCap
            response = self.project.import_records([record])
            
            if response.get('count', 0) > 0:
                logging.info(f"✅ Conversation end logged to REDCap: {conversation_id}")
                return True
            else:
                logging.error("❌ Failed to log conversation end to REDCap")
                return False
                
        except Exception as e:
            logging.error(f"Error logging conversation end: {e}")
            return False
    
    def get_conversation_statistics(self, days_back: int = 30) -> Optional[Dict[str, Any]]:
        """
        Get basic conversation statistics from local tracking
        (REDCap export functionality removed as requested)
        
        Args:
            days_back: Number of days to look back for statistics
            
        Returns:
            Dictionary of basic statistics
        """
        try:
            # This now returns basic stats that can be calculated locally
            # rather than querying REDCap directly
            current_time = datetime.datetime.now()
            start_time = current_time - datetime.timedelta(days=days_back)
            
            return {
                'message': f'Statistics for last {days_back} days',
                'period_start': start_time.isoformat(),
                'period_end': current_time.isoformat(),
                'note': 'Detailed statistics available through REDCap interface'
            }
            
        except Exception as e:
            logging.error(f"Error getting conversation statistics: {e}")
            return None
    
    def test_redcap_fields(self, sample_record: Dict[str, Any]) -> bool:
        """
        Test if REDCap project has the required fields by attempting a dry-run import
        
        Args:
            sample_record: Sample record to test field compatibility
            
        Returns:
            True if fields are compatible
        """
        try:
            # Get project metadata to check field existence
            metadata = self.get_project_metadata()
            if not metadata:
                logging.error("Could not retrieve project metadata")
                return False
            
            # Extract field names from metadata
            available_fields = {field['field_name'] for field in metadata}
            
            # Check if sample record fields exist in project
            missing_fields = set(sample_record.keys()) - available_fields
            
            if missing_fields:
                logging.warning(f"Missing REDCap fields: {missing_fields}")
                return False
            else:
                logging.info("✅ All required fields are available in REDCap project")
                return True
                
        except Exception as e:
            logging.error(f"Error testing REDCap fields: {e}")
            return False

class REDCapLoggerManager:
    """
    Manager class for handling REDCap logging with configuration
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize REDCap logger manager
        
        Args:
            config: Configuration dictionary with REDCap settings
        """
        self.config = config
        self.logger = None
        self.enabled = config.get('redcap_enabled', False)
        
        if self.enabled:
            self._initialize_logger()
    
    def _initialize_logger(self):
        """Initialize REDCap logger with configuration"""
        try:
            api_url = self.config.get('redcap_api_url', '')
            api_token = self.config.get('redcap_api_token', '')
            project_id = self.config.get('redcap_project_id', '')
            
            if not api_url or not api_token:
                logging.error("REDCap API URL and token are required")
                self.enabled = False
                return
            
            self.logger = REDCapLogger(api_url, api_token, project_id)
            
            # Test with a sample record to verify field compatibility
            sample_record = {
                'record_id': 'test_record',
                'conversation_id': 'test_conversation',
                'participant_id': 'test_participant',
                'session_start_time': datetime.datetime.now().isoformat(),
                'message_content': 'test message',
                'sender': 'user',
                'rag_enabled': 0
            }
            
            field_test = self.logger.test_redcap_fields(sample_record)
            if not field_test:
                logging.warning("⚠️  REDCap field compatibility issues detected")
            
            logging.info("✅ REDCap logger initialized successfully")
            
        except Exception as e:
            logging.error(f"Failed to initialize REDCap logger: {e}")
            self.enabled = False
    
    def log_conversation_event(self, event_type: str, data: Dict[str, Any]) -> bool:
        """
        Log conversation event to REDCap
        
        Args:
            event_type: Type of event ('start', 'message', 'end')
            data: Event data
            
        Returns:
            True if successful or disabled
        """
        if not self.enabled or not self.logger:
            return True  # Return True if disabled to not block operation
        
        try:
            if event_type == 'start':
                return self.logger.log_conversation_start(data) is not None
            elif event_type == 'message':
                conversation_id = data.get('conversation_id', '')
                return self.logger.log_message(data, conversation_id)
            elif event_type == 'end':
                conversation_id = data.get('conversation_id', '')
                return self.logger.log_conversation_end(conversation_id, data)
            else:
                logging.warning(f"Unknown event type: {event_type}")
                return False
                
        except Exception as e:
            logging.error(f"Error logging {event_type} event: {e}")
            return False
    
    def is_enabled(self) -> bool:
        """Check if REDCap logging is enabled and functional"""
        return self.enabled and self.logger is not None