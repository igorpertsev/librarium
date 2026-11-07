from __future__ import annotations

from tests.conftest import API, ApiUser


async def test_each_copy_has_its_own_condition_and_damaged_copies_show_in_data_quality(
    admin: ApiUser,
) -> None:
    created = await admin.post(
        f"{API}/admin/books",
        json={"title": "Dune", "author": "F. Herbert", "category": "fiction", "condition": "new"},
    )
    assert created.status_code == 201, created.text
    dune = created.json()
    assert (dune["condition"], dune["condition_note"]) == ("new", None)
    copies = (await admin.post(f"{API}/admin/books/{dune['id']}/copies", json={"count": 1})).json()
    assert copies[0]["condition"] == "good"  # new copies start in good condition

    # Noting damage on one copy leaves the other copy alone (it is not shared by the title).
    damaged = await admin.patch(
        f"{API}/admin/books/{dune['id']}",
        json={"condition": "damaged", "condition_note": "  Torn cover  "},
    )
    assert (damaged.json()["condition"], damaged.json()["condition_note"]) == (
        "damaged",
        "Torn cover",
    )
    other = (await admin.get(f"{API}/admin/books/{copies[0]['id']}")).json()
    assert other["condition"] == "good"

    quality = (await admin.get(f"{API}/admin/books/quality")).json()
    assert quality["issues"]["damaged"] == 1
    listed = (await admin.get(f"{API}/admin/books", params={"quality": "damaged"})).json()
    assert [b["title"] for b in listed["items"]] == ["Dune"]

    cleared = await admin.patch(f"{API}/admin/books/{dune['id']}", json={"condition_note": ""})
    assert cleared.json()["condition_note"] is None
    refused = await admin.patch(f"{API}/admin/books/{dune['id']}", json={"condition": None})
    assert refused.status_code == 422
