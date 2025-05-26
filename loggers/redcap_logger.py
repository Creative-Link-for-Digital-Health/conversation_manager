import toml
from datetime import datetime
from redcap import Project
import uuid


class RedCAPLogger:
    def __init__(self, config_path: str):
        """
        Initialize REDCap logger from TOML config file
        
        Args:
            config_path: Path to TOML configuration file
        """
        with open(config_path, 'r') as f:
            secrets = toml.load(f)
        
        # Initialize REDCap connection
        self.project = Project(secrets['REDCAP']['API_URL'], secrets['REDCAP']['API_TOKEN'])

    def log_message(self, session_id: str, conversation_id: str, message: str, role: str):
        """
        Log a message to REDCap

        """
        record_data = {
            'record_id': str(uuid.uuid4()),
            'session_id': session_id,
            'conversation_id': conversation_id,
            'message': message,
            'role': role,
            'timestamp': datetime.now().isoformat()
        }  

        # print(record_data)

        try:
            response = self.project.import_records([record_data])
            # print(response)
            # REDCap returns {'count': 1} on success
            return response.get('count', 0) > 0
        except Exception:
            return False