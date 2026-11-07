from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, UploadFile, status

from app.api.dependencies import (
    AdminUser,
    MediaStorageDep,
    OpenLibraryDep,
    PaginationDep,
    SessionDep,
    SettingsDep,
    StaffUser,
    TranslationLookupDep,
    audit_trail,
    require_admin,
)
from app.api.routes.books import LanguageQuery, TagsQuery, tag_slugs
from app.api.routes.challenges import challenge_read
from app.core.exceptions import BadRequestError, ConflictError
from app.models.enums import (
    BookCategory,
    BookStatus,
    OrderStatus,
    PurchaseStatus,
    ReviewStatus,
)
from app.repositories import books as books_repo
from app.repositories import orders as orders_repo
from app.repositories.books import BookFilters
from app.schemas.audit import AuditEventRead, AuditPage
from app.schemas.book import (
    AddCopies,
    BookCreate,
    BookPage,
    BookRead,
    BookSort,
    BookStats,
    BookUpdate,
    BulkBookUpdate,
    BulkResult,
    QualityIssue,
    QualitySummary,
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
from app.schemas.challenge import (
    ChallengeCreate,
    ChallengeParticipant,
    ChallengeRead,
    ChallengeUpdate,
)
from app.schemas.common import error_responses
from app.schemas.library_settings import LibrarySettingsRead, LibrarySettingsUpdate
from app.schemas.order import (
    LateFeeSettlement,
    OrderDueDateUpdate,
    OrderPage,
    OrderRead,
    OrderStatusUpdate,
    ReminderQueued,
)
from app.schemas.pickup import PickupPointCreate, PickupPointRead, PickupPointUpdate
from app.schemas.purchase import PurchaseRequestRead, PurchaseRequestUpdate
from app.schemas.report import DemandRead, ReportSummaryRead
from app.schemas.reservation import UpcomingReservationRead
from app.schemas.review import (
    ModerateReview,
    ModerationReviewPage,
    ModerationReviewRead,
    ReviewRead,
)
from app.schemas.stocktake import (
    Counted,
    CountIn,
    FinishIn,
    ScanIn,
    ScanResultRead,
    StocktakeBrief,
    StocktakeLine,
    StocktakeReportRead,
    UnknownIsbn,
)
from app.schemas.translation import TranslationSuggestion, TranslationSuggestRequest
from app.schemas.user import AdminUserPage, AdminUserUpdate, UserRead
from app.services import (
    audit,
    book_import,
    catalog,
    challenges,
    covers,
    duplicates,
    pickup,
    purchases,
    reports,
    reservations,
    reviews,
    stocktaking,
)
from app.services import books as books_service
from app.services import library_settings as settings_service
from app.services import orders as orders_service
from app.services import users as users_service
from app.services.tag_suggestions import suggest_tags

# Every route below requires library staff (librarian or administrator), checked server-side;
# routes marked ADMIN_ONLY require an administrator. Changes are recorded in the activity log.
router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(audit_trail)],
    responses=error_responses(401, 403),
)


ADMIN_ONLY = [Depends(require_admin)]


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
    quality: Annotated[
        QualityIssue | None,
        Query(description="Titles with this gap (one entry per title, like the catalogue)"),
    ] = None,
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
            quality=quality,
        ),
        sort=sort,
        page=pagination.page,
        page_size=pagination.page_size,
        group_copies=quality is not None,
    )
    return BookPage(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get(
    "/books/quality",
    response_model=QualitySummary,
    description="How many titles lack a cover, description, tags, ISBN or translation, and how "
    "many have machine translations nobody has checked. List them with GET "
    "/admin/books?quality=<issue>.",
)
async def admin_book_quality(session: SessionDep) -> QualitySummary:
    titles, issues = await books_repo.quality_counts(session)
    return QualitySummary(titles=titles, issues=issues)


@router.get(
    "/books/duplicates",
    response_model=list[BookRead],
    responses=error_responses(422),
    description="Titles that look like this book: the same ISBN (hyphens ignored) or the same "
    "title and author (any case). For a warning before adding a duplicate.",
)
async def admin_find_duplicates(
    session: SessionDep,
    isbn: Annotated[str | None, Query(max_length=32)] = None,
    title: Annotated[str | None, Query(max_length=500)] = None,
    author: Annotated[str | None, Query(max_length=300)] = None,
) -> list[BookRead]:
    return await duplicates.find(session, isbn=isbn, title=title, author=author)


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


@router.post(
    "/books/bulk",
    response_model=BulkResult,
    responses=error_responses(400, 404, 422),
    description="One change (status, category, condition, tags to add or remove, or removal "
    "from the catalogue) for every copy of up to 200 titles, all or nothing.",
)
async def admin_bulk_update_books(body: BulkBookUpdate, session: SessionDep) -> BulkResult:
    return await books_service.bulk_update(session, body)


@router.post(
    "/books/{book_id}/cover",
    response_model=BookRead,
    responses=error_responses(400, 404, 413, 422),
    description="Upload a cover (JPEG, PNG or WebP, at most 5 MB) for every copy of the title. "
    "It is stored as WebP in three sizes; cover_url becomes /media/covers/<name>-L.webp.",
)
async def admin_upload_cover(
    book_id: uuid.UUID,
    file: UploadFile,
    session: SessionDep,
    settings: SettingsDep,
    storage: MediaStorageDep,
) -> BookRead:
    data = await file.read(settings.max_cover_bytes + 1)
    return await covers.upload(
        session,
        book_id,
        data,
        storage=storage,
        max_bytes=settings.max_cover_bytes,
    )


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


@router.patch(
    "/users/{user_id}",
    response_model=UserRead,
    responses=error_responses(404, 409, 422),
    dependencies=ADMIN_ONLY,
)
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


@router.patch(
    "/orders/{order_id}/late-fee",
    response_model=OrderRead,
    responses=error_responses(404, 409, 422),
    description="Record that the late fee was paid, or waive it (409 NO_LATE_FEE without one).",
)
async def admin_settle_late_fee(
    order_id: uuid.UUID, body: LateFeeSettlement, session: SessionDep
) -> OrderRead:
    order = await orders_service.settle_late_fee(session, order_id, waive=body.action == "waived")
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
    "/reports/demand",
    response_model=DemandRead,
    responses=error_responses(400, 422),
    description="What readers want: the titles with the most readers waiting and the most "
    '"want to read" saves (right now, with the number of copies), and the tags of the books '
    "lent in the period. Default period: the last 30 days.",
)
async def admin_report_demand(
    session: SessionDep, date_from: date | None = None, date_to: date | None = None
) -> DemandRead:
    start, end = _period(date_from, date_to)
    return DemandRead.model_validate(
        await reports.demand(session, start, end), from_attributes=True
    )


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


@router.patch(
    "/settings",
    response_model=LibrarySettingsRead,
    responses=error_responses(409, 422),
    dependencies=ADMIN_ONLY,
)
async def admin_update_settings(
    body: LibrarySettingsUpdate, user: StaffUser, session: SessionDep
) -> LibrarySettingsRead:
    # Requiring two-step sign-in for staff would otherwise lock this administrator out.
    if body.require_staff_mfa and not user.mfa_enabled:
        raise ConflictError(
            "Turn on two-step sign-in for yourself first", code="MFA_SETUP_REQUIRED_FIRST"
        )
    row = await settings_service.update_library_settings(session, body)
    return LibrarySettingsRead.model_validate(row)


# --- Reviews -----------------------------------------------------------------------------


@router.get(
    "/reviews",
    response_model=ModerationReviewPage,
    responses=error_responses(422),
    description="Reviews by status (default: waiting for moderation), oldest first.",
)
async def admin_list_reviews(
    session: SessionDep,
    pagination: PaginationDep,
    review_status: Annotated[ReviewStatus, Query(alias="status")] = ReviewStatus.PENDING,
) -> ModerationReviewPage:
    items, total = await reviews.for_moderation(
        session, review_status, page=pagination.page, page_size=pagination.page_size
    )
    return ModerationReviewPage(
        items=[
            ModerationReviewRead(
                id=item.review.id,
                rating=item.review.rating,
                text=item.review.text,
                status=item.review.status,
                created_at=item.review.created_at,
                updated_at=item.review.updated_at,
                book_id=item.review.book_id,
                book_title=item.book_title,
                reader_name=item.reader_name,
                reader_email=item.reader_email,
            )
            for item in items
        ],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.patch(
    "/reviews/{review_id}",
    response_model=ReviewRead,
    responses=error_responses(404, 422),
    description="Publish or reject a review.",
)
async def admin_moderate_review(
    review_id: uuid.UUID, body: ModerateReview, session: SessionDep
) -> ReviewRead:
    return ReviewRead.model_validate(await reviews.moderate(session, review_id, body.status))


@router.delete(
    "/reviews/{review_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(404, 422),
)
async def admin_delete_review(review_id: uuid.UUID, session: SessionDep) -> Response:
    await reviews.delete(session, review_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Pickup points ------------------------------------------------------------------------


@router.get("/pickup-points", response_model=list[PickupPointRead])
async def admin_list_pickup_points(session: SessionDep) -> list[PickupPointRead]:
    """Every pickup point, active ones first."""
    return [PickupPointRead.model_validate(p) for p in await pickup.list_all(session)]


@router.post(
    "/pickup-points",
    status_code=status.HTTP_201_CREATED,
    response_model=PickupPointRead,
    responses=error_responses(422),
    dependencies=ADMIN_ONLY,
)
async def admin_create_pickup_point(
    body: PickupPointCreate, session: SessionDep
) -> PickupPointRead:
    return PickupPointRead.model_validate(await pickup.create(session, body))


@router.patch(
    "/pickup-points/{point_id}",
    response_model=PickupPointRead,
    responses=error_responses(404, 422),
    dependencies=ADMIN_ONLY,
)
async def admin_update_pickup_point(
    point_id: uuid.UUID, body: PickupPointUpdate, session: SessionDep
) -> PickupPointRead:
    return PickupPointRead.model_validate(await pickup.update(session, point_id, body))


@router.delete(
    "/pickup-points/{point_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(404, 409, 422),
    dependencies=ADMIN_ONLY,
)
async def admin_delete_pickup_point(point_id: uuid.UUID, session: SessionDep) -> Response:
    """Only points no order used; switch the others off (active = false)."""
    await pickup.delete(session, point_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/reservations", response_model=list[UpcomingReservationRead])
async def admin_upcoming_reservations(session: SessionDep) -> list[UpcomingReservationRead]:
    """Titles readers reserved for a date that has not come yet (or whose copy is late)."""
    return [
        UpcomingReservationRead.model_validate(item, from_attributes=True)
        for item in await reservations.upcoming(session)
    ]


# --- Activity log ------------------------------------------------------------------------


@router.get(
    "/audit",
    response_model=AuditPage,
    responses=error_responses(422),
    dependencies=ADMIN_ONLY,
)
async def admin_audit_log(
    session: SessionDep, pagination: PaginationDep, actor_id: uuid.UUID | None = None
) -> AuditPage:
    """Changes made by staff, newest first (administrators only)."""
    items, total = await audit.list_events(
        session, page=pagination.page, page_size=pagination.page_size, actor_id=actor_id
    )
    return AuditPage(
        items=[AuditEventRead.model_validate(item, from_attributes=True) for item in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


# --- Stocktaking -------------------------------------------------------------------------


def _report(report: stocktaking.StocktakeReport) -> StocktakeReportRead:
    return StocktakeReportRead(
        id=report.id,
        started_at=report.started_at,
        finished_at=report.finished_at,
        marked_missing=report.marked_missing,
        expected=report.expected,
        counted=report.counted,
        lines=[StocktakeLine.model_validate(line, from_attributes=True) for line in report.lines],
        unknown_isbns=[UnknownIsbn(isbn=i, counted=c) for i, c in report.unknown_isbns],
    )


@router.get("/stocktakes", response_model=list[StocktakeBrief])
async def admin_list_stocktakes(session: SessionDep) -> list[StocktakeBrief]:
    """The latest counts, newest first (an open one has no finished_at)."""
    return [StocktakeBrief.model_validate(s) for s in await stocktaking.latest(session)]


@router.post(
    "/stocktakes",
    status_code=status.HTTP_201_CREATED,
    response_model=StocktakeBrief,
    responses=error_responses(409),
)
async def admin_start_stocktake(user: StaffUser, session: SessionDep) -> StocktakeBrief:
    """Start counting the shelves (409 STOCKTAKE_OPEN while another count is open)."""
    return StocktakeBrief.model_validate(await stocktaking.start(session, user))


@router.get(
    "/stocktakes/{stocktake_id}",
    response_model=StocktakeReportRead,
    responses=error_responses(404, 422),
)
async def admin_stocktake_report(
    stocktake_id: uuid.UUID, session: SessionDep
) -> StocktakeReportRead:
    return _report(await stocktaking.report(session, stocktake_id))


@router.post(
    "/stocktakes/{stocktake_id}/scan",
    response_model=ScanResultRead,
    responses=error_responses(400, 404, 409, 422),
)
async def admin_stocktake_scan(
    stocktake_id: uuid.UUID, body: ScanIn, session: SessionDep
) -> ScanResultRead:
    """Count one copy by its ISBN; unknown ISBNs are listed in the report."""
    result = await stocktaking.scan(session, stocktake_id, body.isbn)
    return ScanResultRead.model_validate(result, from_attributes=True)


@router.post(
    "/stocktakes/{stocktake_id}/count",
    response_model=Counted,
    responses=error_responses(404, 409, 422),
)
async def admin_stocktake_count(
    stocktake_id: uuid.UUID, body: CountIn, session: SessionDep
) -> Counted:
    """Count a title by hand (+1), or take one back (-1)."""
    return Counted(counted=await stocktaking.count(session, stocktake_id, body.book_id, body.delta))


@router.post(
    "/stocktakes/{stocktake_id}/finish",
    response_model=StocktakeReportRead,
    responses=error_responses(404, 409, 422),
)
async def admin_finish_stocktake(
    stocktake_id: uuid.UUID, body: FinishIn, session: SessionDep
) -> StocktakeReportRead:
    """Close the count; mark_missing makes copies that were not found "not available"."""
    return _report(await stocktaking.finish(session, stocktake_id, mark_missing=body.mark_missing))


# --- Purchase requests -------------------------------------------------------------------


@router.get("/purchase-requests", response_model=list[PurchaseRequestRead])
async def admin_list_purchase_requests(
    user: StaffUser,
    session: SessionDep,
    status_: Annotated[list[PurchaseStatus] | None, Query(alias="status")] = None,
) -> list[PurchaseRequestRead]:
    """Readers' suggestions, most votes first (default: every status)."""
    found = await purchases.list_requests(session, user, tuple(status_) if status_ else None)
    return [PurchaseRequestRead.model_validate(r, from_attributes=True) for r in found]


@router.patch(
    "/purchase-requests/{request_id}",
    response_model=PurchaseRequestRead,
    responses=error_responses(404, 409, 422),
    description="Mark a suggestion ordered, added or declined, with an optional note for "
    'readers. "added" needs the book in the catalogue (same ISBN, or title and author; 409 '
    "BOOK_NOT_IN_CATALOGUE) and emails everyone who voted.",
)
async def admin_update_purchase_request(
    request_id: uuid.UUID, body: PurchaseRequestUpdate, user: StaffUser, session: SessionDep
) -> PurchaseRequestRead:
    view = await purchases.update(
        session,
        user,
        request_id,
        status=body.status,
        librarian_note=body.librarian_note,
        note_given="librarian_note" in body.model_fields_set,
    )
    return PurchaseRequestRead.model_validate(view, from_attributes=True)


# --- Reading challenges ------------------------------------------------------------------


@router.get("/challenges", response_model=list[ChallengeRead])
async def admin_list_challenges(_: StaffUser, session: SessionDep) -> list[ChallengeRead]:
    """Every challenge, newest first, with how many take part and reached the goal."""
    return [challenge_read(v) for v in await challenges.everything(session)]


@router.post(
    "/challenges",
    response_model=ChallengeRead,
    status_code=201,
    responses=error_responses(422),
)
async def admin_create_challenge(
    body: ChallengeCreate, _: StaffUser, session: SessionDep
) -> ChallengeRead:
    return challenge_read(await challenges.create(session, body.model_dump()))


@router.patch(
    "/challenges/{challenge_id}",
    response_model=ChallengeRead,
    responses=error_responses(404, 409, 422),
)
async def admin_update_challenge(
    challenge_id: uuid.UUID, body: ChallengeUpdate, _: StaffUser, session: SessionDep
) -> ChallengeRead:
    return challenge_read(await challenges.update(session, challenge_id, body.changes()))


@router.delete(
    "/challenges/{challenge_id}",
    status_code=204,
    response_class=Response,
    responses=error_responses(404),
)
async def admin_delete_challenge(
    challenge_id: uuid.UUID, _: StaffUser, session: SessionDep
) -> Response:
    """Remove a challenge and who took part (the reading logs stay)."""
    await challenges.remove(session, challenge_id)
    return Response(status_code=204)


@router.get(
    "/challenges/{challenge_id}/participants",
    response_model=list[ChallengeParticipant],
    responses=error_responses(404),
)
async def admin_challenge_participants(
    challenge_id: uuid.UUID, _: StaffUser, session: SessionDep
) -> list[ChallengeParticipant]:
    """Who takes part and how far they are, most books first (to hand out prizes)."""
    found = await challenges.participants(session, challenge_id)
    return [ChallengeParticipant.model_validate(p, from_attributes=True) for p in found]
