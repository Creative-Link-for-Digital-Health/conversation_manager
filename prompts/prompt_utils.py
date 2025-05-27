"""
Prompt utils - Database interface for prompt management
"""

import os
import toml
import duckdb
from typing import Optional

class PromptLibrary:
    def __init__(self, config_path: str, db_path: str):
        """
        Create an interface to db file for prompt storage and tracking
        
        Args:
            config_path: Path to TOML configuration file
            db_path: Path to prompts database
        """
        self.config_path = config_path
        self.db_path = db_path
        
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database file not found: {db_path}")
        
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        # Load config
        with open(config_path, 'r') as f:
            self.scenario = toml.load(f)
        
        self.prompt_uuid = self.scenario['system_prompt']['prompt_id']
    
    def checkout(self) -> Optional[str]:
        """
        Get the prompt content from database
        
        Returns:
            str: The prompt content if found, None if not found
        """
        try:
            conn = duckdb.connect(self.db_path)
            
            # Query for the specific prompt
            result = conn.execute("""
                SELECT content FROM prompts 
                WHERE uuid = ?
            """, [self.prompt_uuid]).fetchone()
            
            conn.close()
            
            if result and result[0]:
                return result[0]
            else:
                print(f"Warning: No prompt found with UUID {self.prompt_uuid}")
                return None
                
        except Exception as e:
            print(f"Database error: {e}")
            return None