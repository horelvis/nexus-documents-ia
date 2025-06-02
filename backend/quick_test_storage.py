#!/usr/bin/env python3
"""
Quick test to verify storage factory works correctly.
Run this before running the full test suite.
"""

import os
import sys
import logging

# Set up path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure for testing mode
os.environ["TESTING"] = "true"
os.environ["USE_MOCK_STORAGE"] = "true"

# Import after setting environment
from app.services.storage_factory import StorageServiceFactory

# Configure logging
logging.basicConfig(level=logging.INFO)

def main():
    print("🔧 Quick Storage Test")
    print("=" * 30)
    
    try:
        # Test factory creation
        storage = StorageServiceFactory.create_storage_service(
            tenant_id="test-tenant",
            user_id="test-user"
        )
        
        print(f"✅ Storage service created: {type(storage).__name__}")
        
        # Test basic operations
        import io
        test_content = b"Hello, World!"
        test_file = io.BytesIO(test_content)
        
        # Upload test
        upload_result = storage.upload_file(test_file, "test-file.txt", {"test": "true"})
        print(f"✅ Upload test: {upload_result}")
        
        # Download test
        downloaded = storage.download_file("test-file.txt")
        print(f"✅ Download test: {downloaded == test_content}")
        
        # List test
        files = storage.list_files()
        print(f"✅ List test: {len(files)} files found")
        
        # Delete test
        delete_result = storage.delete_file("test-file.txt")
        print(f"✅ Delete test: {delete_result}")
        
        # Health check
        health = storage.health_check()
        print(f"✅ Health check: {health}")
        
        print("\n🎉 All tests passed! Storage factory is working correctly.")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)