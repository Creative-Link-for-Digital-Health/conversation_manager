import toml
import threading
import queue
import time
from datetime import datetime
from typing import Dict, Any, Optional
import uuid
import requests.exceptions

# Define a timeout for REDCap API calls
REDCAP_TIMEOUT = 5  # seconds

class RedCAPLogger:
    def __init__(self, config_path: str):
        """
        Initialize REDCap logger from TOML config file with background processing
        
        Args:
            config_path: Path to TOML configuration file
        """
        self.initialized = False
        self.enabled = True
        self.error = None
        
        try:
            with open(config_path, 'r') as f:
                secrets = toml.load(f)
            
            if 'REDCAP' not in secrets:
                self.error = "No REDCAP section in secrets file"
                self.enabled = False
                print(f"REDCap logging disabled: {self.error}")
                return
                
            # Import REDCap here to avoid issues if it's not installed
            try:
                from redcap import Project
                self.Project = Project
            except ImportError as e:
                self.error = f"PyCap not installed: {str(e)}"
                self.enabled = False
                print(f"REDCap logging disabled: {self.error}")
                return
            
            # Save credentials but don't connect immediately
            self.api_url = secrets['REDCAP']['API_URL']
            self.api_token = secrets['REDCAP']['API_TOKEN']
            
            # Initialize project to None - will connect on first use
            self.project = None
            
            # Initialize message queue and worker thread
            self.message_queue = queue.Queue()
            self.worker_thread = threading.Thread(target=self._process_queue)
            self.worker_thread.daemon = True  # Allow thread to be terminated when program exits
            self.worker_thread.start()
            
            self.initialized = True
            print("REDCap logger initialized successfully")
            
        except Exception as e:
            self.error = str(e)
            self.enabled = False
            print(f"Error initializing REDCap logger: {self.error}")
    
    def _connect(self) -> bool:
        """Establish connection to REDCap project"""
        if self.project is not None:
            return True
            
        if not self.enabled:
            return False
            
        try:
            self.project = self.Project(self.api_url, self.api_token, timeout=REDCAP_TIMEOUT)
            return True
        except Exception as e:
            self.error = f"Connection error: {str(e)}"
            print(f"REDCap connection error: {self.error}")
            return False
    
    def log_message(self, session_id: str, conversation_id: str, message: str, role: str) -> bool:
        """
        Queue a message to be logged to REDCap asynchronously
        
        Args:
            session_id: Session ID
            conversation_id: Conversation ID
            message: Message text
            role: Role (user or assistant)
            
        Returns:
            bool: True if message was queued successfully
        """
        if not self.enabled:
            return False
            
        try:
            record_data = {
                'record_id': str(uuid.uuid4()),
                'session_id': session_id,
                'conversation_id': conversation_id,
                'message': message,
                'role': role,
                'timestamp': datetime.now().isoformat()
            }
            
            # Add to queue and return immediately
            self.message_queue.put(record_data)
            return True
        except Exception as e:
            print(f"Error queueing REDCap message: {str(e)}")
            return False
    
    def _process_queue(self):
        """Background thread to process queued messages"""
        while True:
            try:
                # Get a batch of messages (up to 10) or wait for new ones
                batch = []
                try:
                    # Get first message or wait
                    batch.append(self.message_queue.get(block=True, timeout=1))
                    
                    # Get any additional messages without waiting
                    for _ in range(9):  # Up to 9 more (10 total)
                        if not self.message_queue.empty():
                            batch.append(self.message_queue.get(block=False))
                        else:
                            break
                except queue.Empty:
                    # No messages in queue, just continue the loop
                    continue
                
                # Process the batch
                if batch and self._connect():
                    try:
                        response = self.project.import_records(batch, timeout=REDCAP_TIMEOUT)
                        success_count = response.get('count', 0)
                        if success_count != len(batch):
                            print(f"Warning: REDCap logged {success_count}/{len(batch)} messages")
                    except requests.exceptions.Timeout:
                        print("REDCap API timeout - will retry messages later")
                        # Put messages back in queue
                        for record in batch:
                            self.message_queue.put(record)
                    except Exception as e:
                        print(f"Error sending batch to REDCap: {str(e)}")
                
                # Mark tasks as done
                for _ in batch:
                    self.message_queue.task_done()
                    
                # Small delay to prevent CPU spinning
                time.sleep(0.1)
                
            except Exception as e:
                print(f"Error in REDCap worker thread: {str(e)}")
                time.sleep(5)  # Sleep longer on error