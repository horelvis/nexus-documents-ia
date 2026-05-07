# Unified Security Implementation for Microservices

## Overview

All active microservices use a shared internal-auth pattern based on the
`X-API-Key` header plus optional request context headers. The previous
tenant-header workaround is historical; the current deployment is
single-tenant on-premise.

## Common Pattern

### Core Functions

All services now implement these common functions:

```python
def get_api_key_from_header(request: Request) -> str
def get_user_id_from_header(request: Request) -> Optional[str]
def validate_api_key(api_key: str = Depends(get_api_key_from_header)) -> bool
def validate_service_access(...) -> dict
```

### Key Changes

1. **Use `X-API-Key` for service-to-service auth**.
2. **Propagate request context explicitly** with headers such as `X-User-ID`, `X-User-Roles`, and `X-Request-ID`.
3. **Keep tenant identifiers as compatibility scopes only**; they are not a security boundary.
4. **Validate every internal endpoint at the edge** before doing DB, storage, or model work.

## Service-Specific Implementation

### Storage Service (`storage-service/app/core/security.py`)
- ✅ **Unified implementation**
- ✅ **Added new `validate_service_access` function**
- ✅ **Backwards compatible with existing API endpoints**

### Emma Agent Service (`emma-agent-service/app/core/security.py`)
- ✅ **Validates internal service calls with `X-API-Key`**
- ✅ **Accepts propagated user context for ACL-aware tool calls**

### Weaviate Service (`weaviate-service/app/core/security.py`)
- ✅ **Validates internal indexing/search calls with `X-API-Key`**
- ✅ **Delegates document extraction and embeddings to intelligence-docs-service**

## Usage Patterns

### For routes with compatibility scope in path:
```python
@app.delete("/documents/{tenant_id}/{doc_id}")
async def delete_document(
    scope_id: str,
    doc_id: str,
    security: dict = Depends(validate_service_access)
) -> dict:
    # Scope identifiers are compatibility values, not auth boundaries.
    # ... rest of function
```

### For routes that need user context:
```python
@app.post("/documents/add")
async def add_document(
    request: AddDocumentRequest,
    security: dict = Depends(validate_service_access)
) -> dict:
    user_id = security.get("user_id")
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
