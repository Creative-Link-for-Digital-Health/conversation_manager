import streamlit as st
import duckdb
import uuid
import pandas as pd
from pathlib import Path
import time

# Database setup
DB_PATH = "prompts.db"

def init_database():
    """Initialize the prompts database"""
    conn = duckdb.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prompts (
            uuid VARCHAR PRIMARY KEY,
            title VARCHAR NOT NULL,
            content TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            version INTEGER DEFAULT 1,
            forked_from VARCHAR
        )
    """)
    conn.close()

# Prompt management functions
def generate_uuid():
    """Generate a new UUID for a prompt"""
    return str(uuid.uuid4())

def save_prompt(prompt_data):
    """Save a prompt to the database"""
    conn = duckdb.connect(DB_PATH)
    try:
        # Set default version if not provided
        version = prompt_data.get('version', 1)
        
        # Check if forked_from is in the data
        forked_from = prompt_data.get('forked_from', None)
        
        # Check if forked_from column exists
        metadata_result = conn.execute("PRAGMA table_info(prompts)").fetchall()
        column_names = [col[1] for col in metadata_result]
        
        if 'forked_from' in column_names:
            # With forked_from field
            conn.execute("""
                INSERT INTO prompts (uuid, title, content, description, version, forked_from)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                prompt_data['uuid'],
                prompt_data['title'],
                prompt_data['content'],
                prompt_data['description'],
                version,
                forked_from
            ))
        else:
            # Without forked_from field
            conn.execute("""
                INSERT INTO prompts (uuid, title, content, description, version)
                VALUES (?, ?, ?, ?, ?)
            """, (
                prompt_data['uuid'],
                prompt_data['title'],
                prompt_data['content'],
                prompt_data['description'],
                version
            ))
        
        conn.close()
        return True
    except Exception as e:
        conn.close()
        st.error(f"Error saving prompt: {e}")
        return False

def update_prompt(prompt_data):
    """Update an existing prompt"""
    conn = duckdb.connect(DB_PATH)
    try:
        conn.execute("""
            UPDATE prompts 
            SET title = ?, content = ?, description = ?, updated_at = CURRENT_TIMESTAMP,
                version = version + 1
            WHERE uuid = ?
        """, (
            prompt_data['title'],
            prompt_data['content'],
            prompt_data['description'],
            prompt_data['uuid']
        ))
        conn.close()
        return True
    except Exception as e:
        conn.close()
        st.error(f"Error updating prompt: {e}")
        return False

def delete_prompt(uuid):
    """
    Delete a prompt from the database by its UUID.    
    """
    try:
        conn = duckdb.connect(DB_PATH)
        
        # Check if the prompt exists
        result = conn.execute(
            "SELECT COUNT(*) FROM prompts WHERE uuid = ?", 
            [uuid]
        ).fetchone()
        
        if result[0] == 0:
            print(f"No prompt found with UUID: {uuid}")
            conn.close()
            return False
        
        # Delete the prompt
        conn.execute(
            "DELETE FROM prompts WHERE uuid = ?", 
            [uuid]
        )
        
        conn.close()
        print(f"Successfully deleted prompt with UUID: {uuid}")
        return True
    
    except Exception as e:
        print(f"Error deleting prompt: {e}")
        return False

def get_prompt_by_uuid(prompt_uuid):
    """Get a specific prompt by UUID"""
    conn = duckdb.connect(DB_PATH)
    try:
        result = conn.execute("""
            SELECT * FROM prompts WHERE uuid = ?""", (prompt_uuid,)).fetchone()
        conn.close()
        return result
    except Exception as e:
        conn.close()
        st.error(f"Error fetching prompt: {e}")
        return None

def get_all_prompts():
    """Get all active prompts"""
    conn = duckdb.connect(DB_PATH)
    try:
        # Check if forked_from column exists
        metadata_result = conn.execute("PRAGMA table_info(prompts)").fetchall()
        column_names = [col[1] for col in metadata_result]
        
        if 'forked_from' in column_names:
            # Include forked_from in the results
            result = conn.execute("""
                SELECT uuid, title, description, created_at, updated_at, version, forked_from
                FROM prompts 
                ORDER BY updated_at DESC
            """).fetchdf()
        else:
            # Without forked_from
            result = conn.execute("""
                SELECT uuid, title, description, created_at, updated_at, version
                FROM prompts 
                ORDER BY updated_at DESC
            """).fetchdf()
            
        conn.close()
        return result
    except Exception as e:
        conn.close()
        st.error(f"Error fetching prompts: {e}")
        return pd.DataFrame()

def search_prompts(search_term):
    """Search prompts by title or description"""
    conn = duckdb.connect(DB_PATH)
    try:
        # Check if forked_from column exists
        metadata_result = conn.execute("PRAGMA table_info(prompts)").fetchall()
        column_names = [col[1] for col in metadata_result]
        
        if 'forked_from' in column_names:
            # Include forked_from in the results
            result = conn.execute("""
                SELECT uuid, title, description, created_at, updated_at, version, forked_from
                FROM prompts 
                WHERE (title ILIKE ? OR description ILIKE ?)
                ORDER BY updated_at DESC
            """, (f'%{search_term}%', f'%{search_term}%')).fetchdf()
        else:
            # Without forked_from
            result = conn.execute("""
                SELECT uuid, title, description, created_at, updated_at, version
                FROM prompts 
                WHERE (title ILIKE ? OR description ILIKE ?)
                ORDER BY updated_at DESC
            """, (f'%{search_term}%', f'%{search_term}%')).fetchdf()
            
        conn.close()
        return result
    except Exception as e:
        conn.close()
        st.error(f"Error searching prompts: {e}")
        return pd.DataFrame()

def export_prompt(prompt_uuid, format_type="json"):
    """Export a prompt in different formats"""
    prompt_data = get_prompt_by_uuid(prompt_uuid)
    if not prompt_data:
        return None
    
    if format_type == "json":
        import json
        export_data = {
            "uuid": prompt_data[0],
            "title": prompt_data[1],
            "content": prompt_data[2],
            "description": prompt_data[3],
            "version": prompt_data[6]
        }
        return json.dumps(export_data, indent=2)
    elif format_type == "toml":
        return f"""[system_prompt]
prompt_uuid = "{prompt_data[0]}"
title = "{prompt_data[1]}"
content = \"\"\"
{prompt_data[2]}
\"\"\"
"""
    elif format_type == "markdown":
        return f"""# {prompt_data[1]}

**UUID:** `{prompt_data[0]}`
**Description:** {prompt_data[3] or 'No description'}
**Version:** {prompt_data[6]}

## Prompt Content

```
{prompt_data[2]}
```
"""

# Streamlit App
def main():
    st.set_page_config(
        page_title="Prompt Manager",
        page_icon="📝",
        layout="wide"
    )
    
    init_database()
    
    # Get stats for dashboard
    prompts_df = get_all_prompts()
    total_prompts = len(prompts_df)
    
    # Sidebar navigation using radio buttons
    st.sidebar.title("Prompt Manager")

    # Define pages with their icons and functions
    pages = {
        "📋 Browse & Search Prompts": browse_prompts_page,
        "➕ Create New Prompt": create_prompt_page,
        "✏️ Update Prompt": update_prompt_page
    }

    # Create radio button navigation
    selected_page = st.sidebar.radio("", list(pages.keys()))

    # Call the function for the selected page
    pages[selected_page]()

def browse_prompts_page():
    st.header("📋 Browse & Search Prompts")
    
    # Search functionality
    col1, col2 = st.columns([3, 1])
    with col1:
        search_term = st.text_input(
            "🔍 Search prompts", 
            placeholder="Enter keywords to search in title or description"
        )
    with col2:
        search_button = st.button("Search", type="primary")
    
    # Get prompts data based on search
    prompts_df = None
    if search_term and (search_button or st.session_state.get("last_search") == search_term):
        # Save last search term in session state
        st.session_state["last_search"] = search_term
        prompts_df = search_prompts(search_term)
        if not prompts_df.empty:
            st.success(f"Found {len(prompts_df)} prompt(s) matching '{search_term}'")
        else:
            st.info(f"No prompts found matching '{search_term}'")
            # Fallback to showing all prompts
            prompts_df = get_all_prompts()
    else:
        # Clear last search if search field is empty
        if not search_term:
            if "last_search" in st.session_state:
                del st.session_state["last_search"]
        prompts_df = get_all_prompts()
    
    if prompts_df.empty:
        st.info("No prompts found. Create your first prompt!")
        return
    
    st.write(f"Showing {len(prompts_df)} prompts")
    
    # Check if forked_from column exists in the dataframe
    if 'forked_from' in prompts_df.columns:
        # Display table with forked_from info
        st.dataframe(
            prompts_df[['title', 'description', 'uuid', 'version', 'forked_from']],
            hide_index=True,
            height=200,
            column_config={
                "title": st.column_config.TextColumn("Title"),
                "description": st.column_config.TextColumn("Description"),
                "uuid": st.column_config.TextColumn("UUID"),
                "version": st.column_config.NumberColumn("Version"),
                "forked_from": st.column_config.TextColumn("Forked From")
            }
        )
    else:
        # Display table without forked_from
        st.dataframe(
            prompts_df[['title', 'description', 'uuid', 'version']],
            hide_index=True,
            height=200,
            column_config={
                "title": st.column_config.TextColumn("Title"),
                "description": st.column_config.TextColumn("Description"),
                "uuid": st.column_config.TextColumn("UUID"),
                "version": st.column_config.NumberColumn("Version")
            }
        )

    st.divider()

    st.subheader("Bulk Export")
    
    bulk_format = st.selectbox("Bulk export format:", ["JSON", "CSV"])
    
    if st.button("📦 Export All"):
        filtered_df = prompts_df.copy()
        
        if bulk_format == "JSON":
            import json
            export_data = []
            for _, prompt in filtered_df.iterrows():
                prompt_data = get_prompt_by_uuid(prompt['uuid'])
                if prompt_data:
                    export_item = {
                        "uuid": prompt_data[0],
                        "title": prompt_data[1],
                        "content": prompt_data[2],
                        "description": prompt_data[3],
                        "version": prompt_data[6],
                        "created_at": str(prompt['created_at']),
                        "updated_at": str(prompt['updated_at'])
                    }
                    
                    # Add forked_from if available
                    if 'forked_from' in prompt and not pd.isna(prompt['forked_from']):
                        export_item["forked_from"] = prompt['forked_from']
                    
                    export_data.append(export_item)
            
            json_content = json.dumps(export_data, indent=2)
            st.download_button(
                label="⬇️ Download JSON",
                data=json_content,
                file_name="prompts_export.json",
                mime="application/json"
            )
            
        elif bulk_format == "CSV":
            csv_content = filtered_df.to_csv(index=False)
            st.download_button(
                label="⬇️ Download CSV",
                data=csv_content,
                file_name="prompts_export.csv",
                mime="text/csv"
            )
        
        st.success(f"Exported {len(filtered_df)} prompts!")

def create_prompt_page():
    st.subheader("➕ Create New Prompt")
    
    # Template selection
    with st.expander("📋 Use Template (Optional)"):
        template_type = st.selectbox("Choose a template", [
            "None",
            "Assistant",
            "Code Helper", 
            "Creative Writer",
            "Analyst",
            "Teacher"
        ])
        
        templates = {
            "Assistant": {
                "title": "Helpful Assistant",
                "description": "A general-purpose helpful assistant",
                "content": "You are a helpful, harmless, and honest AI assistant. You provide clear, accurate, and useful responses to user questions. Always be polite and professional."
            },
            "Code Helper": {
                "title": "Programming Assistant",
                "description": "Specialized in helping with coding tasks",
                "content": "You are an expert programming assistant. Help users write, debug, and improve their code. Provide clear explanations and follow best practices. Always include comments in code examples."
            },
            "Creative Writer": {
                "title": "Creative Writing Assistant",
                "description": "Helps with creative writing tasks",
                "content": "You are a creative writing assistant. Help users develop stories, characters, dialogue, and creative content. Be imaginative and inspiring while maintaining good writing structure."
            },
            "Analyst": {
                "title": "Data Analyst",
                "description": "Specialized in data analysis and insights",
                "content": "You are a data analyst expert. Help users analyze data, create visualizations, and derive insights. Be methodical, precise, and explain your reasoning clearly."
            },
            "Teacher": {
                "title": "Educational Assistant",
                "description": "Helps with teaching and learning",
                "content": "You are an educational assistant. Help students learn by providing clear explanations, examples, and step-by-step guidance. Adapt your teaching style to the student's level."
            }
        }
    
    with st.form("create_prompt_form"):
        # Pre-fill from template if selected
        template_data = templates.get(template_type, {})
        
        title = st.text_input(
            "Prompt Title*", 
            value=template_data.get("title", ""),
            placeholder="e.g., Helpful Assistant"
        )
        description = st.text_area(
            "Description", 
            value=template_data.get("description", ""),
            placeholder="Describe the purpose and context of this prompt"
        )
        
        content = st.text_area(
            "Prompt Content*", 
            value=template_data.get("content", ""),
            height=400,
            placeholder="Enter your system prompt here...",
            help="This is the actual prompt that will be sent to the LLM"
        )
        
        # Character count
        char_count = len(content)
        st.caption(f"Character count: {char_count:,}")
        
        submitted = st.form_submit_button("💾 Save Prompt", type="primary")
        
        if submitted:
            if not title or not content:
                st.error("Title and Content are required!")
            else:
                new_uuid = generate_uuid()
                prompt_data = {
                    'uuid': new_uuid,
                    'title': title,
                    'content': content,
                    'description': description,
                    'version': 1  # Start at version 1
                }
                
                if save_prompt(prompt_data):
                    st.success(f"✅ Prompt saved successfully!")
                    st.code(new_uuid, language="text")
                    st.caption("Click the copy button in the top-right of the code block to copy the UUID")

def update_prompt_page():
    st.header("✏️ Update Prompt")
    
    # Initialize session state variables if they don't exist
    if "selected_uuid" not in st.session_state:
        st.session_state.selected_uuid = ""
    if "prompt_loaded" not in st.session_state:
        st.session_state.prompt_loaded = False
    if "create_new_uuid" not in st.session_state:
        st.session_state.create_new_uuid = False
    
    # Debug section (collapsible)
    with st.expander("Debug Log", expanded=False):
        if "debug_messages" not in st.session_state:
            st.session_state.debug_messages = []
        
        # Clear log button
        if st.button("Clear Debug Log"):
            st.session_state.debug_messages = []
        
        # Display debug messages
        for i, msg in enumerate(st.session_state.debug_messages):
            st.text(f"{i+1}. {msg}")
    
    # Function to add debug messages
    def add_debug(message):
        st.session_state.debug_messages.append(f"[{time.strftime('%H:%M:%S')}] {message}")
    
    # Function to handle UUID submission
    def on_uuid_submit():
        uuid_input = st.session_state.uuid_input
        if uuid_input:
            add_debug(f"UUID submitted: {uuid_input}")
            
            # Check if it's a partial UUID
            if len(uuid_input) < 36:  # Standard UUID is 36 chars
                prompts_df = get_all_prompts()
                for _, row in prompts_df.iterrows():
                    if uuid_input.lower() in row['uuid'].lower():
                        st.session_state.selected_uuid = row['uuid']  # Set to full UUID
                        add_debug(f"Partial UUID matched to: {row['uuid']}")
                        break
                else:
                    st.session_state.selected_uuid = uuid_input
            else:
                st.session_state.selected_uuid = uuid_input
                
            st.session_state.prompt_loaded = True
            st.session_state.create_new_uuid = False  # Reset fork checkbox when loading a new prompt
    
    # Function to toggle create_new_uuid
    def toggle_create_new_uuid():
        st.session_state.create_new_uuid = not st.session_state.create_new_uuid
        add_debug(f"Create new UUID toggled to: {st.session_state.create_new_uuid}")
    
    # Function to handle prompt update
    def on_update_submit():
        add_debug("Update button clicked!")
        
        # Get values from session state
        title = st.session_state.title_input
        content = st.session_state.content_input
        description = st.session_state.description_input
        create_new_uuid = st.session_state.create_new_uuid
        
        if not title or not content:
            add_debug("Error: Title and Content are required!")
            st.error("Title and Content are required!")
            return
        
        # Create updated data
        updated_data = {
            'title': title,
            'content': content,
            'description': description
        }
        
        # Handle UUID and versioning
        if create_new_uuid:
            # Generate a new UUID for a new prompt version
            new_uuid = generate_uuid()
            updated_data['uuid'] = new_uuid
            updated_data['version'] = 1  # Start at version 1 for new prompts
            updated_data['forked_from'] = st.session_state.selected_uuid
            
            add_debug(f"Creating new prompt with UUID: {new_uuid}, forked from: {st.session_state.selected_uuid}")
            
            # Save as a new prompt
            result = save_prompt(updated_data)
            action_type = "created new version"
        else:
            # Update existing prompt
            updated_data['uuid'] = st.session_state.selected_uuid
            result = update_prompt(updated_data)
            action_type = "updated"
        
        add_debug(f"Action result: {result}")
        
        if result:
            # Success handling
            if create_new_uuid:
                success_msg = f"✅ New prompt version created successfully!"
                add_debug(f"New prompt version created with UUID: {updated_data['uuid']}")
                
                # Update session state to reference the new UUID
                st.session_state.selected_uuid = updated_data['uuid']
                st.session_state.create_new_uuid = False  # Reset the checkbox
            else:
                success_msg = f"✅ Prompt updated successfully!"
                add_debug(f"Prompt updated: {st.session_state.selected_uuid}")
                
                # Increment version in session state (for display)
                if 'current_version' in st.session_state:
                    st.session_state.current_version += 1
            
            st.success(success_msg)
            time.sleep(0.8)  # Brief pause to show the success message
            st.rerun()  # Refresh the page to show updated data
        else:
            error_msg = f"Failed to {action_type} prompt"
            add_debug(error_msg)
            st.error(error_msg)
    
    # UUID input section
    with st.form(key="uuid_form"):
        st.text_input(
            "Enter prompt UUID to edit:",
            key="uuid_input",
            value=st.session_state.selected_uuid,
            help="Enter the full UUID or a partial UUID to load a specific prompt"
        )
        st.form_submit_button("Load Prompt", on_click=on_uuid_submit)
    
    # Get available prompts for reference
    prompts_df = get_all_prompts()
    if prompts_df.empty:
        st.info("No prompts available to edit.")
        return
    
    # Display available UUIDs
    with st.expander("Available Prompt UUIDs (Click to expand)"):
        # Show forked_from if available
        if 'forked_from' in prompts_df.columns:
            st.dataframe(
                prompts_df[['uuid', 'title', 'version', 'forked_from']],
                hide_index=True
            )
        else:
            st.dataframe(
                prompts_df[['uuid', 'title', 'version']],
                hide_index=True
            )
    
    # Only show the edit form if a UUID has been loaded
    if st.session_state.prompt_loaded and st.session_state.selected_uuid:
        # Try to find the prompt
        prompt_data = get_prompt_by_uuid(st.session_state.selected_uuid)
        
        if prompt_data:
            add_debug(f"Prompt found: {prompt_data[1]}")
            
            # Store version in session state
            st.session_state.current_version = 0 if prompt_data[6] is None else prompt_data[6]
            
            # Show current version info
            st.info(f"Editing: **{prompt_data[1]}** - UUID: `{prompt_data[0]}`")
            
            # Display forked info if available (column index 7 should be forked_from)
            if len(prompt_data) > 7 and prompt_data[7]:
                forked_parent = prompt_data[7]
                st.caption(f"This prompt was forked from: `{forked_parent}`")
            
            # Fork checkbox (outside the form for immediate effect)
            st.checkbox(
                "Create new UUID (fork this prompt)",
                value=st.session_state.create_new_uuid,
                key="fork_checkbox",
                on_change=toggle_create_new_uuid,
                help="Check this to create a new prompt version with a new UUID instead of updating the existing one"
            )
            
            # Show version info based on checkbox state
            if st.session_state.create_new_uuid:
                st.caption(f"Current version: {st.session_state.current_version} → Will create new prompt with version 1")
            else:
                st.caption(f"Current version: {st.session_state.current_version} → Will update to version: {st.session_state.current_version + 1}")
            
            # Edit form
            with st.form(key="update_form"):
                st.text_input(
                    "Prompt Title*", 
                    key="title_input",
                    value=prompt_data[1]
                )
                
                st.text_area(
                    "Prompt Content*", 
                    key="content_input",
                    value=prompt_data[2],
                    height=300
                )
                
                st.text_area(
                    "Description", 
                    key="description_input",
                    value=prompt_data[3] or ""
                )
                
                # Character count
                char_count = len(st.session_state.content_input)
                st.caption(f"Character count: {char_count:,}")
                
                # Update button with dynamic label based on session state
                button_label = "Create New Version" if st.session_state.create_new_uuid else "Update Prompt"
                st.form_submit_button(button_label, on_click=on_update_submit)
        else:
            st.error(f"No prompt found with UUID: {st.session_state.selected_uuid}")
            add_debug("No matching prompt found")

if __name__ == "__main__":
    main()