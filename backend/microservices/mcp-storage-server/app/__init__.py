"""
MCP Storage Server

A Model Context Protocol (MCP) server that provides file storage operations
for the NouxCubeIA platform. This server replaces the legacy storage-service
microservice with a standardized MCP interface.

Features:
- Upload files to Google Cloud Storage
- Download file content
- List files in a directory/bucket
- Delete files
- Generate signed URLs for direct access
- Move/rename files

All operations are tenant-isolated and respect the multi-tenant architecture.
"""

__version__ = "1.0.0"
