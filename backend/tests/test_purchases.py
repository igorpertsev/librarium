from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy import select

from app.models import Notification
from app.models.enums import NotificationKind
from app.services.notifications import deliver_pending
from tests.conftest import API, ApiUser, RegisterUser
from tests.test_holds import FakeSender

URL = f"{API}/purchase-requests"


async def test_readers_suggest_books_and_vote_for_them(
    customer: ApiUser, other_customer: ApiUser, register_user: RegisterUser, admin: ApiUser
) -> None:
    made = await customer.post(
        URL, json={"title": "Project Hail Mary", "author": "Andy Weir", "isbn": "978-0-593-13520-4"}
    )
    assert made.status_code == 201, made.text
    request = made.json()["request"]
    assert (request["votes"], request["voted"], request["mine"]) == (1, True, True)

    # The same book again (by title and author, any case) is a vote, not a new suggestion.
    same = await other_customer.post(
        URL, json={"title": "project hail mary", "author": "ANDY WEIR"}
    )
    assert (same.status_code, same.json()["created"]) == (200, False)
    assert same.json()["request"]["id"] == request["id"]
    third = await register_user()
    await third.post(URL, json={"title": "Dune", "author": "Frank Herbert"})
    await third.put(f"{URL}/{request['id']}/vote")
    await third.put(f"{URL}/{request['id']}/vote")  # voting twice counts once

    listed = (await customer.get(URL)).json()
    assert [(r["title"], r["votes"]) for r in listed] == [("Project Hail Mary", 3), ("Dune", 1)]
    withdrawn = (await third.delete(f"{URL}/{request['id']}/vote")).json()
    assert (withdrawn["votes"], withdrawn["voted"]) == (2, False)

    # Books already in the catalogue cannot be suggested.
    await admin.post(
        f"{API}/admin/books", json={"title": "Emma", "author": "Jane Austen", "category": "fiction"}
    )
    there = await customer.post(URL, json={"title": "Emma", "author": "Jane Austen"})
    assert there.json()["error"]["code"] == "ALREADY_IN_CATALOGUE"


async def test_librarians_mark_suggestions_and_voters_hear_when_the_book_arrives(
    app: FastAPI, customer: ApiUser, other_customer: ApiUser, admin: ApiUser
) -> None:
    request = (
        await customer.post(URL, json={"title": "Piranesi", "author": "Susanna Clarke"})
    ).json()["request"]
    await other_customer.put(f"{URL}/{request['id']}/vote")
    admin_url = f"{API}/admin/purchase-requests/{request['id']}"

    ordered = await admin.patch(admin_url, json={"status": "ordered", "librarian_note": "Due May"})
    assert (ordered.json()["status"], ordered.json()["librarian_note"]) == ("ordered", "Due May")
    early = await admin.patch(admin_url, json={"status": "added"})
    assert early.json()["error"]["code"] == "BOOK_NOT_IN_CATALOGUE"

    book = (
        await admin.post(
            f"{API}/admin/books",
            json={"title": "Piranesi", "author": "Susanna Clarke", "category": "fiction"},
        )
    ).json()
    added = (await admin.patch(admin_url, json={"status": "added"})).json()
    assert (added["status"], added["book_id"]) == ("added", book["id"])
    # Added suggestions leave the readers' list; everyone who voted is told.
    assert (await customer.get(URL)).json() == []
    async with app.state.db.sessionmaker() as session:
        kinds = (
            await session.scalars(
                select(Notification.kind).where(
                    Notification.kind == NotificationKind.PURCHASE_ADDED
                )
            )
        ).all()
        assert len(kinds) == 2
        send = FakeSender()
        await deliver_pending(session, app.state.settings, send)
    subjects = [m["Subject"] for m in send.messages if "is in the library" in m["Subject"]]
    assert len(subjects) == 2
    news = (await customer.get(f"{API}/users/me/notifications")).json()
    assert news["items"][0]["kind"] == "purchase_added"
