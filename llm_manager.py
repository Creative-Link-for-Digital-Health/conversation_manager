"""
LLM Manager Module
"""

import sys
from typing import Dict
from openai import OpenAI

import time
from datetime import datetime

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
        
    # def get_chat_response(self, message: str, conversation_messages: list = None, **kwargs) -> dict:
    #     """Get chat response with conversation context"""
    #     messages = []
        
    #     # Add conversation history
    #     if conversation_messages:
    #         for msg in conversation_messages:
    #             # Handle the new format with 'role' and 'content'
    #             if 'role' in msg and 'content' in msg:
    #                 messages.append({
    #                     "role": msg['role'], 
    #                     "content": msg['content']
    #                 })
    #             # Keep backward compatibility with old format
    #             elif 'user_message' in msg and 'ai_response' in msg:
    #                 messages.append({"role": "user", "content": msg['user_message']})
    #                 messages.append({"role": "assistant", "content": msg['ai_response']})
        
    #     # Add current message
    #     messages.append({"role": "user", "content": message})
        
    #     response = self.client.chat.completions.create(
    #         model=self.model,
    #         messages=messages,
    #         **kwargs
    #     )
        
    #     return {
    #         'response': response.choices[0].message.content,
    #         'provider': 'openai_compatible'
    #     }



    def get_chat_response(self, message: str, conversation_messages: list = None, **kwargs) -> dict:
        """Get chat response with conversation context"""
        print(f"LLM request started at {datetime.now().isoformat()}")
        start_time = time.time()
        
        # Set a default timeout if not provided
        if 'timeout' not in kwargs:
            kwargs['timeout'] = 30.0  # 30 second timeout
        
        try:
            messages = []
            
            # Add conversation history
            if conversation_messages:
                for msg in conversation_messages:
                    # Handle the new format with 'role' and 'content'
                    if 'role' in msg and 'content' in msg:
                        messages.append({
                            "role": msg['role'], 
                            "content": msg['content']
                        })
                    # Keep backward compatibility with old format
                    elif 'user_message' in msg and 'ai_response' in msg:
                        messages.append({"role": "user", "content": msg['user_message']})
                        messages.append({"role": "assistant", "content": msg['ai_response']})
            
            # Add current message
            messages.append({"role": "user", "content": message})
            
            print(f"Sending request to LLM API with {len(messages)} messages")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                **kwargs
            )
            
            response_time = time.time() - start_time
            print(f"LLM request completed in {response_time:.2f} seconds")
            
            return {
                'response': response.choices[0].message.content,
                'provider': 'openai_compatible',
                'response_time': response_time
            }
        except Exception as e:
            response_time = time.time() - start_time
            print(f"LLM request failed after {response_time:.2f} seconds: {str(e)}")
            # Return a graceful error message
            return {
                'response': f"I'm sorry, I encountered a problem while processing your request. Please try again in a moment.",
                'provider': 'error',
                'error': str(e),
                'response_time': response_time
            }