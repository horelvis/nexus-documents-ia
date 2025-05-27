import pytest
from sqlalchemy import create_engine, Column, ForeignKey, String, Uuid # Corrected Uuid import
from sqlalchemy.orm import sessionmaker, Session, relationship
from app.db.base_class import Base 
from app.db.models import User, UserImage, Role, Permission, Plan, Price, Subscription, Tenant
import uuid
from datetime import datetime

# pytest fixture for an in-memory SQLite database session
@pytest.fixture(scope="function")
def db_session():
    engine = create_engine("sqlite:///:memory:")
    # Base.metadata.create_all(engine) will try to create all tables, including those
    # that might have PostgreSQL-specific types not fully compatible with SQLite out-of-the-box
    # without type decorators (e.g. sqlalchemy.dialects.postgresql.JSONB).
    # For unit tests focusing on model instantiation and basic relationships,
    # this is usually fine if specific PG types are not strictly enforced or tested at this level.
    # If PG-specific functions or constraints are needed, a test PG database would be better.
    
    # For SQLite, UUIDs are often stored as strings. Ensure models are compatible or use TypeDecorator.
    # The models provided use sqlalchemy.dialects.postgresql.UUID which might need handling for SQLite.
    # A simple way is to override such columns for testing with SQLite if direct compatibility is an issue.
    # However, SQLAlchemy often handles basic UUID as string in SQLite. Let's proceed and adapt if errors occur.

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)

# --- Test Data Factory Functions (Optional but helpful) ---
def create_dummy_tenant(db_session: Session, tenant_id: uuid.UUID = None) -> Tenant:
    tenant_id = tenant_id or uuid.uuid4()
    tenant = db_session.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        tenant = Tenant(
            id=tenant_id,
            name=f"Test Tenant {tenant_id}",
            bucket_name=f"testbucket-{tenant_id}"
        )
        db_session.add(tenant)
        db_session.commit()
        db_session.refresh(tenant)
    return tenant

def create_dummy_user(db_session: Session, tenant_id: uuid.UUID, clerk_id: Optional[str] = None, email_prefix: str = "testuser") -> User:
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"{email_prefix}{user_id}@example.com",
        hashed_password="fakepassword",
        full_name="Test User",
        tenant_id=tenant_id,
        clerk_user_id=clerk_id or f"clerk_{user_id}"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user

# --- Test Cases ---

def test_create_tenant(db_session: Session):
    tenant_id = uuid.uuid4()
    tenant = Tenant(
        id=tenant_id,
        name="Main Corp Tenant",
        description="Main corporate tenant for testing",
        bucket_name="maincorp-bucket",
        is_active=True,
        settings={"feature_x": True}
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)

    retrieved_tenant = db_session.query(Tenant).filter(Tenant.id == tenant_id).first()
    assert retrieved_tenant is not None
    assert retrieved_tenant.name == "Main Corp Tenant"
    assert retrieved_tenant.bucket_name == "maincorp-bucket"
    assert retrieved_tenant.settings == {"feature_x": True}

def test_create_user_with_clerk_id(db_session: Session):
    tenant = create_dummy_tenant(db_session)
    clerk_id_value = "user_clerktest123abc"
    email_val = "clerk_user@example.com"
    user_id = uuid.uuid4()

    user = User(
        id=user_id,
        email=email_val,
        hashed_password="securepassword123",
        full_name="Clerk Test User",
        tenant_id=tenant.id,
        clerk_user_id=clerk_id_value,
        is_active=True,
        is_superuser=False
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    retrieved_user = db_session.query(User).filter(User.email == email_val).first()
    assert retrieved_user is not None
    assert retrieved_user.clerk_user_id == clerk_id_value
    assert retrieved_user.email == email_val
    assert retrieved_user.tenant_id == tenant.id

def test_create_user_image(db_session: Session):
    tenant = create_dummy_tenant(db_session)
    user = create_dummy_user(db_session, tenant_id=tenant.id)
    
    image_id = uuid.uuid4()
    image_data = b"someimagedata"
    user_image = UserImage(
        id=image_id,
        user_id=user.id,
        alt_text="Profile picture",
        content_type="image/png",
        blob=image_data
    )
    db_session.add(user_image)
    db_session.commit()
    db_session.refresh(user_image)

    # Test relationship from UserImage to User
    assert user_image.user is not None
    assert user_image.user.id == user.id
    
    # Test relationship from User to UserImage
    db_session.refresh(user) # Refresh user to load the relationship
    assert user.image is not None
    assert user.image.id == image_id
    assert user.image.blob == image_data

def test_role_and_permission_creation_and_linking(db_session: Session):
    # Create Permissions
    perm_read_doc = Permission(id=uuid.uuid4(), entity="document", action="read", access="tenant")
    perm_edit_doc = Permission(id=uuid.uuid4(), entity="document", action="edit", access="own")
    db_session.add_all([perm_read_doc, perm_edit_doc])
    db_session.commit()

    # Create Role and link Permissions
    role_editor = Role(id=uuid.uuid4(), name="Editor", description="Can edit documents")
    role_editor.permissions.append(perm_read_doc)
    role_editor.permissions.append(perm_edit_doc)
    db_session.add(role_editor)
    db_session.commit()
    db_session.refresh(role_editor)

    assert len(role_editor.permissions) == 2
    assert perm_read_doc in role_editor.permissions
    
    # Create User and link Role
    tenant = create_dummy_tenant(db_session)
    user_editor = create_dummy_user(db_session, tenant_id=tenant.id, email_prefix="editoruser")
    user_editor.roles.append(role_editor)
    db_session.commit()
    db_session.refresh(user_editor)
    
    assert len(user_editor.roles) == 1
    assert role_editor in user_editor.roles
    
    # Check reverse relationship (Role to User)
    db_session.refresh(role_editor)
    assert user_editor in role_editor.users

def test_plan_price_subscription_creation_and_linking(db_session: Session):
    # Create Plan
    plan_premium = Plan(id=uuid.uuid4(), name="Premium", description="Premium Plan Features")
    db_session.add(plan_premium)
    db_session.commit()

    # Create Price for Plan
    price_monthly = Price(
        id=uuid.uuid4(),
        plan_id=plan_premium.id,
        amount=2999, # in cents
        currency="usd",
        interval="month"
    )
    db_session.add(price_monthly)
    db_session.commit()
    db_session.refresh(plan_premium) # Refresh to see prices relationship if defined as backpopulating

    # Optionally check plan.prices if relationship is set up to populate it
    # assert price_monthly in plan_premium.prices 

    # Create User
    tenant = create_dummy_tenant(db_session)
    subscriber_user = create_dummy_user(db_session, tenant_id=tenant.id, email_prefix="subscriber")

    # Create Subscription
    subscription = Subscription(
        id=uuid.uuid4(),
        user_id=subscriber_user.id,
        plan_id=plan_premium.id,
        price_id=price_monthly.id,
        status="active",
        current_period_start=datetime.utcnow(),
        current_period_end=datetime.utcnow() + timedelta(days=30) # Corrected timedelta import
    )
    db_session.add(subscription)
    db_session.commit()
    db_session.refresh(subscription)

    # Test relationships
    assert subscription.user is not None
    assert subscription.user.id == subscriber_user.id
    assert subscription.plan is not None
    assert subscription.plan.id == plan_premium.id
    assert subscription.price is not None
    assert subscription.price.id == price_monthly.id

    # Test reverse relationships (from User, Plan, Price to Subscription)
    db_session.refresh(subscriber_user)
    db_session.refresh(plan_premium)
    db_session.refresh(price_monthly)

    assert subscriber_user.subscription is not None
    assert subscriber_user.subscription.id == subscription.id
    
    # To test plan.subscriptions and price.subscriptions, ensure these relationships
    # are defined in the models (e.g., Plan.subscriptions = relationship("Subscription", back_populates="plan"))
    # For now, we assume they are from the previous model definitions.
    assert subscription in plan_premium.subscriptions
    assert subscription in price_monthly.subscriptions

# Placeholder for future tests or more complex scenarios
def test_example_placeholder():
    assert True
