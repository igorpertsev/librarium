from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints

from app.models.enums import TranslationSource, UiLanguage
from app.schemas.common import ApiModel, RequestModel
from app.schemas.types import Description, Isbn, LanguageCode, OptionalHttpUrlStr, Title

TranslatedAuthor = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]


class BookTranslationRead(ApiModel):
    language: UiLanguage
    title: str
    author: str
    description: str
    title_source: TranslationSource
    description_source: TranslationSource
    source_url: str | None = Field(
        description="Wikipedia article the description comes from (CC BY-SA attribution)"
    )


class BookTranslationIn(RequestModel):
    language: UiLanguage
    title: Title
    author: TranslatedAuthor = ""
    description: Description = ""
    title_source: TranslationSource = TranslationSource.MANUAL
    description_source: TranslationSource = TranslationSource.MANUAL
    source_url: OptionalHttpUrlStr = None


def _one_per_language(items: list[BookTranslationIn]) -> list[BookTranslationIn]:
    languages = [item.language for item in items]
    if len(set(languages)) != len(languages):
        raise ValueError("At most one translation per language")
    return items


Translations = Annotated[
    list[BookTranslationIn],
    Field(max_length=len(UiLanguage)),
    AfterValidator(_one_per_language),
]


class TranslationSuggestRequest(RequestModel):
    """The book as it is in the form; nothing is saved."""

    target: UiLanguage = Field(description="Language to find the title and description in")
    title: Title
    author: TranslatedAuthor = ""
    description: Description = ""
    isbn: Isbn = None
    language: LanguageCode = Field(None, description="Language of the book itself")
    machine: bool = Field(
        True, description="Machine-translate what Wikidata and Wikipedia do not have"
    )


class TranslationSuggestion(ApiModel):
    """What was found; empty fields were not found anywhere."""

    language: UiLanguage
    title: str | None
    author: str | None
    description: str | None
    title_source: TranslationSource | None
    description_source: TranslationSource | None
    source_url: str | None
    wikidata_id: str | None = Field(description="The Wikidata item of the work, e.g. Q183883")
    machine_available: bool = Field(description="Whether machine translation is set up")
