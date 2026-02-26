"""
LADX - JWT Token Handler
Encode and decode JWT tokens for user authentication.
"""

from datetime import datetime, timedelta
import jwt
from config import JWT_SECRET, JWT_EXPIRY_HOURS


def create_token(user_id: int, email: str, tier: str) -> str:
    """Create a JWT token for a user."""
    payload = {
        "sub": str(user_id),
        "email": email,
        "tier": tier,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Returns payload dict or raises."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        payload["sub"] = int(payload["sub"])
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")
