#!/usr/bin/env python3
"""
Patch litellm library on startup to fix AsyncHTTPHandler issue
"""
import sys
import warnings

def monkey_patch_litellm():
    """Apply monkey patch to litellm's AsyncHTTPHandler"""
    try:
        # Import the module
        from litellm.llms.custom_httpx import http_handler
        
        # Save the original close method
        original_close = http_handler.AsyncHTTPHandler.close if hasattr(http_handler, 'AsyncHTTPHandler') else None
        
        # Define the patched close method
        async def patched_close(self):
            """Patched close method that handles missing client attribute"""
            try:
                if hasattr(self, 'client') and self.client is not None:
                    await self.client.aclose()
            except (AttributeError, RuntimeError) as e:
                # Silently ignore these errors
                pass
            except Exception as e:
                # Log other errors but don't fail
                warnings.warn(f"Error closing AsyncHTTPHandler: {e}")
        
        # Apply the monkey patch
        if hasattr(http_handler, 'AsyncHTTPHandler'):
            http_handler.AsyncHTTPHandler.close = patched_close
            print("✅ Successfully monkey-patched litellm AsyncHTTPHandler")
            return True
        else:
            print("⚠️ AsyncHTTPHandler not found in litellm")
            return False
            
    except ImportError as e:
        print(f"⚠️ Could not import litellm: {e}")
        return False
    except Exception as e:
        print(f"❌ Failed to apply monkey patch: {e}")
        return False

# Apply the patch when this module is imported
monkey_patch_litellm()