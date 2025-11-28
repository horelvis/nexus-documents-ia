import sys
import os
from uuid import UUID
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.core.config import settings
from app.db.models import GoogleDriveToken, User

def check_google_tokens():
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Check if table exists
        try:
            result = db.execute(text("SELECT count(*) FROM google_drive_tokens"))
            print(f"Total Google tokens: {result.scalar()}")
        except Exception as e:
            print(f"Error querying google_drive_tokens table: {e}")
            return

        # Check specific user
        user_id = "cd8bb336-5653-43fa-b84e-ee1627540d5a"
        try:
            token = db.query(GoogleDriveToken).filter(GoogleDriveToken.user_id == UUID(user_id)).first()
            if token:
                print(f"Token found for user {user_id}")
                print(f"  Email: {token.google_email}")
                print(f"  Expiry: {token.token_expiry}")
            else:
                print(f"No token found for user {user_id}")
        except Exception as e:
             print(f"Error querying user token: {e}")

    finally:
        db.close()

if __name__ == "__main__":
    check_google_tokens()
