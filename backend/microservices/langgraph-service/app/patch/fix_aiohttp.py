"""
Fix aiohttp compatibility issues
"""
import aiohttp
from loguru import logger

# Import available exceptions from aiohttp
try:
    from aiohttp import ClientError, ServerTimeoutError, ClientConnectionError
except ImportError:
    from aiohttp import ClientError
    ServerTimeoutError = ClientError
    ClientConnectionError = ClientError

# Apply compatibility patches for missing attributes
patches_applied = []

# ConnectionTimeoutError
if not hasattr(aiohttp, 'ConnectionTimeoutError'):
    aiohttp.ConnectionTimeoutError = ServerTimeoutError
    patches_applied.append('ConnectionTimeoutError')

# SocketTimeoutError  
if not hasattr(aiohttp, 'SocketTimeoutError'):
    aiohttp.SocketTimeoutError = ServerTimeoutError
    patches_applied.append('SocketTimeoutError')

# ClientConnectionError
if not hasattr(aiohttp, 'ClientConnectionError'):
    aiohttp.ClientConnectionError = ClientConnectionError
    patches_applied.append('ClientConnectionError')

# ServerTimeoutError
if not hasattr(aiohttp, 'ServerTimeoutError'):
    aiohttp.ServerTimeoutError = ServerTimeoutError
    patches_applied.append('ServerTimeoutError')

# Log what was patched
if patches_applied:
    logger.info(f"Applied aiohttp compatibility patches for: {', '.join(patches_applied)}")
else:
    logger.info("No aiohttp compatibility patches needed")