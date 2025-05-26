"""
LLM Manager Module
Handles interactions with Large Language Model providers (OpenAI, etc.)
Reads configuration from secrets.toml and scenario.toml files
"""

import openai
import os
import toml
from typing import List, Dict, Optional

class LLMProvider:
    """LLM provider implementation"""
    
    def __init__(self, provider_config: Dict, secrets_config: Dict):
        """
        Initialize LLM provider with configuration from TOML files
        
        Args:
            provider_config: Configuration from scenario.toml
            secrets_config: Secrets from secrets.toml
        """
        # Required fields - fail if missing
        required_fields = ['name', 'secrets_key', 'model', 'temperature', 'max_tokens']
        missing_fields = [field for field in required_fields if field not in provider_config]
        
        if missing_fields:
            raise ValueError(f"Missing required fields in [llm_provider] section of scenario.toml: {missing_fields}")
        
        self.provider_name = provider_config['name']
        self.secrets_key = provider_config['secrets_key']
        self.model = provider_config['model']
        self.temperature = provider_config['temperature']
        self.max_tokens = provider_config['max_tokens']
        
        # Get secrets for this provider
        provider_secrets = secrets_config.get(self.secrets_key, {})
        self.api_key = provider_secrets.get('API_KEY')
        self.api_url = provider_secrets.get('API_URL', 'https://api.openai.com/v1')
        
        # Override model from secrets if specified
        if provider_secrets.get('MODEL'):
            self.model = provider_secrets.get('MODEL')
        
        # Configure OpenAI client if this is an OpenAI-compatible provider
        if self.api_key:
            openai.api_key = self.api_key
            if self.api_url != 'https://api.openai.com/v1':
                openai.api_base = self.api_url
    
    def get_response(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        Get response from LLM API
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            **kwargs: Additional parameters for the API call
            
        Returns:
            str: AI response text
        """
        try:
            # Default parameters from configuration
            params = {
                'model': self.model,
                'messages': messages,
                'max_tokens': kwargs.get('max_tokens', self.max_tokens),
                'temperature': kwargs.get('temperature', self.temperature)
            }
            
            # Override with any additional kwargs
            params.update(kwargs)
            
            response = openai.ChatCompletion.create(**params)
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            raise Exception(f"{self.provider_name} API error: {str(e)}")
    
    def is_configured(self) -> bool:
        """Check if provider is properly configured"""
        return bool(self.api_key)



class LLMManager:
    """
    Manages LLM interactions with configuration from TOML files
    """
    
    def __init__(self, scenario_file: str = "scenario.toml", secrets_file: str = ".secrets.toml"):
        """
        Initialize LLM Manager with configuration files
        
        Args:
            scenario_file: Path to scenario configuration file
            secrets_file: Path to secrets configuration file
        """
        self.scenario_config = self._load_scenario_config(scenario_file)
        self.secrets_config = self._load_secrets_config(secrets_file)
        
        # Initialize provider
        self.primary_provider = self._create_primary_provider()
        
        # Load system prompt configuration
        self.system_prompt_config = self.scenario_config.get('system_prompt', {})
        self.default_system_prompt = self.system_prompt_config.get(
            'fallback_content', 
            "You are a helpful AI assistant. Provide thoughtful, accurate, and engaging responses."
        )
        
        print(f"LLM Manager initialized successfully:")
        print(f"- Provider: {self.primary_provider.provider_name}")
        print(f"- Model: {self.primary_provider.model}")
        print(f"- API configured: {self.primary_provider.is_configured()}")
    
    def _load_scenario_config(self, scenario_file: str) -> Dict:
        """Load scenario configuration from TOML file"""
        try:
            with open(scenario_file, 'r') as f:
                config = toml.load(f)
                print(f"Loaded scenario configuration from {scenario_file}")
                return config
        except FileNotFoundError:
            raise FileNotFoundError(f"Required configuration file '{scenario_file}' not found. Please create this file with your LLM provider settings.")
        except Exception as e:
            raise Exception(f"Failed to load scenario configuration from '{scenario_file}': {e}")
    
    def _load_secrets_config(self, secrets_file: str) -> Dict:
        """Load secrets configuration from TOML file"""
        try:
            with open(secrets_file, 'r') as f:
                config = toml.load(f)
                print(f"Loaded secrets configuration from {secrets_file}")
                return config
        except FileNotFoundError:
            # Try environment variables as fallback
            env_config = self._get_env_fallback()
            if not any(provider.get('API_KEY') for provider in env_config.values()):
                raise FileNotFoundError(f"Required secrets file '{secrets_file}' not found and no API keys found in environment variables. Please create '{secrets_file}' with your API keys.")
            print(f"Warning: {secrets_file} not found, using environment variables")
            return env_config
        except Exception as e:
            raise Exception(f"Failed to load secrets configuration from '{secrets_file}': {e}")
    

    
    def _get_env_fallback(self) -> Dict:
        """Fallback to environment variables if secrets file not found"""
        return {
            "OPENAI": {
                "API_KEY": os.getenv('OPENAI_API_KEY'),
                "API_URL": "https://api.openai.com/v1",
                "MODEL": os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')
            }
        }
    
    def _create_primary_provider(self) -> LLMProvider:
        """Create the primary LLM provider from configuration"""
        provider_config = self.scenario_config.get('llm_provider', {})
        
        if not provider_config:
            raise ValueError("No 'llm_provider' section found in scenario configuration. Please add LLM provider settings to your scenario.toml file.")
        
        provider = LLMProvider(provider_config, self.secrets_config)
        
        if not provider.is_configured():
            secrets_key = provider_config.get('secrets_key', 'OPENAI')
            raise ValueError(f"LLM provider not properly configured. Missing API key for '{secrets_key}' in secrets file or environment variables.")
        
        return provider
    
    def get_chat_response(self, message: str, conversation_messages: List[Dict] = None, 
                         system_prompt: Optional[str] = None, **kwargs) -> Dict[str, any]:
        """
        Get a chat response with conversation context
        
        Args:
            message: Current user message
            conversation_messages: Previous messages for context
            system_prompt: Custom system prompt (optional)
            **kwargs: Additional parameters for the LLM call
            
        Returns:
            dict: Response data including text, provider used, etc.
        """
        # Build message history
        messages = self._build_message_history(message, conversation_messages, system_prompt)
        
        # Try primary provider
        response_data = self._try_provider(self.primary_provider, messages, "primary", **kwargs)
        
        # If provider fails, return error response
        if not response_data:
            response_data = {
                'response': "I'm experiencing technical difficulties. Please try again later.",
                'provider': 'error',
                'success': False,
                'error': 'LLM provider failed'
            }
        
        return response_data
    
    def _build_message_history(self, current_message: str, conversation_messages: List[Dict] = None, 
                              system_prompt: Optional[str] = None) -> List[Dict[str, str]]:
        """Build the message history for the LLM call"""
        messages = []
        
        # Add system prompt
        system_text = system_prompt or self.default_system_prompt
        messages.append({"role": "system", "content": system_text})
        
        # Add conversation history
        if conversation_messages:
            for msg in conversation_messages[-10:]:  # Last 10 for context
                messages.append({"role": "user", "content": msg['user_message']})
                messages.append({"role": "assistant", "content": msg['ai_response']})
        
        # Add current message
        messages.append({"role": "user", "content": current_message})
        
        return messages
    
    def _try_provider(self, provider, messages: List[Dict[str, str]], 
                     provider_name: str, **kwargs) -> Optional[Dict[str, any]]:
        """Try to get a response from a specific provider"""
        try:
            if not provider.is_configured():
                print(f"{provider_name} provider not configured, skipping...")
                return None
                
            response_text = provider.get_response(messages, **kwargs)
            
            return {
                'response': response_text,
                'provider': provider_name,
                'success': True,
                'error': None
            }
            
        except Exception as e:
            print(f"{provider_name} provider failed: {str(e)}")
            return None
    
    def get_available_providers(self) -> Dict[str, bool]:
        """Get status of available provider"""
        return {
            'primary': self.primary_provider.is_configured()
        }
    
    def get_provider_info(self) -> Dict[str, any]:
        """Get detailed information about the current provider configuration"""
        return {
            'provider_name': self.primary_provider.provider_name,
            'model': self.primary_provider.model,
            'temperature': self.primary_provider.temperature,
            'max_tokens': self.primary_provider.max_tokens,
            'configured': self.primary_provider.is_configured()
        }