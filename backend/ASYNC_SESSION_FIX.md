# AsyncSession Fix for Document Service

## Problem
The document preview endpoint was failing with:
```
AttributeError: 'AsyncSession' object has no attribute 'query'
```

This occurred because several endpoints in `documents.py` were using the synchronous `DocumentService` with `AsyncSession`, but the sync service expects a regular `Session` object.

## Root Cause
The sync `DocumentService` uses SQLAlchemy's synchronous query syntax (`db.query()`), which is not available on `AsyncSession` objects. AsyncSession requires using the async query syntax with `select()` statements and `await`.

## Solution
1. **Used `AsyncDocumentService`** for all endpoints that use `AsyncSession`
2. **Added missing async methods** to `AsyncDocumentService`:
   - `generate_summary()` - Generate document summary
   - `add_tag()` - Add tag to document
   - `remove_tag()` - Remove tag from document

### Changes Made:

1. **Updated endpoints in `documents.py`**:
   - `/documents/{doc_id}/preview` - Now uses `AsyncDocumentService`
   - `/documents/{doc_id}/converted-pdf` - Now uses `AsyncDocumentService`
   - `/documents/{doc_id}/summary` - Now uses `AsyncDocumentService`
   - `/documents/{doc_id}/tag` (POST) - Now uses `AsyncDocumentService`
   - `/documents/{doc_id}/tag/{tag_name}` (DELETE) - Now uses `AsyncDocumentService`
   - `/documents/{doc_id}/agents` - Now uses `AsyncDocumentService`

2. **Added async methods to `AsyncDocumentService`**:
   ```python
   async def generate_summary(self, db: AsyncSession, doc_id: str) -> Dict[str, str]
   async def add_tag(self, db: AsyncSession, doc_id: str, tag_name: str) -> Dict[str, Any]
   async def remove_tag(self, db: AsyncSession, doc_id: str, tag_name: str) -> Dict[str, Any]
   ```

3. **Fixed attribute access**:
   - Changed from dictionary access (`document.get("tags")`) to attribute access (`document.tags`)
   - This is because `AsyncDocumentService.get_document()` returns a SQLAlchemy model object, not a dictionary

## Key Differences

### Sync (OLD):
```python
document_service = DocumentService(tenant_id=tenant_id, user_id=str(current_user.id))
document = document_service.get_document(db=db, doc_id=doc_id)  # Sync call
```

### Async (NEW):
```python
document_service = AsyncDocumentService(tenant_id=tenant_id, user_id=str(current_user.id))
document = await document_service.get_document(db=db, doc_id=doc_id)  # Async call with await
```

## Best Practices
1. Always use `AsyncDocumentService` with `AsyncSession`
2. Always use `await` when calling async methods
3. Access model attributes directly (e.g., `document.tags`) instead of using dictionary methods
4. Remember that async methods return model objects, not dictionaries

## Testing
The document preview endpoint should now work correctly without the AsyncSession error.