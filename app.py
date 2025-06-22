from flask import Flask, render_template, request, jsonify, session, redirect
from flask_cors import CORS
from functools import wraps
import time
import os
import toml
import uuid

print("Starting Flask server...")

# LOAD SECRETS
with open('./.secrets.toml', 'r') as f:
    secrets = toml.load(f)

# IMPORT SCENARIO STATE
with open('./scenario.toml', 'r') as f:
    scenario_settings = toml.load(f)
# Check if scenario settings are loaded correctly
if not scenario_settings:
    raise ValueError("Failed to load scenario settings from scenario.toml")

# Import our custom modules
from session_manager import SessionManager
from llm_manager import LLMManager

# LOCAL LOGGING
if scenario_settings['local_logging']['enabled'] == True:
    print("Local logging is enabled.")
    try:
        # Import loggers
        from loggers.local_logger import LocalLogger
        local_chat_logger = LocalLogger("./loggers/chat_logs.db")
        print("Successfully initialized local logger")
    except Exception as e:
        print(f"Error initializing logger: {e}")
        # Create a dummy logger that does nothing
        class DummyLogger:
            def log_message(self, *args, **kwargs):
                print("DummyLogger: log_message called (no action taken)")
            def log_conversation_turn(self, *args, **kwargs):
                print("DummyLogger: log_conversation_turn called (no action taken)")
            def get_conversation(self, *args, **kwargs):
                return []
            def get_session_conversations(self, *args, **kwargs):
                return []
            def export_to_csv(self, *args, **kwargs):
                pass
            def get_stats(self, *args, **kwargs):
                return {"note": "Dummy logger - no actual data"}
        local_chat_logger = DummyLogger()
        print("Using fallback dummy logger")
else:    
    print("Local logging is disabled. No local logger will be used.")



# REDCAP LOGGING
if scenario_settings['redcap_logging']['enabled'] == True:
    print("REDCap logging is enabled.")
    try:
        # Import logger
        from loggers.redcap_logger import RedCAPLogger
        redcap_logger = RedCAPLogger("./.secrets.toml")
        if not redcap_logger.enabled:
            print("Warning: REDCap logger was initialized but is disabled due to errors")
    except Exception as e:
        print(f"ERROR setting up REDCap logging: {str(e)}")
        print("Continuing without REDCap logging")
        redcap_logger = None
else:
    print("REDCap logging is disabled. No REDCap logger will be used.")
    redcap_logger = None



from prompts.prompt_utils import PromptLibrary
# load default scenario settings prompt
try:
    prompt_library = PromptLibrary(scenario_settings['system_prompt']['prompt_id'], "./prompts/prompts.db")
    default_system_prompt = prompt_library.checkout()
    
    if not default_system_prompt:
        print("Warning: Could not load default system prompt, using fallback")
        default_system_prompt = "You are a helpful AI assistant."
except Exception as e:
    print(f"Error loading default system prompt: {e}")
    default_system_prompt = "You are a helpful AI assistant."

# Initialize managers
session_manager = SessionManager()
llm_manager = LLMManager("./.secrets.toml", "./scenario.toml") #TODO rewrite to pass which LLM directly

app = Flask(__name__)

# Set flask secret key from secrets file
app.secret_key = secrets['INSTANCE_VARS']['flask_secret_key']
# Check if secret key is set
if not app.secret_key:
    raise ValueError("Flask secret key not configured in .secrets.toml")

CORS(app, resources={
    r"/chat": {"origins": "*"},
    r"/health": {"origins": "*"},
    r"/api/*": {"origins": "*"}
})

# API Key decorator for protected routes
def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        expected_api_key = secrets['INSTANCE_VARS']['api_key']
        
        if not expected_api_key:
            return jsonify({'error': 'API key not configured on server'}), 500
        
        if not api_key:
            return jsonify({'error': 'API key required'}), 401
        
        if api_key != expected_api_key:
            return jsonify({'error': 'Invalid API key'}), 403
        
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def home():
    """Render the main chat interface + option to load a new prompt"""
    
    prompt_id = request.args.get('prompt_id')

    if prompt_id:
        try:
            # Load specific prompt if provided
            prompt_library = PromptLibrary(prompt_id, "./prompts/prompts.db")
            loaded_prompt = prompt_library.checkout()
            
            if loaded_prompt:
                session['system_prompt'] = loaded_prompt
                print(f"Loaded custom prompt: {prompt_id}")
            else:
                # Handle case where prompt wasn't found
                print(f"Warning: Prompt {prompt_id} not found, using default")
                session['system_prompt'] = default_system_prompt
        except ValueError as e:
            print(f"Invalid prompt ID format: {e}")
            session['system_prompt'] = default_system_prompt
        except Exception as e:
            print(f"Error loading prompt: {e}")
            session['system_prompt'] = default_system_prompt
    else:
        # Set default system prompt if none exists in session
        if 'system_prompt' not in session:
            session['system_prompt'] = default_system_prompt
            
    return render_template('index.html')

@app.route('/api/prompts', methods=['GET'])
@require_api_key
def list_prompts():
    """List all available prompts"""
    try:
        prompts = PromptLibrary.list_all_prompts("./prompts/prompts.db")
        return jsonify({
            'status': 'success',
            'prompts': prompts,
            'count': len(prompts)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/prompts/<prompt_uuid>', methods=['GET'])
@require_api_key
def get_prompt(prompt_uuid):
    """Get a specific prompt by UUID"""
    try:
        prompt_data = PromptLibrary.get_prompt_by_uuid("./prompts/prompts.db", prompt_uuid)
        
        if prompt_data:
            return jsonify({
                'status': 'success',
                'prompt': prompt_data
            })
        else:
            return jsonify({'error': 'Prompt not found'}), 404
            
    except ValueError as e:
        return jsonify({'error': f'Invalid UUID format: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/prompts/<prompt_uuid>', methods=['PUT', 'POST'])
@require_api_key
def set_prompt(prompt_uuid):
    """Create or update a prompt"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'JSON data required'}), 400
        
        title = data.get('title', '').strip()
        description = data.get('description', '').strip()
        content = data.get('content', '').strip()
        
        if not content:
            return jsonify({'error': 'Content is required'}), 400
        
        if not title:
            title = f"Prompt {prompt_uuid[:8]}"
        
        success = PromptLibrary.set_prompt(
            "./prompts/prompts.db",
            prompt_uuid,
            title,
            description,
            content
        )
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Prompt saved successfully',
                'uuid': prompt_uuid
            })
        else:
            return jsonify({'error': 'Failed to save prompt'}), 500
            
    except ValueError as e:
        return jsonify({'error': f'Invalid UUID format: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/prompts/<prompt_uuid>', methods=['DELETE'])
@require_api_key
def delete_prompt(prompt_uuid):
    """Delete a specific prompt"""
    try:
        success = PromptLibrary.delete_prompt("./prompts/prompts.db", prompt_uuid)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Prompt deleted successfully'
            })
        else:
            return jsonify({'error': 'Failed to delete prompt'}), 500
            
    except ValueError as e:
        return jsonify({'error': f'Invalid UUID format: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/prompts/generate-uuid', methods=['GET'])
@require_api_key
def generate_uuid():
    """Generate a new UUID for prompt creation"""
    return jsonify({
        'status': 'success',
        'uuid': str(uuid.uuid4())
    })

@app.route('/chat', methods=['POST', 'OPTIONS'])
def chat():
    # Handle preflight requests
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    try:
        # Get the data from the request
        data = request.get_json()
        user_message = data.get('message', '')
        session_data = data.get('session', {})
        conversation_data = data.get('conversation', {})
        # prompt_id = data.get('prompt_id', None) # Optional prompt ID for specific prompts
        
        # Extract session information
        session_id = session_data.get('sessionId')
        session_start_time = session_data.get('sessionStartTime')
        current_time = session_data.get('currentTime')
        
        # Extract conversation information
        conversation_id = conversation_data.get('conversationId')
        conversation_start_time = conversation_data.get('conversationStartTime')
        message_timestamp = conversation_data.get('messageTimestamp')
        
        print(f"\n=== CHAT REQUEST ===")
        print(f"Message: {user_message}")
        print(f"Session ID: {session_id}")
        print(f"Conversation ID: {conversation_id}")
        print(f"===================")

        if scenario_settings['local_logging']['enabled'] == True:
            local_chat_logger.log_message(
                session_id=session_id,
                conversation_id=conversation_id,
                message=user_message,
                role='user'
            )
        if scenario_settings['redcap_logging']['enabled'] == True:
            redcap_logger.log_message(
                session_id=session_id,
                conversation_id=conversation_id,
                message=user_message,
                role='user'
            )
  
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400
        
        # Determine which system prompt to use
        # Check Flask session first, then fall back to default
        system_prompt = session.get('system_prompt', default_system_prompt)
        
        # Initialize session and conversation using session manager
        # Renamed to avoid conflict with Flask's session object
        user_session = session_manager.initialize_session(session_id, session_start_time)
        conversation = session_manager.initialize_conversation(
            conversation_id, 
            conversation_start_time, 
            session_id,
            system_prompt=system_prompt
        )
        
        # Get conversation history for context
        conversation_messages = session_manager.get_conversation_messages(conversation_id, limit=10)
        
        # Get AI response using LLM manager
        llm_response = llm_manager.get_chat_response(
            message=user_message,
            conversation_messages=conversation_messages
        )
        
        ai_response = llm_response['response']
        provider_used = llm_response['provider']
        
        # Store the message and response in conversation history
        session_manager.add_message_to_conversation(conversation_id, user_message, ai_response, session_id)
        
        print(f"LLM Response ({provider_used}): {ai_response[:100]}...")
        print(f"Session stats: {user_session['message_count']} messages, {user_session['conversation_count']} conversations")

        print(f"Session ID: '{session_id}' (type: {type(session_id)})")
        print(f"Conversation ID: '{conversation_id}' (type: {type(conversation_id)})")
        print(f"Bot Message: '{ai_response}' (type: {type(ai_response)})")
        
        if scenario_settings['local_logging']['enabled'] == True:
            local_chat_logger.log_message(
                session_id=session_id,
                conversation_id=conversation_id,
                message=ai_response,
                role='assistant'
            )

        if scenario_settings['redcap_logging']['enabled'] == True:
            redcap_logger.log_message(
                session_id=session_id,
                conversation_id=conversation_id,
                message=ai_response,
                role='assistant'
            )
        
        response_data = {
            'response': ai_response,
            'timestamp': time.time(),
            'status': 'success',
            'provider': provider_used,
            'session': {
                'sessionId': session_id,
                'acknowledged': True,
                'message_count': user_session['message_count'],
                'conversation_count': user_session['conversation_count']
            },
            'conversation': {
                'conversationId': conversation_id,
                'acknowledged': True,
                'message_count': conversation['message_count']
            }
        }
        
        print("About to jsonify response...")
        response = jsonify(response_data)
        
        print("About to add headers...")
        response.headers.add('Access-Control-Allow-Origin', '*')
        
        print("About to return response...")
        return response
        
    except Exception as e:
        print(f"ERROR TYPE: {type(e).__name__}")
        print(f"ERROR MESSAGE: {str(e)}")
        print(f"ERROR TRACEBACK:")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
   
@app.route('/health', methods=['GET'])
def health_check():
    """Comprehensive health check endpoint"""
    session_stats = session_manager.get_session_stats()
    
    return jsonify({
        'status': 'healthy', 
        'timestamp': time.time()
    })

@app.route('/manage-prompts', methods=['GET', 'POST'])
def manage_prompts():
    """Prompt management GUI with basic password protection"""
    
    # Handle login
    if request.method == 'POST':
        password = request.form.get('password')
        expected_password = secrets['INSTANCE_VARS']['admin_password']
        
        if not expected_password:
            return render_template('manage_prompts.html', error='Admin password not configured')
        
        if password == expected_password:
            session['admin_authenticated'] = True
            return redirect('/manage-prompts')
        else:
            return render_template('manage_prompts.html', error='Invalid password')
    
    # Check if already authenticated
    if not session.get('admin_authenticated'):
        return render_template('manage_prompts.html', show_login=True)
    
    # Load prompts for authenticated users
    try:
        prompts = PromptLibrary.list_all_prompts("./prompts/prompts.db")
        api_key = secrets['INSTANCE_VARS']['api_key']  # Get API key from secrets
        return render_template('manage_prompts.html', 
                             prompts=prompts, 
                             authenticated=True,
                             api_key=api_key)  # Pass API key to template
    except Exception as e:
        return render_template('manage_prompts.html', 
                             error=f'Error loading prompts: {str(e)}', 
                             authenticated=True,
                             api_key=secrets['INSTANCE_VARS'].get('api_key', ''))

@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    """Logout from admin interface"""
    session.pop('admin_authenticated', None)
    return redirect('/manage-prompts')

@app.route('/debug/redis')
def debug_redis():
    if app.debug:  # Only in debug mode
        contents = session_manager.debug_redis_contents(detailed=True)
        return jsonify(contents)
    else:
        return "Debug mode only", 403
    
# Uncomment these routes if you want to enable session and conversation reporting features

# @app.route('/session/<session_id>', methods=['GET'])
# def get_session_info(session_id):
#     """Get session information and statistics"""
#     user_session = session_manager.get_session(session_id)
#     if user_session:
#         return jsonify(user_session)
#     else:
#         return jsonify({'error': 'Session not found'}), 404

# @app.route('/conversation/<conversation_id>', methods=['GET'])
# def get_conversation_history(conversation_id):
#     """Get full conversation history"""
#     conversation = session_manager.get_conversation(conversation_id)
#     if conversation:
#         return jsonify(conversation)
#     else:
#         return jsonify({'error': 'Conversation not found'}), 404

# @app.route('/cleanup', methods=['POST'])
# def cleanup_sessions():
#     """Manually trigger cleanup of old sessions"""
#     max_age = request.json.get('max_age_hours', 24) if request.json else 24
#     cleaned_count = session_manager.cleanup_old_sessions(max_age)
#     return jsonify({
#         'status': 'success',
#         'cleaned_sessions': cleaned_count,
#         'remaining_stats': session_manager.get_session_stats()
#     })

if __name__ == '__main__':
    print("Starting Flask server on http://localhost:5500")
    app.run(debug=True, host='0.0.0.0', port=5500)