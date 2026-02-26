"""
LADX - Rate Limiter
Tier-based usage tracking and rate limiting.
"""

from datetime import date
from sqlalchemy.orm import Session
from db.models import UsageTracking, Conversation

# Tier configuration
TIER_LIMITS = {
    "free": {
        "messages_per_day": 20,
        "max_conversations": 3,
        "features": ["generate_plc_code", "troubleshoot_plc", "explain_plc_code",
                      "generate_tag_list", "save_code_to_file"],
    },
    "pro": {
        "messages_per_day": 200,
        "max_conversations": None,  # Unlimited
        "features": ["generate_plc_code", "troubleshoot_plc", "explain_plc_code",
                      "generate_tag_list", "save_code_to_file", "convert_plc_code",
                      "send_to_tia_portal", "export_chat"],
    },
    "enterprise": {
        "messages_per_day": None,  # Unlimited
        "max_conversations": None,
        "features": ["generate_plc_code", "troubleshoot_plc", "explain_plc_code",
                      "generate_tag_list", "save_code_to_file", "convert_plc_code",
                      "send_to_tia_portal", "export_chat", "priority_response"],
    },
}


def check_rate_limit(db: Session, user_id: int, tier: str) -> dict:
    """
    Check if user has remaining messages for today.
    Returns: {"allowed": bool, "used": int, "limit": int|None, "remaining": int|None}
    """
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    max_messages = limits["messages_per_day"]

    # Unlimited tier
    if max_messages is None:
        return {"allowed": True, "used": 0, "limit": None, "remaining": None}

    today = date.today()
    usage = db.query(UsageTracking).filter(
        UsageTracking.user_id == user_id,
        UsageTracking.date == today,
    ).first()

    used = usage.messages_count if usage else 0
    remaining = max_messages - used

    return {
        "allowed": remaining > 0,
        "used": used,
        "limit": max_messages,
        "remaining": max(0, remaining),
    }


def increment_usage(db: Session, user_id: int):
    """Increment the message count for today."""
    today = date.today()
    usage = db.query(UsageTracking).filter(
        UsageTracking.user_id == user_id,
        UsageTracking.date == today,
    ).first()

    if not usage:
        usage = UsageTracking(user_id=user_id, date=today, messages_count=0)
        db.add(usage)

    usage.messages_count += 1
    db.commit()


def check_conversation_limit(db: Session, user_id: int, tier: str) -> bool:
    """Check if user can create a new conversation."""
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    max_convos = limits["max_conversations"]

    if max_convos is None:
        return True

    active_count = db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.is_archived == False,
    ).count()

    return active_count < max_convos


def get_allowed_features(tier: str) -> list:
    """Get the list of allowed tool/feature names for a tier."""
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    return limits["features"]
