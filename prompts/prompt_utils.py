"""
Prompt utils - Database interface for prompt management
"""

import os
import toml
import duckdb
import uuid
from typing import Optional, List, Dict
from functools import lru_cache

class PromptLibrary:
    _cache = {}  # Simple in-memory cache
    
    def __init__(self, prompt_id: str, db_path: str):
        """
        Create an interface to db file for prompt storage and tracking
        
        Args:
            prompt_id: UUID of the prompt to retrieve
            db_path: Path to prompts database
        """
        # Validate UUID format
        try:
            uuid.UUID(prompt_id)
        except ValueError:
            raise ValueError(f"Invalid UUID format: {prompt_id}")
        
        self.prompt_uuid = prompt_id
        self.db_path = db_path
        
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database file not found: {db_path}")
    
    def checkout(self) -> Optional[str]:
        """
        Get the prompt content from database
        
        Returns:
            str: The prompt content if found, None if not found
        """
        # Check cache first
        if self.prompt_uuid in self._cache:
            return self._cache[self.prompt_uuid]
        
        try:
            with duckdb.connect(self.db_path) as conn:
                result = conn.execute("""
                    SELECT content FROM prompts 
                    WHERE uuid = ?
                """, [self.prompt_uuid]).fetchone()
                
                if result and result[0]:
                    # Cache the result
                    self._cache[self.prompt_uuid] = result[0]
                    return result[0]
                else:
                    print(f"Warning: No prompt found with UUID {self.prompt_uuid}")
                    return None
                    
        except Exception as e:
            print(f"Database error: {e}")
            return None
    
    @staticmethod
    def list_all_prompts(db_path: str) -> List[Dict]:
        """
        Get all prompts from the database
        
        Args:
            db_path: Path to prompts database
            
        Returns:
            List of dictionaries containing prompt metadata
        """
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database file not found: {db_path}")
        
        try:
            with duckdb.connect(db_path) as conn:
                results = conn.execute("""
                    SELECT uuid, title, description, created_at, updated_at
                    FROM prompts 
                    ORDER BY updated_at DESC
                """).fetchall()
                
                prompts = []
                for row in results:
                    prompts.append({
                        'uuid': row[0],
                        'title': row[1] if row[1] else 'Untitled',
                        'description': row[2] if row[2] else '',
                        'created_at': row[3],
                        'updated_at': row[4]
                    })
                
                return prompts
                
        except Exception as e:
            print(f"Database error: {e}")
            return []
    
    @staticmethod
    def get_prompt_by_uuid(db_path: str, prompt_uuid: str) -> Optional[Dict]:
        """
        Get a specific prompt by UUID with all metadata
        
        Args:
            db_path: Path to prompts database
            prompt_uuid: UUID of the prompt
            
        Returns:
            Dictionary with prompt data or None if not found
        """
        # Validate UUID format
        try:
            uuid.UUID(prompt_uuid)
        except ValueError:
            raise ValueError(f"Invalid UUID format: {prompt_uuid}")
        
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database file not found: {db_path}")
        
        try:
            with duckdb.connect(db_path) as conn:
                result = conn.execute("""
                    SELECT uuid, title, description, content, created_at, updated_at
                    FROM prompts 
                    WHERE uuid = ?
                """, [prompt_uuid]).fetchone()
                
                if result:
                    return {
                        'uuid': result[0],
                        'title': result[1] if result[1] else 'Untitled',
                        'description': result[2] if result[2] else '',
                        'content': result[3],
                        'created_at': result[4],
                        'updated_at': result[5]
                    }
                else:
                    return None
                    
        except Exception as e:
            print(f"Database error: {e}")
            return None
    
    @staticmethod
    def set_prompt(db_path: str, prompt_uuid: str, title: str, description: str, content: str) -> bool:
        """
        Create or update a prompt in the database
        
        Args:
            db_path: Path to prompts database
            prompt_uuid: UUID of the prompt
            title: Prompt title
            description: Prompt description
            content: Prompt content
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Validate UUID format
        try:
            uuid.UUID(prompt_uuid)
        except ValueError:
            raise ValueError(f"Invalid UUID format: {prompt_uuid}")
        
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database file not found: {db_path}")
        
        try:
            with duckdb.connect(db_path) as conn:
                # Check if prompt exists
                existing = conn.execute("""
                    SELECT uuid FROM prompts WHERE uuid = ?
                """, [prompt_uuid]).fetchone()
                
                if existing:
                    # Update existing prompt
                    conn.execute("""
                        UPDATE prompts 
                        SET title = ?, description = ?, content = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE uuid = ?
                    """, [title, description, content, prompt_uuid])
                else:
                    # Insert new prompt
                    conn.execute("""
                        INSERT INTO prompts (uuid, title, description, content, created_at, updated_at)
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """, [prompt_uuid, title, description, content])
                
                # Clear cache for this prompt
                if prompt_uuid in PromptLibrary._cache:
                    del PromptLibrary._cache[prompt_uuid]
                
                return True
                
        except Exception as e:
            print(f"Database error: {e}")
            return False
    
    @staticmethod
    def delete_prompt(db_path: str, prompt_uuid: str) -> bool:
        """
        Delete a prompt from the database
        
        Args:
            db_path: Path to prompts database
            prompt_uuid: UUID of the prompt to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Validate UUID format
        try:
            uuid.UUID(prompt_uuid)
        except ValueError:
            raise ValueError(f"Invalid UUID format: {prompt_uuid}")
        
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database file not found: {db_path}")
        
        try:
            with duckdb.connect(db_path) as conn:
                # Check if prompt exists
                existing = conn.execute("""
                    SELECT uuid FROM prompts WHERE uuid = ?
                """, [prompt_uuid]).fetchone()
                
                if not existing:
                    return False  # Prompt doesn't exist
                
                # Delete the prompt
                conn.execute("""
                    DELETE FROM prompts WHERE uuid = ?
                """, [prompt_uuid])
                
                # Clear cache for this prompt
                if prompt_uuid in PromptLibrary._cache:
                    del PromptLibrary._cache[prompt_uuid]
                
                return True
                
        except Exception as e:
            print(f"Database error: {e}")
            return False

    @staticmethod
    def clear_cache():
        """Clear the prompt cache"""
        PromptLibrary._cache.clear()