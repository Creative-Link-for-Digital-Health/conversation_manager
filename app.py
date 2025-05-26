from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import time
import os

# Import our custom modules
from session_manager import SessionManager
from llm_manager import LLMManager

app = Flask(__name__)
CORS(app, resources={
    r"/chat": {"origins": "*"},
    r"/health": {"origins": "*"}
})

# Initialize managers
session_manager = SessionManager()
llm_manager = LLMManager("./.secrets.toml", "./scenario.toml")

@app.route('/')
def home():
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
        
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400
        
        # Initialize session and conversation using session manager
        session = session_manager.initialize_session(session_id, session_start_time)
        conversation = session_manager.initialize_conversation(conversation_id, conversation_start_time, session_id)
        
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

@app.route('/session/<session_id>', methods=['GET'])
def get_session_info(session_id):
    """Get session information and statistics"""
    session = session_manager.get_session(session_id)
    if session:
        return jsonify(session)
    else:
        return jsonify({'error': 'Session not found'}), 404

@app.route('/conversation/<conversation_id>', methods=['GET'])
def get_conversation_history(conversation_id):
    """Get full conversation history"""
    conversation = session_manager.get_conversation(conversation_id)
    if conversation:
        return jsonify(conversation)
    else:
        return jsonify({'error': 'Conversation not found'}), 404

@app.route('/cleanup', methods=['POST'])
def cleanup_sessions():
    """Manually trigger cleanup of old sessions"""
    max_age = request.json.get('max_age_hours', 24) if request.json else 24
    cleaned_count = session_manager.cleanup_old_sessions(max_age)
    return jsonify({
        'status': 'success',
        'cleaned_sessions': cleaned_count,
        'remaining_stats': session_manager.get_session_stats()
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Comprehensive health check endpoint"""
    session_stats = session_manager.get_session_stats()
    llm_providers = llm_manager.get_available_providers()
    
    return jsonify({
        'status': 'healthy', 
        'timestamp': time.time()
    })

if __name__ == '__main__':
    print("Starting Flask server on http://localhost:5500")
    app.run(debug=True, host='0.0.0.0', port=5500)