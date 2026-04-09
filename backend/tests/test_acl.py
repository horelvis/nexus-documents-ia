"""Tests for the role-based ACL helpers in app.core.auth.acl."""
import pytest
from sqlalchemy import create_engine, Column, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from app.core.auth.acl import filter_visible_to_user, require_role
from app.core.auth.base import UserProfile

Base = declarative_base()


class FakeDoc(Base):
    __tablename__ = "fake_docs_for_acl_test"
    id = Column(String, primary_key=True)
    roles = Column(ARRAY(String), nullable=False)


@pytest.fixture
def db_session():
    # In-memory SQLite for tests; ARRAY is only Postgres, so we use a
    # session-level mock instead. The query construction is what we test —
    # not the SQL execution against a real DB. Plan 5 covers integration
    # tests against real Postgres.
    engine = create_engine("sqlite://")
    Session = sessionmaker(bind=engine)
    return Session()


def make_user(roles):
    """Helper: create a UserProfile with the given role list."""
    return UserProfile(
        sub="test-user-id",
        email="test@example.com",
        name="Test User",
        roles=roles,
    )


def test_filter_visible_to_user_includes_everyone():
    """A user with no relevant roles still sees EVERYONE-tagged docs."""
    user = make_user(roles=[])
    from app.core.auth.acl import build_role_filter_clause
    clause = build_role_filter_clause(user)
    # Inline literal binds so the "EVERYONE" sentinel shows up in the
    # compiled SQL string instead of being hidden behind :roles_1.
    compiled = str(clause.compile(compile_kwargs={"literal_binds": True}))
    assert "EVERYONE" in compiled


def test_filter_visible_to_user_includes_user_roles():
    """A user with role SALES sees docs tagged SALES."""
    user = make_user(roles=["SALES"])
    from app.core.auth.acl import build_role_filter_clause
    clause = build_role_filter_clause(user)
    compiled = str(clause.compile(compile_kwargs={"literal_binds": True}))
    compiled_upper = compiled.upper()
    # The EVERYONE branch is always present (the OR clause)
    assert "EVERYONE" in compiled_upper
    # The user's role must appear in the overlap operand
    assert "SALES" in compiled_upper
    # The array-overlap operator (&&) or "OVERLAP" name must appear
    assert "&&" in compiled or "OVERLAP" in compiled_upper


def test_require_role_passes_when_user_has_role():
    """require_role(*roles) returns the user when at least one role matches."""
    user = make_user(roles=["LEGAL", "SALES"])
    dep = require_role("LEGAL")
    result = dep(user=user)
    assert result is user


def test_require_role_passes_when_user_has_any_of_multiple():
    """require_role passes if the user has ANY of the listed roles."""
    user = make_user(roles=["SALES"])
    dep = require_role("LEGAL", "SALES", "HR")
    result = dep(user=user)
    assert result is user


def test_require_role_raises_when_user_lacks_role():
    """require_role raises 403 if the user has none of the listed roles."""
    user = make_user(roles=["HR"])
    dep = require_role("LEGAL", "ADMIN")
    with pytest.raises(HTTPException) as exc_info:
        dep(user=user)
    assert exc_info.value.status_code == 403
    assert "forbidden" in exc_info.value.detail.lower()


def test_require_role_raises_when_user_has_no_roles():
    """A user with empty roles list cannot pass any require_role check."""
    user = make_user(roles=[])
    dep = require_role("LEGAL")
    with pytest.raises(HTTPException) as exc_info:
        dep(user=user)
    assert exc_info.value.status_code == 403


def test_require_role_admin_bypass_not_implicit():
    """ADMIN role does NOT implicitly grant other roles. Each check is explicit."""
    user = make_user(roles=["ADMIN"])
    dep = require_role("LEGAL")
    with pytest.raises(HTTPException):
        dep(user=user)
    # If you want admin to bypass, the endpoint must list ADMIN in require_role.
