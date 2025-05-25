from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import time
import random

app = Flask(__name__)
CORS(app, resources={
    r"/chat": {"origins": "*"},
    r"/health": {"origins": "*"}
})

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
        print(f"Session Start: {session_start_time}")
        print(f"Current Time: {current_time}")
        print(f"Conversation ID: {conversation_id}")
        print(f"Conversation Start: {conversation_start_time}")
        print(f"Message Timestamp: {message_timestamp}")
        print(f"===================\n")
        
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400
        
        # Simulate some processing time
        time.sleep(random.uniform(0.5, 2.0))
        
        # Generate a response (you can replace this with actual AI logic)
        responses = [
            f"That's an interesting point about '{user_message}'. Let me think about that...",
            f"I understand you're asking about '{user_message}'. Here's what I think...",
            f"Thanks for sharing that. Regarding '{user_message}', I'd say...",
            f"That's a great question about '{user_message}'. In my experience...",
            f"You mentioned '{user_message}' - that's quite thought-provoking.",
            f"I see you're interested in '{user_message}'. Let me elaborate on that.",
            f"Regarding '{user_message}', there are several aspects to consider...",
            f"Your question about '{user_message}' touches on an important topic."
        ]
        
        ai_response = random.choice(responses)
        
        print(f"Sending response: {ai_response}")
        
        response_data = {
            'response': ai_response,
            'timestamp': time.time(),
            'status': 'success',
            'session': {
                'sessionId': session_id,
                'acknowledged': True
            },
            'conversation': {
                'conversationId': conversation_id,
                'acknowledged': True
            }
        }
        
        response = jsonify(response_data)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': time.time()})

if __name__ == '__main__':
    print("Starting Flask server on http://localhost:5500")
    app.run(debug=True, host='0.0.0.0', port=5500)