from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.dependencies import (
    AdminUser,
    OpenLibraryDep,
    PaginationDep,
    SessionDep,
    TranslationLookupDep,
    require_admin,
)
from app.api.routes.books import LanguageQuery, TagsQuery, tag_slugs
from app.core.exceptions import BadRequestError
from app.models.enums import BookCategory, BookStatus, OrderStatus
from app.repositories import orders as orders_repo
from app.repositories.books import BookFilters
from app.schemas.book import (
    AddCopies,
    BookCreate,
    BookPage,
    BookRead,
    BookSort,
    BookStats,
    BookUpdate,
)
from app.schemas.book_import import BookImportRequest, BookImportResult, BookLookup, LookupSeries
from app.schemas.catalog import (
    MergeInto,
    SeriesCreate,
    SeriesRead,
    SeriesUpdate,
    TagBrief,
    TagCreate,
    TagRead,
    TagUpdate,
)
from app.schemas.common import error_responses
from app.schemas.library_settings import LibrarySettingsRead, LibrarySettingsUpdate
from app.schemas.order import (
    OrderDueDateUpdate,
    OrderPage,
    OrderRead,
    OrderStatusUpdate,
    ReminderQueued,
)
from app.schemas.report import ReportSummaryRead
from app.schemas.translation import TranslationSuggestion, TranslationSuggestRequest
from app.schemas.user import AdminUserPage, AdminUserUpdate, UserRead
from app.services import book_import, catalog, reports
from app.services import books as books_service
from app.services import library_settings as settings_service
from app.services import orders as orders_service
from app.services import users as users_service
from app.services.tag_suggestions import suggest_tags

# Every route below requires an authenticated administrator (checked server-side).
router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
    responses=error_responses(401, 403),
)


# --- Books -------------------------------------------------------------------------------


@router.get("/books", response_model=BookPage, responses=error_responses(422))
async def admin_list_books(
    session: SessionDep,
    pagination: PaginationDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    category: BookCategory | None = None,
    book_status: Annotated[BookStatus | None, Query(alias="status")] = None,
    available: bool | None = None,
    include_inactive: bool = False,
    tags: TagsQuery = None,
    series: uuid.UUID | None = None,
    language: LanguageQuery = None,
    sort: BookSort = BookSort.CREATED_AT,
) -> BookPage:
    items, total = await books_service.list_books(
        session,
        BookFilters(
            q=q.strip() if q else None,
            category=category,
            status=book_status,
            available=available,
            include_inactive=include_inactive,
            tags=tag_slugs(tags),
            series_id=series,
            language=language,
        ),
        sort=sort,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return BookPage(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/books/stats", response_model=BookStats)
async def admin_book_stats(session: SessionDep) -> BookStats:
    return await books_service.stats(session)


@router.post(
    "/books",
    status_code=status.HTTP_201_CREATED,
    response_model=BookRead,
    responses=error_responses(422),
)
async def admin_create_book(body: BookCreate, session: SessionDep) -> BookRead:
    return await books_service.create_book(session, body)


@router.post(
    "/books/import",
    response_model=BookImportResult,
    responses=error_responses(422),
    description="Creates books from CSV text (header row; required columns title, author, "
    "category). All or nothing: with any invalid row nothing is created and `errors` lists "
    "them by line. `dry_run=true` only validates. At most 500 books per import.",
)
async def admin_import_books(
    body: BookImportRequest, session: SessionDep, dry_run: bool = False
) -> BookImportResult:
    result = await book_import.import_books(session, body.csv, dry_run=dry_run)
    return BookImportResult.model_validate(result, from_attributes=True)


@router.post(
    "/translations/suggest",
    response_model=TranslationSuggestion,
    responses=error_responses(422),
    description="Title, author and description of a book in another interface language, for "
    "the librarian to review: the official name of the work from Wikidata (found by the ISBN's "
    "Open Library work), the Wikipedia summary (keep source_url for attribution), and machine "
    "translation of what is still missing when it is set up (machine_available). Saves nothing.",
)
async def admin_suggest_translation(
    body: TranslationSuggestRequest, lookup: TranslationLookupDep
) -> TranslationSuggestion:
    return await lookup.suggest(body)


@router.get(
    "/isbn/{isbn}",
    response_model=BookLookup,
    responses=error_responses(404, 502),
    description="Title, author, description, year, language, cover, series and suggested tags "
    "for an ISBN, from Open "
    "Library. 404 ISBN_NOT_FOUND, 502 LOOKUP_UNAVAILABLE.",
)
async def admin_lookup_isbn(
    isbn: str, openlibrary: OpenLibraryDep, session: SessionDep
) -> BookLookup:
    details = await openlibrary.lookup(isbn)
    series = None
    if details.series_name:
        existing = await catalog.find_series(
            session, name=details.series_name, openlibrary_key=details.series_key
        )
        series = LookupSeries(
            id=existing.id if existing else None,
            name=existing.name if existing else details.series_name,
            openlibrary_key=details.series_key,
            position=details.series_position,
        )
    suggested = await suggest_tags(session, details.subjects)
    return BookLookup(
        isbn=details.isbn,
        title=details.title,
        author=details.author,
        description=details.description,
        publication_year=details.publication_year,
        cover_url=details.cover_url,
        language=details.language,
        series=series,
        suggested_tags=[TagBrief.model_validate(tag) for tag in suggested],
    )


@router.post(
    "/books/{book_id}/copies",
    status_code=status.HTTP_201_CREATED,
    response_model=list[BookRead],
    responses=error_responses(404, 422),
    description="Adds copies of a title (same catalogue data, status available). The catalogue "
    "lists the title once and counts its copies.",
)
async def admin_add_copies(
    book_id: uuid.UUID, body: AddCopies, session: SessionDep
) -> list[BookRead]:
    return await books_service.add_copies(session, book_id, body.count)


@router.get("/books/{book_id}", response_model=BookRead, responses=error_responses(404, 422))
async def admin_get_book(book_id: uuid.UUID, session: SessionDep) -> BookRead:
    return await books_service.get_book(session, book_id, include_inactive=True)


@router.patch("/books/{book_id}", response_model=BookRead, responses=error_responses(404, 422))
async def admin_update_book(book_id: uuid.UUID, body: BookUpdate, session: SessionDep) -> BookRead:
    return await books_service.update_book(session, book_id, body)


@router.delete(
    "/books/{book_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(404, 422),
    description="Soft delete: the book disappears from the catalogue and from carts, while "
    "existing orders keep referencing it.",
)
async def admin_delete_book(book_id: uuid.UUID, session: SessionDep) -> Response:
    await books_service.deactivate_book(session, book_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Users -------------------------------------------------------------------------------


@router.get("/users", response_model=AdminUserPage, responses=error_responses(422))
async def admin_list_users(
    session: SessionDep,
    pagination: PaginationDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> AdminUserPage:
    items, total = await users_service.list_users_with_loans(
        session, q=q.strip() if q else None, page=pagination.page, page_size=pagination.page_size
    )
    return AdminUserPage(
        items=items, total=total, page=pagination.page, page_size=pagination.page_size
    )


@router.patch("/users/{user_id}", response_model=UserRead, responses=error_responses(404, 409, 422))
async def admin_update_user(
    user_id: uuid.UUID, body: AdminUserUpdate, admin: AdminUser, session: SessionDep
) -> UserRead:
    user = await users_service.admin_update_user(session, admin, user_id, body)
    return UserRead.model_validate(user)


# --- Orders ------------------------------------------------------------------------------


@router.get("/orders", response_model=OrderPage, responses=error_responses(422))
async def admin_list_orders(
    session: SessionDep,
    pagination: PaginationDep,
    order_status: Annotated[OrderStatus | None, Query(alias="status")] = None,
    user_id: uuid.UUID | None = None,
) -> OrderPage:
    orders, total = await orders_repo.list_orders(
        session,
        user_id=user_id,
        status=order_status,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return OrderPage(
        items=[OrderRead.model_validate(o) for o in orders],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/orders/{order_id}", response_model=OrderRead, responses=error_responses(404, 422))
async def admin_get_order(order_id: uuid.UUID, session: SessionDep) -> OrderRead:
    return OrderRead.model_validate(await orders_service.get_order(session, order_id))


@router.patch(
    "/orders/{order_id}/status",
    response_model=OrderRead,
    responses=error_responses(404, 409, 422),
    description="Allowed transitions: pending → confirmed | cancelled, confirmed → returned. "
    "Returned and cancelled orders release their books.",
)
async def admin_change_order_status(
    order_id: uuid.UUID, body: OrderStatusUpdate, session: SessionDep
) -> OrderRead:
    order = await orders_service.change_status(session, order_id, body.status)
    return OrderRead.model_validate(order)


@router.patch(
    "/orders/{order_id}/due-date",
    response_model=OrderRead,
    responses=error_responses(400, 404, 409, 422),
)
async def admin_change_order_due_date(
    order_id: uuid.UUID, body: OrderDueDateUpdate, session: SessionDep
) -> OrderRead:
    order = await orders_service.change_due_date(session, order_id, body.due_date)
    return OrderRead.model_validate(order)


@router.post(
    "/orders/{order_id}/remind",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ReminderQueued,
    responses=error_responses(404, 409, 422),
    description="Emails the customer a reminder (overdue, or due soon) with the next notifier "
    "run. Only for borrowed orders, at most once per 24 hours (409 REMINDER_RECENTLY_SENT).",
)
async def admin_remind_customer(order_id: uuid.UUID, session: SessionDep) -> ReminderQueued:
    notification = await orders_service.remind_customer(session, order_id)
    return ReminderQueued(kind=notification.kind, queued_at=notification.created_at)


# --- Tags and series ------------------------------------------------------------------------


@router.post(
    "/tags",
    status_code=status.HTTP_201_CREATED,
    response_model=TagRead,
    responses=error_responses(400, 409, 422),
)
async def admin_create_tag(body: TagCreate, session: SessionDep) -> TagRead:
    tag = await catalog.create_tag(session, body)
    return TagRead(id=tag.id, slug=tag.slug, name_en=tag.name_en, name_ru=tag.name_ru)


@router.patch("/tags/{tag_id}", response_model=TagRead, responses=error_responses(404, 409, 422))
async def admin_update_tag(tag_id: uuid.UUID, body: TagUpdate, session: SessionDep) -> TagRead:
    await catalog.update_tag(session, tag_id, body)
    return next(t for t in await catalog.list_tags(session) if t.id == tag_id)


@router.delete(
    "/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(404, 422)
)
async def admin_delete_tag(tag_id: uuid.UUID, session: SessionDep) -> Response:
    """The tag disappears from every book."""
    await catalog.delete_tag(session, tag_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/tags/{tag_id}/merge",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(400, 404, 422),
    description="Books with this tag get the tag `into_id` instead; this tag is deleted.",
)
async def admin_merge_tag(tag_id: uuid.UUID, body: MergeInto, session: SessionDep) -> Response:
    await catalog.merge_tags(session, tag_id, body.into_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/series",
    status_code=status.HTTP_201_CREATED,
    response_model=SeriesRead,
    responses=error_responses(409, 422),
)
async def admin_create_series(body: SeriesCreate, session: SessionDep) -> SeriesRead:
    return await catalog.create_series(session, body)


@router.patch(
    "/series/{series_id}", response_model=SeriesRead, responses=error_responses(404, 409, 422)
)
async def admin_update_series(
    series_id: uuid.UUID, body: SeriesUpdate, session: SessionDep
) -> SeriesRead:
    return await catalog.update_series(session, series_id, body)


@router.delete(
    "/series/{series_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(404, 422),
    description="Deletes the series; its books stay in the catalogue without a series.",
)
async def admin_delete_series(series_id: uuid.UUID, session: SessionDep) -> Response:
    await catalog.delete_series(session, series_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/series/{series_id}/merge",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(400, 404, 422),
    description="Moves the books to the series `into_id` (keeping their volume numbers) and "
    "deletes this series.",
)
async def admin_merge_series(
    series_id: uuid.UUID, body: MergeInto, session: SessionDep
) -> Response:
    await catalog.merge_series(session, series_id, body.into_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Reports -----------------------------------------------------------------------------

MAX_REPORT_DAYS = 366


def _period(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    """Default: the last 30 days up to today (both inclusive)."""
    end = date_to or datetime.now(UTC).date()
    start = date_from or end - timedelta(days=29)
    if start > end or (end - start).days >= MAX_REPORT_DAYS:
        raise BadRequestError(
            f"Choose a period of at most {MAX_REPORT_DAYS} days that ends after it starts",
            code="INVALID_PERIOD",
        )
    return start, end


@router.get(
    "/reports/summary",
    response_model=ReportSummaryRead,
    responses=error_responses(400, 422),
    description="Orders placed, loans (orders handed over) and their books, returns, revenue "
    "(orders handed over), readers and the 10 most borrowed books in the period; overdue "
    "loans right now. Default period: the last 30 days.",
)
async def admin_report_summary(
    session: SessionDep, date_from: date | None = None, date_to: date | None = None
) -> ReportSummaryRead:
    start, end = _period(date_from, date_to)
    report = await reports.summary(session, start, end)
    return ReportSummaryRead.model_validate(report, from_attributes=True)


@router.get(
    "/reports/orders.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}, **error_responses(400, 422)},
    description="Orders placed in the period as CSV (UTF-8 with BOM for spreadsheet apps).",
)
async def admin_report_orders_csv(
    session: SessionDep, date_from: date | None = None, date_to: date | None = None
) -> Response:
    start, end = _period(date_from, date_to)
    content = "\ufeff" + await reports.orders_csv(session, start, end)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="orders-{start}-to-{end}.csv"',
        },
    )


# --- Library settings (batch configuration) --------------------------------------------


@router.get("/settings", response_model=LibrarySettingsRead)
async def admin_get_settings(session: SessionDep) -> LibrarySettingsRead:
    return LibrarySettingsRead.model_validate(await settings_service.get_library_settings(session))


@router.patch("/settings", response_model=LibrarySettingsRead, responses=error_responses(422))
async def admin_update_settings(
    body: LibrarySettingsUpdate, session: SessionDep
) -> LibrarySettingsRead:
    row = await settings_service.update_library_settings(session, body)
    return LibrarySettingsRead.model_validate(row)
