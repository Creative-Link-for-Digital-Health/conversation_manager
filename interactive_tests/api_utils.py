from typing import Dict, Any, List
import toml
import sys
from openai import OpenAI

# Load Configuration
def load_api_params(SECRETS_PATH, SCENARIO_PATH) -> Dict[str, str]:
    """Load API parameters from TOML file."""
    try:
        with open(SECRETS_PATH, 'r') as f:
            secrets = toml.load(f)
        with open(SCENARIO_PATH, 'r') as f:
            scenario = toml.load(f)
        return {
            'API_KEY': secrets['OPENROUTER']['API_KEY'],
            'API_URL': secrets['OPENROUTER']['API_URL'],
            'MODEL': scenario['llm_provider']['model'],
        }
    except Exception as e:
        print(f"Error loading API key: {e}", file=sys.stderr)
        sys.exit(1)
