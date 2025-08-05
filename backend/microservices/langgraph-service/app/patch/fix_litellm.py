"""
Fix litellm compatibility issues
"""
import litellm
from loguru import logger

# Add missing _key_management_system attribute if needed
if not hasattr(litellm, '_key_management_system'):
    # Create a dummy key management system
    class DummyKeyManagementSystem:
        def __init__(self):
            self.keys = {}
        
        def get_key(self, provider):
            return None
            
        def set_key(self, provider, key):
            self.keys[provider] = key
    
    litellm._key_management_system = DummyKeyManagementSystem()
    logger.info("Applied litellm._key_management_system compatibility patch")