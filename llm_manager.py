"""
LLM Manager Module
"""

import sys
from typing import Dict
from openai import OpenAI

# Use modern TOML library
try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # pip install tomli


def load_api_params(secrets_path: str, scenario_path: str) -> Dict[str, str]:
    """Load API parameters from TOML files"""
    try:
        with open(secrets_path, 'rb') as f:
            secrets = tomllib.load(f)
        with open(scenario_path, 'rb') as f:
            scenario = tomllib.load(f)

        provider = scenario['llm_provider']['name']
        model = scenario['llm_provider']['model']
        print(f"""PROVIDER: {provider} MODEL: {model}""")

        return {
            'API_KEY': secrets[provider]['API_KEY'],
            'API_URL': secrets[provider]['API_URL'],
            'MODEL': model,
        }
    except Exception as e:
        print(f"Error loading API parameters: {e}", file=sys.stderr)
        sys.exit(1)


class LLMManager:
    """Simple LLM wrapper"""
    
    def __init__(self, secrets_path: str, scenario_path: str):
        """Initialize with TOML config files"""
        params = load_api_params(secrets_path, scenario_path)
        
        self.model = params['MODEL']
        self.client = OpenAI(
            base_url=params['API_URL'],
            api_key=params['API_KEY']
        )
    
    def get_completion(self, prompt: str, **kwargs) -> str:
        """Get completion from LLM"""
        messages = [{"role": "user", "content": prompt}]
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs
        )
        
        return response.choices[0].message.content
    
    def get_chat_response(self, message: str, conversation_messages: list = None, **kwargs) -> dict:
        """Get chat response with conversation context"""
        messages = []
        
        # Add conversation history
        if conversation_messages:
            for msg in conversation_messages:
                messages.append({"role": "user", "content": msg['user_message']})
                messages.append({"role": "assistant", "content": msg['ai_response']})
        
        # Add current message
        messages.append({"role": "user", "content": message})
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs
        )
        
        return {
            'response': response.choices[0].message.content,
            'provider': 'openai_compatible'
        }

# # Usage example:
# if __name__ == "__main__":
#     llm = LLMManager("../.secrets.toml", "../scenario.toml")
    
#     # Simple completion
#     result = llm.get_completion("Hello, how are you?")
#     print(result)
    
#     # Chat with conversation history
#     conversation_messages = [
#         {"user_message": "My name is John", "ai_response": "Nice to meet you, John!"},
#         {"user_message": "What's my favorite color?", "ai_response": "I don't know your favorite color yet."}
#     ]
    
#     chat_result = llm.get_chat_response(
#         message="What's my name?",
#         conversation_messages=conversation_messages
#     )
    
#     print(f"Response: {chat_result['response']}")
#     print(f"Provider: {chat_result['provider']}")