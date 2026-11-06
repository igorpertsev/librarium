from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.models.enums import ReviewStatus
from app.schemas.common import ApiModel, Page, RequestModel

ReviewText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class PublicReviewRead(ApiModel):
    id: uuid.UUID
    author_name: str = Field(description='First name and initial, e.g. "Dana R."')
    rating: int
    text: str
    created_at: datetime


class ReviewSummaryRead(ApiModel):
    average: float | None = Field(description="Average published rating, one decimal")
    count: int = Field(description="Published ratings")
    reviews: list[PublicReviewRead] = Field(description="Published reviews with text, newest first")


class ReviewRead(ApiModel):
    id: uuid.UUID
    rating: int
    text: str
    status: ReviewStatus
    created_at: datetime
    updated_at: datetime


class MyReviewRead(ApiModel):
    can_review: bool = Field(description="The reader has borrowed this title")
    review: ReviewRead | None


class ReviewWrite(RequestModel):
    rating: Annotated[int, Field(ge=1, le=5)]
    text: ReviewText = ""


class ModerationReviewRead(ReviewRead):
    book_id: uuid.UUID
    book_title: str
    reader_name: str
    reader_email: str


class ModerationReviewPage(Page[ModerationReviewRead]):
    pass


class ModerateReview(RequestModel):
    status: Literal[ReviewStatus.PUBLISHED, ReviewStatus.REJECTED]
