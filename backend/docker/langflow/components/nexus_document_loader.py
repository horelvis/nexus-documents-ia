"""
Custom Langflow component to load documents from Nexus API
"""
from typing import List, Optional
from langflow import CustomComponent
from langflow.field_typing import Document
import httpx


class NexusDocumentLoader(CustomComponent):
    display_name = "Nexus Document Loader"
    description = "Load documents from Nexus document management system"
    
    def build_config(self):
        return {
            "api_url": {
                "display_name": "API URL",
                "value": "http://backend:8000",
                "type": "str",
            },
            "api_key": {
                "display_name": "API Key",
                "type": "str",
                "password": True,
            },
            "tenant_id": {
                "display_name": "Tenant ID",
                "type": "str",
                "required": True,
            },
            "limit": {
                "display_name": "Document Limit",
                "value": 10,
                "type": "int",
            },
            "tags": {
                "display_name": "Filter by Tags",
                "type": "str",
                "info": "Comma-separated tags",
            }
        }

    def build(
        self,
        api_url: str,
        api_key: str,
        tenant_id: str,
        limit: int = 10,
        tags: Optional[str] = None
    ) -> List[Document]:
        """Load documents from Nexus API"""
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "X-Tenant-ID": tenant_id
        }
        
        params = {"limit": limit}
        if tags:
            params["tags"] = tags.split(",")
        
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{api_url}/api/v1/documents",
                    headers=headers,
                    params=params
                )
                response.raise_for_status()
                
                documents = []
                for doc in response.json():
                    documents.append(
                        Document(
                            page_content=doc.get("content", ""),
                            metadata={
                                "id": doc["id"],
                                "title": doc["title"],
                                "filename": doc["filename"],
                                "tags": doc.get("tags", []),
                                "created_at": doc["created_at"]
                            }
                        )
                    )
                
                self.status = f"Loaded {len(documents)} documents"
                return documents
                
        except Exception as e:
            self.status = f"Error: {str(e)}"
            return []