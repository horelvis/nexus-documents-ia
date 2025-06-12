# Unified Security Implementation for Microservices

## Overview

All microservices now use a unified security implementation to avoid conflicts between path parameters and header dependencies in FastAPI. This resolves the `Cannot use 'Header' for path param 'tenant_id'` error.

## Common Pattern

### Core Functions

All services now implement these common functions:

```python
def get_api_key_from_header(request: Request) -> str
def get_tenant_id_from_header(request: Request) -> Optional[str]
def get_user_id_from_header(request: Request) -> Optional[str]
def validate_api_key(api_key: str = Depends(get_api_key_from_header)) -> bool
def validate_service_access(...) -> dict
def validate_tenant_access(tenant_id: str, context: dict) -> str
```

### Key Changes

1. **Using `Request` instead of `Header` dependencies**: Eliminates conflicts with path parameters
2. **Optional tenant_id in headers**: Allows tenant_id to be in path parameters without conflicts
3. **Consistent validation patterns**: All services follow the same security validation flow
4. **Legacy compatibility**: Existing endpoints continue to work

## Service-Specific Implementation

### LangChain Service (`langchain-service/app/core/security.py`)
- ✅ **Fully unified implementation**
- ✅ **All routes updated to use `validate_service_access`**
- ✅ **Resolves the original FastAPI error**

### Langroid Service (`langroid-service/app/core/security.py`)
- ✅ **Unified base implementation**
- ✅ **Maintains existing SecurityService class for agent management**
- ✅ **Backwards compatible with existing endpoints**
- ✅ **Legacy functions updated to use new pattern**

### Storage Service (`storage-service/app/core/security.py`)
- ✅ **Unified implementation**
- ✅ **Maintains existing `validate_tenant_access` function**
- ✅ **Added new `validate_service_access` function**
- ✅ **Backwards compatible with existing API endpoints**

### Ollama Service (`ollama-service/app/core/security.py`)
- ✅ **New security module created**
- ✅ **Unified implementation**
- ✅ **Optional API key validation (can be disabled)**
- ✅ **Ready for authentication if needed**

## Usage Patterns

### For routes with tenant_id in path:
```python
@app.delete("/documents/{tenant_id}/{doc_id}")
async def delete_document(
    tenant_id: str, 
    doc_id: str,
    security: dict = Depends(validate_service_access)
) -> dict:
    # validate_service_access doesn't require tenant_id in headers
    # tenant_id comes from path parameter
    validated_tenant_id = validate_tenant_access(tenant_id, security)
    # ... rest of function
```

### For routes with tenant_id in headers only:
```python
@app.post("/documents/add")
async def add_document(
    request: AddDocumentRequest,
    security: dict = Depends(validate_service_access)
) -> dict:
    # tenant_id must be in headers (X-Tenant-ID)
    tenant_id = security.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant ID required in headers")
    # ... rest of function
```

## Benefits

1. **No more FastAPI conflicts**: Path parameters and headers work together
2. **Consistent security**: All services use the same pattern
3. **Flexible tenant handling**: Works with tenant_id in path or headers
4. **Backwards compatible**: Existing endpoints continue to work
5. **Easy to maintain**: Single pattern across all microservices

## Testing

All services should now start without the original error:
```
Cannot use `Header` for path param 'tenant_id'
```

## Future Improvements

1. **Common security module**: Consider creating a shared security package
2. **Enhanced validation**: Add more sophisticated tenant/user validation
3. **Token-based auth**: Migrate from API keys to JWT tokens
4. **Role-based permissions**: Expand the permission system