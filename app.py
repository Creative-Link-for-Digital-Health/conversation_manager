from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import time
import os
import toml


print("Starting Flask server...")

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
    # Import loggers
    from loggers.local_logger import LocalLogger
    local_chat_logger = LocalLogger("./loggers/chat_logs.db")
else:    
    print("Local logging is disabled. No local logger will be used.")

# REDCAP LOGGING
if scenario_settings['redcap_logging']['enabled'] == True:
    print("REDCap logging is enabled.")
    # Import loggers
    from loggers.redcap_logger import RedCAPLogger
    redcap_logger = RedCAPLogger("./.secrets.toml")
else:
    print("RedCAP logging is disabled. No RedCAP logger will be used.")


from prompts.prompt_utils import PromptLibrary
prompt_library = PromptLibrary( scenario_settings['system_prompt']['prompt_id'], "./prompts/prompts.db")
system_prompt = prompt_library.checkout()
# print(f"""SYSTEM_PROMPT: {system_prompt}""")

# Initialize managers
session_manager = SessionManager()
llm_manager = LLMManager("./.secrets.toml", "./scenario.toml") #TODO rewrite to pass which LLM directly


app = Flask(__name__)
CORS(app, resources={
    r"/chat": {"origins": "*"},
    r"/health": {"origins": "*"}
})

@app.route('/')
def home():
    """Render the main chat interface"""
    return render_template('index.html')

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
        prompt_id = data.get('prompt_id', None) # Optional prompt ID for specific prompts
        
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
        
        # Initialize session and conversation using session manager
        session = session_manager.initialize_session(session_id, session_start_time)
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
        print(f"Session stats: {session['message_count']} messages, {session['conversation_count']} conversations")

        print(f"Session ID: '{session_id}' (type: {type(session_id)})")
        print(f"Conversation ID: '{conversation_id}' (type: {type(conversation_id)})")
        print(f"Bot Message: '{ai_response}' (type: {type(ai_response)})")
        
        if scenario_settings['local_logging']['enabled'] == True:
            local_chat_logger.log_message(
                session_id = session_id,
                conversation_id = conversation_id,
                message = ai_response,
                role='assistant'
            )

        if scenario_settings['redcap_logging']['enabled'] == True:
            redcap_logger.log_message(
                session_id = session_id,
                conversation_id = conversation_id,
                message = ai_response,
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
                'message_count': session['message_count'],
                'conversation_count': session['conversation_count']
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
#     session = session_manager.get_session(session_id)
#     if session:
#         return jsonify(session)
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