"""
Prompt Utilities for integrating with the prompt tracker database
"""

import duckdb
import sys
from pathlib import Path
import logging

class PromptManager:
    """
    Manager for accessing prompts stored in the DuckDB database
    """
    
    def __init__(self, db_path="prompts.db"):
        self.db_path = db_path
        self.ensure_database_exists()
    
    def ensure_database_exists(self):
        """Ensure the prompts database exists and is accessible"""
        if not Path(self.db_path).exists():
            print(f"⚠️  Warning: Prompt database not found at {self.db_path}")
            print("   Please run the Prompt Tracker Streamlit app to create prompts.")
            return False
        return True
    
    def get_prompt_by_uuid(self, prompt_uuid):
        """
        Get a prompt by its UUID
        
        Args:
            prompt_uuid: UUID of the prompt to retrieve
            
        Returns:
            dict: Prompt data with keys: uuid, title, content, description, 
                  created_at, created_by, tags, version
            None: If prompt not found
        """
        try:
            conn = duckdb.connect(self.db_path)
            result = conn.execute("""
                SELECT uuid, title, content, description, created_at, updated_at,
                       created_by, tags, version, is_active
                FROM prompts 
                WHERE uuid = ? AND is_active = true
            """, (prompt_uuid,)).fetchone()
            conn.close()
            
            if result:
                return {
                    'uuid': result[0],
                    'title': result[1],
                    'content': result[2],
                    'description': result[3],
                    'created_at': result[4],
                    'updated_at': result[5],
                    'created_by': result[6],
                    'tags': result[7],
                    'version': result[8],
                    'is_active': result[9]
                }
            else:
                print(f"⚠️  Warning: Prompt with UUID {prompt_uuid} not found")
                return None
                
        except Exception as e:
            print(f"❌ Error accessing prompt database: {e}")
            return None
    
    def get_prompt_content(self, prompt_uuid, fallback_content=None):
        """
        Get just the prompt content, with fallback
        
        Args:
            prompt_uuid: UUID of the prompt to retrieve
            fallback_content: Content to use if prompt not found
            
        Returns:
            str: The prompt content
            
        Raises:
            ValueError: If prompt not found and no fallback provided
        """
        prompt_data = self.get_prompt_by_uuid(prompt_uuid)
        
        if prompt_data:
            print(f"✅ Loaded prompt: {prompt_data['title']} (v{prompt_data['version']})")
            return prompt_data['content']
        elif fallback_content:
            print(f"⚠️  Using fallback prompt for UUID: {prompt_uuid}")
            return fallback_content
        else:
            raise ValueError(f"Prompt UUID {prompt_uuid} not found and no fallback provided")
    
    def list_all_prompts(self):
        """
        List all available prompts (for debugging/admin)
        
        Returns:
            list: List of prompt metadata dictionaries
        """
        try:
            conn = duckdb.connect(self.db_path)
            results = conn.execute("""
                SELECT uuid, title, description, created_at, updated_at, 
                       created_by, tags, version
                FROM prompts 
                WHERE is_active = true 
                ORDER BY updated_at DESC
            """).fetchall()
            conn.close()
            
            return [
                {
                    'uuid': row[0],
                    'title': row[1],
                    'description': row[2],
                    'created_at': row[3],
                    'updated_at': row[4],
                    'created_by': row[5],
                    'tags': row[6],
                    'version': row[7]
                }
                for row in results
            ]
        except Exception as e:
            print(f"❌ Error listing prompts: {e}")
            return []
    
    def search_prompts(self, search_term):
        """
        Search prompts by title, description, or tags
        
        Args:
            search_term: Term to search for
            
        Returns:
            list: List of matching prompt metadata dictionaries
        """
        try:
            conn = duckdb.connect(self.db_path)
            results = conn.execute("""
                SELECT uuid, title, description, created_at, updated_at, 
                       created_by, tags, version
                FROM prompts 
                WHERE is_active = true 
                AND (title ILIKE ? OR description ILIKE ? OR tags ILIKE ?)
                ORDER BY updated_at DESC
            """, (f'%{search_term}%', f'%{search_term}%', f'%{search_term}%')).fetchall()
            conn.close()
            
            return [
                {
                    'uuid': row[0],
                    'title': row[1],
                    'description': row[2],
                    'created_at': row[3],
                    'updated_at': row[4],
                    'created_by': row[5],
                    'tags': row[6],
                    'version': row[7]
                }
                for row in results
            ]
        except Exception as e:
            print(f"❌ Error searching prompts: {e}")
            return []
    
    def get_prompts_by_tag(self, tag):
        """
        Get prompts that contain a specific tag
        
        Args:
            tag: Tag to search for
            
        Returns:
            list: List of matching prompt metadata dictionaries
        """
        try:
            conn = duckdb.connect(self.db_path)
            results = conn.execute("""
                SELECT uuid, title, description, created_at, updated_at, 
                       created_by, tags, version
                FROM prompts 
                WHERE is_active = true 
                AND tags ILIKE ?
                ORDER BY updated_at DESC
            """, (f'%{tag}%',)).fetchall()
            conn.close()
            
            return [
                {
                    'uuid': row[0],
                    'title': row[1],
                    'description': row[2],
                    'created_at': row[3],
                    'updated_at': row[4],
                    'created_by': row[5],
                    'tags': row[6],
                    'version': row[7]
                }
                for row in results
            ]
        except Exception as e:
            print(f"❌ Error getting prompts by tag: {e}")
            return []
    
    def get_prompt_stats(self):
        """
        Get statistics about the prompt database
        
        Returns:
            dict: Statistics including total prompts, recent activity, etc.
        """
        try:
            conn = duckdb.connect(self.db_path)
            
            # Total active prompts
            total_prompts = conn.execute("""
                SELECT COUNT(*) FROM prompts WHERE is_active = true
            """).fetchone()[0]
            
            # Recent prompts (last 7 days)
            recent_prompts = conn.execute("""
                SELECT COUNT(*) FROM prompts 
                WHERE is_active = true 
                AND created_at > datetime('now', '-7 days')
            """).fetchone()[0]
            
            # Updated prompts (last 7 days)
            updated_prompts = conn.execute("""
                SELECT COUNT(*) FROM prompts 
                WHERE is_active = true 
                AND updated_at > datetime('now', '-7 days')
                AND updated_at != created_at
            """).fetchone()[0]
            
            # Most recent prompt
            latest_prompt = conn.execute("""
                SELECT title, created_at FROM prompts 
                WHERE is_active = true 
                ORDER BY created_at DESC 
                LIMIT 1
            """).fetchone()
            
            # Unique creators
            creators = conn.execute("""
                SELECT COUNT(DISTINCT created_by) FROM prompts 
                WHERE is_active = true AND created_by IS NOT NULL
            """).fetchone()[0]
            
            conn.close()
            
            return {
                'total_prompts': total_prompts,
                'recent_prompts': recent_prompts,
                'updated_prompts': updated_prompts,
                'latest_prompt': {
                    'title': latest_prompt[0] if latest_prompt else None,
                    'created_at': latest_prompt[1] if latest_prompt else None
                },
                'unique_creators': creators
            }
            
        except Exception as e:
            print(f"❌ Error getting prompt stats: {e}")
            return {
                'total_prompts': 0,
                'recent_prompts': 0,
                'updated_prompts': 0,
                'latest_prompt': {'title': None, 'created_at': None},
                'unique_creators': 0
            }
    
    def validate_prompt_uuid(self, prompt_uuid):
        """
        Validate that a prompt UUID exists and is active
        
        Args:
            prompt_uuid: UUID to validate
            
        Returns:
            bool: True if prompt exists and is active
        """
        try:
            conn = duckdb.connect(self.db_path)
            result = conn.execute("""
                SELECT COUNT(*) FROM prompts 
                WHERE uuid = ? AND is_active = true
            """, (prompt_uuid,)).fetchone()
            conn.close()
            
            return result[0] > 0
            
        except Exception as e:
            print(f"❌ Error validating prompt UUID: {e}")
            return False
    
    def get_prompt_history(self, prompt_uuid):
        """
        Get version history for a prompt (if versioning is implemented)
        
        Args:
            prompt_uuid: UUID of the prompt
            
        Returns:
            list: List of version information
        """
        # For now, return current version only
        # Could be extended to track full version history
        prompt_data = self.get_prompt_by_uuid(prompt_uuid)
        if prompt_data:
            return [{
                'version': prompt_data['version'],
                'updated_at': prompt_data['updated_at'],
                'created_by': prompt_data['created_by']
            }]
        return []

# Convenience function for quick access
def get_system_prompt(prompt_uuid, fallback_content=None, db_path="prompts.db"):
    """
    Quick function to get system prompt content
    
    Args:
        prompt_uuid: UUID of the prompt to retrieve
        fallback_content: Fallback content if prompt not found
        db_path: Path to the DuckDB database file
    
    Returns:
        str: The prompt content
    """
    manager = PromptManager(db_path)
    return manager.get_prompt_content(prompt_uuid, fallback_content)

def validate_prompt_exists(prompt_uuid, db_path="prompts.db"):
    """
    Quick function to validate a prompt exists
    
    Args:
        prompt_uuid: UUID to validate
        db_path: Path to the DuckDB database file
    
    Returns:
        bool: True if prompt exists
    """
    manager = PromptManager(db_path)
    return manager.validate_prompt_uuid(prompt_uuid)

def list_available_prompts(db_path="prompts.db"):
    """
    Quick function to list all available prompts
    
    Args:
        db_path: Path to the DuckDB database file
    
    Returns:
        list: List of prompt metadata
    """
    manager = PromptManager(db_path)
    return manager.list_all_prompts()

# Example usage and testing
if __name__ == "__main__":
    # Test the prompt manager
    manager = PromptManager()
    
    print("📊 Prompt Database Statistics:")
    stats = manager.get_prompt_stats()
    print(f"   Total prompts: {stats['total_prompts']}")
    print(f"   Recent prompts: {stats['recent_prompts']}")
    print(f"   Updated prompts: {stats['updated_prompts']}")
    print(f"   Unique creators: {stats['unique_creators']}")
    
    if stats['latest_prompt']['title']:
        print(f"   Latest prompt: {stats['latest_prompt']['title']}")
    
    print("\n📝 Available Prompts:")
    prompts = manager.list_all_prompts()
    for prompt in prompts[:5]:  # Show first 5
        print(f"   • {prompt['title']} (v{prompt['version']}) - {prompt['uuid']}")
    
    if len(prompts) > 5:
        print(f"   ... and {len(prompts) - 5} more")
    
    if not prompts:
        print("   No prompts found. Run 'streamlit run prompt_tracker.py' to create some!")