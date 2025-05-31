import enum

class IndexingStatus(enum.IntEnum):
    NOT_INDEXED = 0  # Default state, or if processing hasn't started for some reason
    INDEXED = 1
    INDEXING_ERROR = 2
    PROCESSING = 3   # Document is currently being processed

class ErrorCode(enum.Enum):
    # Authentication errors
    INVALID_CREDENTIALS = "invalid_credentials"
    EXPIRED_TOKEN = "expired_token"
    INSUFFICIENT_PERMISSIONS = "insufficient_permissions"
    
    # Document errors
    DOCUMENT_NOT_FOUND = "document_not_found"
    DOCUMENT_PROCESSING_ERROR = "document_processing_error"
    INVALID_FILE_TYPE = "invalid_file_type"
    FILE_TOO_LARGE = "file_too_large"
    
    # Tenant errors
    TENANT_NOT_FOUND = "tenant_not_found"
    TENANT_LIMIT_EXCEEDED = "tenant_limit_exceeded"
    
    # General errors
    VALIDATION_ERROR = "validation_error"
    INTERNAL_SERVER_ERROR = "internal_server_error"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"