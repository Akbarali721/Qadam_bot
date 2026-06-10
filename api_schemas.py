from pydantic import BaseModel, Field


class RelationshipFunnelEventCreate(BaseModel):
    invite_token: str = Field(..., min_length=1, max_length=128)
    event_name: str = Field(..., min_length=1, max_length=64)
    telegram_id: int | None = Field(default=None, ge=1)
    role: str | None = Field(default=None, max_length=16)
    metadata: dict | None = None


class RelationshipPartnerCompletedPayload(BaseModel):
    invite_token: str = Field(..., min_length=1, max_length=128)
    user1_telegram_id: int = Field(..., ge=1)
    partner_telegram_id: int | None = Field(default=None, ge=1)
