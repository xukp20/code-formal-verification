from typing import Dict, List, Tuple
import json
from collections import defaultdict

class LLMRouter:
    def __init__(self, config_path: str):
        self.config_path = config_path
        # Change to track (model, backend) combination usage
        self.usage_counts = defaultdict(lambda: defaultdict(int))
        self.load_config()

    def load_config(self):
        """Load and process the config file"""
        with open(self.config_path, 'r') as f:
            config = json.load(f)
            
        self.backends = config.get('backends', {})
        self.models = config.get('models', {})

        # Init usage counts
        for model in self.models:
            for backend in self.models[model]:
                self.usage_counts[model][backend] = 0

    def get_backend(self, model_name: str) -> Tuple[str, str, str]:
        """
        Get the least used backend for the given model
        Returns (actual_model_name, base_url, api_key)
        """
        if model_name not in self.models:
            raise ValueError(f"Model {model_name} not found in configuration")
            
        available_backends = self.models[model_name]
        if not available_backends:
            raise ValueError(f"No backends available for model {model_name}")
            
        # Find backend with minimum usage for this specific model
        min_usage = float('inf')
        selected_backend = None
        
        for backend_name in available_backends:
            if backend_name not in self.backends:
                continue
            # Check usage count for this specific model-backend combination
            if self.usage_counts[model_name][backend_name] < min_usage:
                min_usage = self.usage_counts[model_name][backend_name]
                selected_backend = backend_name
                
        if not selected_backend:
            raise ValueError(f"No valid backend found for model {model_name}")
                
        # Increment usage count for this model-backend combination
        self.usage_counts[model_name][selected_backend] += 1
        
        backend_config = self.backends[selected_backend]
        actual_model = backend_config["models"].get(model_name, model_name)
        
        print(f"Using {actual_model} from {selected_backend}")
        return actual_model, backend_config["base_url"], backend_config["api_key"]

    def get_usage_stats(self, model_name: str) -> Dict[str, int]:
        """Return current usage statistics for a specific model"""
        return dict(self.usage_counts[model_name])


import os

GLOBAL_ROUTER = None
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, "config.json")
    GLOBAL_ROUTER = LLMRouter(config_path)
except Exception as e:
    print(f"Error loading config: {e}")


def test_router(verbose=False):
    # Get the absolute path to config.json
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, "config.json")
    
    router = LLMRouter(config_path)
    
    # Test multiple calls to see load balancing in action
    for i in range(3):
        model, base_url, api_key = router.get_backend("deepseek-chat")
        if verbose:
            print(f"\nCall {i+1}:")
            print(f"Model name: {model}")
            print(f"Base URL: {base_url}")
            print(f"API Key: {api_key}")
            print("\nCurrent usage stats:")
            print(router.get_usage_stats("deepseek-chat"))

if __name__ == "__main__":
    test_router(verbose=True)