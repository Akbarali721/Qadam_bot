from typing import TypedDict

from sqlalchemy.orm import Session

from db.relationship_crud import count_relationship_funnel_event


class RelationshipFunnelStats(TypedDict):
    invite_created: int
    partner_deeplink_opened: int
    partner_start_clicked: int
    partner_test_started: int
    partner_test_completed: int
    result_ready: int
    user1_result_opened: int
    conversion_deeplink_per_invite: float
    conversion_start_per_deeplink: float
    conversion_completed_per_started: float


def _rate(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((part / total) * 100, 1)


def get_relationship_funnel_stats(db: Session) -> RelationshipFunnelStats:
    invite_created = count_relationship_funnel_event(db, "invite_created")
    partner_deeplink_opened = count_relationship_funnel_event(db, "partner_deeplink_opened")
    partner_start_clicked = count_relationship_funnel_event(db, "partner_start_clicked")
    partner_test_started = count_relationship_funnel_event(db, "partner_test_started")
    partner_test_completed = count_relationship_funnel_event(db, "partner_test_completed")
    result_ready = count_relationship_funnel_event(db, "result_ready")
    user1_result_opened = count_relationship_funnel_event(db, "user1_result_opened")

    return {
        "invite_created": invite_created,
        "partner_deeplink_opened": partner_deeplink_opened,
        "partner_start_clicked": partner_start_clicked,
        "partner_test_started": partner_test_started,
        "partner_test_completed": partner_test_completed,
        "result_ready": result_ready,
        "user1_result_opened": user1_result_opened,
        "conversion_deeplink_per_invite": _rate(partner_deeplink_opened, invite_created),
        "conversion_start_per_deeplink": _rate(partner_start_clicked, partner_deeplink_opened),
        "conversion_completed_per_started": _rate(partner_test_completed, partner_test_started),
    }
