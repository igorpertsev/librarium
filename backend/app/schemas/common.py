"""Shared schema building blocks."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApiModel(BaseModel):
    """Base for response models (built from ORM objects).

    ``json_schema_serialization_defaults_required`` marks every response field as required
    in OpenAPI, so generated TypeScript types do not make server-filled fields optional.
    """

    model_config = ConfigDict(
        from_attributes=True, json_schema_serialization_defaults_required=True
    )


class RequestModel(BaseModel):
    """Base for request bodies: unknown fields are rejected (e.g. a client-sent ``price``).

    Whitespace is trimmed per field type (see ``schemas.types``), never globally, so that
    passwords reach the hasher exactly as typed.
    """

    model_config = ConfigDict(extra="forbid")


class PatchModel(RequestModel):
    """PATCH body base that distinguishes *absent* fields from explicit ``null``.

    Use ``model_dump(exclude_unset=True)`` to get only the fields the client sent.
    Fields listed in ``non_nullable_fields`` may be omitted but not set to ``null``.
    """

    non_nullable_fields: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def _reject_null_for_required_columns(self) -> PatchModel:
        nulls = sorted(
            name
            for name in self.model_fields_set & self.non_nullable_fields
            if getattr(self, name) is None
        )
        if nulls:
            raise ValueError(f"Fields cannot be null: {', '.join(nulls)}")
        return self

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class ErrorBody(BaseModel):
    code: str = Field(examples=["BOOK_UNAVAILABLE"])
    message: str = Field(examples=["One or more books are unavailable"])
    details: dict[str, Any] | None = Field(
        default=None, examples=[{"book_ids": ["0b6c0e2e-6f1b-4b8e-9a43-2d2f6c1d9b11"]}]
    )


class ErrorResponse(BaseModel):
    error: ErrorBody


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses=`` helper so generated clients know the error shape."""
    return {code: {"model": ErrorResponse} for code in status_codes}
