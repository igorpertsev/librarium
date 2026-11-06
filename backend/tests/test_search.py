from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import update

from app.models import Book
from tests.conftest import API, CreateBook


async def _titles(client: AsyncClient, q: str, sort: str = "title") -> list[str]:
    response = await client.get(f"{API}/books", params={"q": q, "sort": sort})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return [book["title"] for book in body["items"]]


async def test_search_forgives_typos_and_word_order(
    client: AsyncClient, create_book: CreateBook
) -> None:
    await create_book("The Hobbit", author="J.R.R. Tolkien")
    await create_book("Nineteen Eighty-Four", author="George Orwell")
    await create_book("Harry Potter and the Sorcerer's Stone", author="J.K. Rowling")
    await create_book("Мастер и Маргарита", author="Михаил Булгаков")

    assert await _titles(client, "hobit") == ["The Hobbit"]
    assert await _titles(client, "orwel") == ["Nineteen Eighty-Four"]
    assert await _titles(client, "potter harry") == ["Harry Potter and the Sorcerer's Stone"]
    assert await _titles(client, "маргарита") == ["Мастер и Маргарита"]
    assert await _titles(client, "zzzzqqq") == []


async def test_search_finds_words_in_the_description(
    app: FastAPI, client: AsyncClient, create_book: CreateBook
) -> None:
    book_id = await create_book("The Hobbit")
    await create_book("Emma")
    async with app.state.db.sessionmaker() as session:
        await session.execute(
            update(Book)
            .where(Book.title == "The Hobbit")
            .values(description="A dragon guards a treasure under the Lonely Mountain.")
        )
        await session.commit()
    assert book_id
    assert await _titles(client, "dragon treasure") == ["The Hobbit"]
    assert await _titles(client, "dragon -treasure") == []  # web-search style exclusion


async def test_isbn_search_ignores_hyphens(client: AsyncClient, create_book: CreateBook) -> None:
    await create_book("The Hobbit", isbn="9780547928227")
    await create_book("Emma", isbn="9780141439587")
    assert await _titles(client, "978-0-547-92822-7") == ["The Hobbit"]
    assert await _titles(client, "0547928227") == ["The Hobbit"]


async def test_best_match_comes_first(client: AsyncClient, create_book: CreateBook) -> None:
    await create_book("Children of Dune", author="Frank Herbert")
    await create_book("Dune", author="Frank Herbert")
    await create_book("A Dunes Field Guide", author="Ann Author")
    titles = await _titles(client, "dune", sort="relevance")
    assert titles[0] == "Dune"
    assert set(titles) == {"Dune", "Children of Dune", "A Dunes Field Guide"}
    # Without a search text "relevance" means alphabetical.
    response = await client.get(f"{API}/books", params={"sort": "relevance"})
    assert [b["title"] for b in response.json()["items"]] == sorted(
        ["Children of Dune", "Dune", "A Dunes Field Guide"], key=str.lower
    )
