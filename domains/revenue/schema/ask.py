"""Ask screen replies (follow-up discussion on the analysis result;
internal-docs §4).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AskReply(BaseModel):
    answer: str = Field(
        default="",
        description=(
            "The reply, at most 110 words, plain everyday words, second person, from the user's own facts"
        ),
    )
    follow_ups: list[str] = Field(
        default_factory=list,
        description="0 to 3 short questions the user could ask next (each under 12 words), or an empty list",
    )
