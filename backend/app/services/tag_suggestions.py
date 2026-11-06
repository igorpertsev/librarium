"""Suggest catalogue tags from Open Library subjects.

Open Library lists many free-form subjects per book (93 for The Hobbit, including
"thrushes" and "Arkenstone"). They are matched against keywords per tag and against the
tags' own names; the librarian confirms the suggestions in the form.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tag

MAX_SUGGESTIONS = 6

# Whole-word keywords (English and Russian) per starter tag slug.
KEYWORDS: dict[str, tuple[str, ...]] = {
    "adventure": ("adventure", "adventures", "action & adventure", "приключения"),
    "fantasy": ("fantasy", "fantasy fiction", "фэнтези", "фентези"),
    "science-fiction": ("science fiction", "science-fiction", "sci-fi", "научная фантастика"),
    "detective": ("detective", "detectives", "mystery", "mysteries", "crime", "детектив"),
    "dystopia": ("dystopia", "dystopias", "dystopian", "totalitarianism", "антиутопия"),
    "romance": ("romance", "love stories", "любовный роман"),
    "horror": ("horror", "horror tales", "ужасы"),
    "historical": ("historical fiction", "historical", "историческая проза"),
    "humor": ("humor", "humour", "humorous stories", "юмор"),
    "classics": ("classics", "classic literature", "классика"),
    "poetry": ("poetry", "poems", "поэзия", "стихи"),
    "fairy-tales": ("fairy tales", "folklore", "сказки"),
    "magic": ("magic", "wizards", "witches", "magicians", "волшебство", "магия"),
    "animals": ("animals", "dogs", "cats", "horses", "животные"),
    "school": ("school", "schools", "boarding schools", "школа"),
    "friendship": ("friendship", "friends", "дружба"),
    "family": ("family", "families", "family life", "семья"),
    "war": ("war", "world war", "war stories", "война"),
    "coming-of-age": ("coming of age", "bildungsroman", "teenagers", "взросление"),
    "true-story": ("biography", "autobiography", "memoirs", "true stories", "биография"),
}


def _words(text: str) -> str:
    return " " + re.sub(r"[^\w&]+", " ", text.lower()).strip() + " "


async def suggest_tags(session: AsyncSession, subjects: Iterable[str]) -> list[Tag]:
    texts = [_words(subject) for subject in subjects]
    if not texts:
        return []
    tags = (await session.scalars(select(Tag))).all()
    hits: Counter[str] = Counter()
    for tag in tags:
        phrases = {*KEYWORDS.get(tag.slug, ()), tag.name_en.lower(), tag.name_ru.lower()}
        needles = [_words(phrase) for phrase in phrases if phrase.strip()]
        hits[tag.slug] = sum(1 for text in texts if any(needle in text for needle in needles))
    by_slug = {tag.slug: tag for tag in tags}
    ranked = [slug for slug, count in hits.most_common() if count > 0]
    return [by_slug[slug] for slug in ranked[:MAX_SUGGESTIONS]]
