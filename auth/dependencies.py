"""
LADX - Auth Dependencies
FastAPI dependency for extracting and validating JWT tokens.
"""

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from auth.jwt_handler import decode_token
from db.database import get_db
from db.models import User

security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Extract and validate user from JWT token."""
    # Debug: check what we received
    auth_header = request.headers.get("Authorization", "")
    print(f"[AUTH DEBUG] Auth header present: {bool(auth_header)}, starts with Bearer: {auth_header.startswith('Bearer ') if auth_header else False}")

    if not credentials:
        print(f"[AUTH DEBUG] No credentials extracted by HTTPBearer")
        print(f"[AUTH DEBUG] Raw Authorization header: '{auth_header[:50]}...' " if len(auth_header) > 50 else f"[AUTH DEBUG] Raw Authorization header: '{auth_header}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated - no token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    print(f"[AUTH DEBUG] Token received (first 20 chars): {token[:20]}...")

    try:
        payload = decode_token(token)
        print(f"[AUTH DEBUG] Token decoded OK - user_id={payload.get('sub')}")
    except ValueError as e:
        print(f"[AUTH DEBUG] Token decode FAILED: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user or not user.is_active:
        print(f"[AUTH DEBUG] User not found or inactive for id={payload.get('sub')}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    print(f"[AUTH DEBUG] Auth SUCCESS - user={user.email}")
    return user
