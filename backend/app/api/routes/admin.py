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
    require_admin,
)
from app.core.exceptions import BadRequestError
from app.models.enums import BookCategory, BookStatus, OrderStatus
from app.repositories import orders as orders_repo
from app.repositories.books import BookFilters
from app.schemas.book import BookCreate, BookPage, BookRead, BookSort, BookStats, BookUpdate
from app.schemas.book_import import BookImportRequest, BookImportResult, BookLookup
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
from app.schemas.user import AdminUserPage, AdminUserUpdate, UserRead
from app.services import book_import, reports
from app.services import books as books_service
from app.services import library_settings as settings_service
from app.services import orders as orders_service
from app.services import users as users_service

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


@router.get(
    "/isbn/{isbn}",
    response_model=BookLookup,
    responses=error_responses(404, 502),
    description="Title, author, description, year, language and cover for an ISBN, from Open "
    "Library. 404 ISBN_NOT_FOUND, 502 LOOKUP_UNAVAILABLE.",
)
async def admin_lookup_isbn(isbn: str, openlibrary: OpenLibraryDep) -> BookLookup:
    details = await openlibrary.lookup(isbn)
    return BookLookup.model_validate(details, from_attributes=True)


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
