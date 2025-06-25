# SQLAlchemy Lazy Loading Fix Summary

## Issue
The application was experiencing a `MissingGreenlet` error when trying to access the `tags` relationship on Document objects in async contexts. This happens when SQLAlchemy tries to lazy load a relationship that wasn't eagerly loaded during the initial query.

## Root Cause
When returning Document objects from API endpoints, the `tags` relationship was being accessed without proper eager loading in some cases, particularly:
1. After creating a new document in `upload_document`
2. When using incorrect initialization of `AsyncDocumentService` in tag endpoints

## Fixes Applied

### 1. Fixed `upload_document` method in `async_document_service.py`
**File**: `/backend/app/services/async_document_service.py`
**Line**: ~279-294

**Change**: After committing the new document with tags, the method now reloads the document with proper eager loading:
```python
# Reload the document with proper eager loading for tags
stmt = select(Document).filter(
    Document.id == doc.id
).options(
    selectinload(Document.tags),
    selectinload(Document.creator)
)
result = await db.execute(stmt)
doc = result.scalar_one()
```

### 2. Fixed tag endpoints in `documents.py`
**File**: `/backend/app/api/v1/documents.py`
**Lines**: ~372-373 and ~388-389

**Change**: Fixed incorrect initialization of `AsyncDocumentService`:
- Before: `document_service = AsyncDocumentService(tenant_id=tenant_id, user_id=str(current_user.id))`
- After: `document_service = await AsyncDocumentService.create(tenant_id=tenant_id, user_id=str(current_user.id))`

## Verified Working Correctly
The following methods already had proper eager loading and didn't need changes:
- `get_documents()` - has `selectinload(Document.tags)` on line 132
- `get_document()` - has `selectinload(Document.tags)` on line 380
- `add_tag()` - has `selectinload(Document.tags)` on line 587
- `remove_tag()` - has `selectinload(Document.tags)` on line 634

## Testing
To verify the fix works:
1. Upload a new document with tags - should not throw lazy loading error
2. Get document details - should return tags properly
3. Add/remove tags from a document - should work without errors

## Prevention
To prevent similar issues in the future:
1. Always use `selectinload()` or `joinedload()` for relationships when querying in async contexts
2. Always use `AsyncDocumentService.create()` factory method instead of direct initialization
3. When returning ORM objects from services, ensure all needed relationships are eagerly loaded