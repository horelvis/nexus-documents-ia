# Async Database Migration Guide

This guide shows how to migrate from synchronous to asynchronous database operations in our FastAPI application.

## Key Changes

### 1. Imports

**Before:**
```python
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.api.dependencies import get_current_user, get_current_active_user
```

**After:**
```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.db.async_database import get_async_db
from app.api.async_dependencies import get_current_user_async, get_current_active_user_async
```

### 2. Dependencies

**Before:**
```python
db: Session = Depends(get_db)
current_user: User = Depends(get_current_user)
```

**After:**
```python
db: AsyncSession = Depends(get_async_db)
current_user: User = Depends(get_current_user_async)
```

### 3. Query Patterns

#### Simple Query
**Before:**
```python
user = db.query(User).filter(User.id == user_id).first()
```

**After:**
```python
result = await db.execute(select(User).filter(User.id == user_id))
user = result.scalar_one_or_none()
```

#### Query with Multiple Results
**Before:**
```python
documents = db.query(Document).filter(Document.tenant_id == tenant_id).all()
```

**After:**
```python
result = await db.execute(select(Document).filter(Document.tenant_id == tenant_id))
documents = result.scalars().all()
```

#### Query with Joins/Eager Loading
**Before:**
```python
document = db.query(Document).options(joinedload(Document.tags)).filter(Document.id == doc_id).first()
```

**After:**
```python
result = await db.execute(
    select(Document)
    .options(selectinload(Document.tags))
    .filter(Document.id == doc_id)
)
document = result.scalar_one_or_none()
```

#### Count Query
**Before:**
```python
count = db.query(Document).filter(Document.tenant_id == tenant_id).count()
```

**After:**
```python
result = await db.execute(
    select(func.count(Document.id))
    .filter(Document.tenant_id == tenant_id)
)
count = result.scalar()
```

#### Complex Query with Pagination
**Before:**
```python
query = db.query(Document).filter(Document.tenant_id == tenant_id)
total = query.count()
documents = query.offset(offset).limit(limit).all()
```

**After:**
```python
# Base query
stmt = select(Document).filter(Document.tenant_id == tenant_id)

# Count total
count_stmt = select(func.count()).select_from(stmt.subquery())
total_result = await db.execute(count_stmt)
total = total_result.scalar()

# Get paginated results
paginated_stmt = stmt.offset(offset).limit(limit)
result = await db.execute(paginated_stmt)
documents = result.scalars().all()
```

### 4. Transactions

**Before:**
```python
db.add(new_document)
db.commit()
db.refresh(new_document)
```

**After:**
```python
db.add(new_document)
await db.commit()
await db.refresh(new_document)
```

### 5. Rollback

**Before:**
```python
try:
    # operations
    db.commit()
except Exception:
    db.rollback()
    raise
```

**After:**
```python
try:
    # operations
    await db.commit()
except Exception:
    await db.rollback()
    raise
```

### 6. Raw SQL

**Before:**
```python
result = db.execute(text("SELECT * FROM users WHERE email = :email"), {"email": email})
user = result.first()
```

**After:**
```python
from sqlalchemy import text
result = await db.execute(text("SELECT * FROM users WHERE email = :email"), {"email": email})
user = result.first()
```

## Service Classes

When migrating service classes:

1. Create async versions (e.g., `AsyncDocumentService`)
2. Use factory pattern for initialization if needed
3. Convert all database operations to async
4. Update all method signatures to `async def`

## Files to Migrate

Priority order:
1. ✅ `document_categorization.py` - DONE
2. 🔄 `documents.py` - IN PROGRESS
3. `document_shares.py`
4. `auth.py`
5. `chat.py`
6. `admin.py`
7. `tenants.py`
8. `stripe.py`
9. `signatures.py`
10. `webhooks.py`

## Testing

After migration:
1. Test with Docker: `cd backend/docker && ./start-dev.sh`
2. Check database connections don't block
3. Verify improved performance under load
4. Ensure all error handling works correctly

## Common Pitfalls

1. **Don't mix sync and async sessions** - Use either all sync or all async
2. **Don't forget await** - All database operations need await
3. **Update all imports** - Check for any missed Session imports
4. **Test error paths** - Ensure rollbacks work correctly
5. **Check service dependencies** - Some services may need async versions