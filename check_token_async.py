
import asyncio
from uuid import UUID
from app.db.async_database import AsyncSessionLocal
from app.db.models import GoogleDriveToken

async def check_token():
    async with AsyncSessionLocal() as db:
        user_id_uuid = UUID('cd8bb336-5653-43fa-b84e-ee1627540d5a')
        token = await db.get(GoogleDriveToken, user_id_uuid)
        print(f'Token found: {token is not None}')

if __name__ == '__main__':
    asyncio.run(check_token())
