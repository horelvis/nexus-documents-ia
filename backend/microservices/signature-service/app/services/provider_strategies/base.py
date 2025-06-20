"""
Base class for signature provider strategies
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

class SignatureProviderStrategy(ABC):
    """Base class for all signature provider implementations"""
    
    @abstractmethod
    async def create_signature_request(
        self, 
        credentials: Dict[str, Any], 
        request_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a signature request with the provider"""
        pass
    
    @abstractmethod
    async def get_signature_status(
        self, 
        credentials: Dict[str, Any], 
        external_id: str
    ) -> Dict[str, Any]:
        """Get the status of a signature request"""
        pass
    
    @abstractmethod
    async def cancel_signature_request(
        self, 
        credentials: Dict[str, Any], 
        external_id: str,
        reason: str
    ) -> bool:
        """Cancel a signature request"""
        pass
    
    @abstractmethod
    async def download_signed_document(
        self, 
        credentials: Dict[str, Any], 
        external_id: str
    ) -> bytes:
        """Download the signed document"""
        pass
    
    @abstractmethod
    async def test_connection(
        self, 
        credentials: Dict[str, Any]
    ) -> Dict[str, bool]:
        """Test the connection with the provider"""
        pass