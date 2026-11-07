"""ORM models. Importing this package registers every table on ``Base.metadata``."""

from app.models.audit import AuditEvent
from app.models.base import Base
from app.models.book import Book
from app.models.cart import Cart, CartItem
from app.models.challenge import Challenge, ChallengeEntry
from app.models.child import ChildProfile
from app.models.collection import Collection, CollectionBook
from app.models.hold import BookHold
from app.models.identity import UserIdentity
from app.models.library_settings import LibrarySettings
from app.models.notification import Notification
from app.models.order import Order, OrderItem
from app.models.passkey import Passkey
from app.models.pickup import PickupPoint
from app.models.purchase import PurchaseRequest, PurchaseVote
from app.models.push import PushSubscription
from app.models.reading_list import ReadingListEntry
from app.models.reading_log import ReadingLogEntry
from app.models.refresh_token import RefreshToken
from app.models.reservation import AdvanceReservation
from app.models.review import Review
from app.models.series import Series
from app.models.stocktake import Stocktake, StocktakeCount
from app.models.tag import Tag, book_tags
from app.models.translation import BookTranslation
from app.models.user import User
from app.models.waitlist import WaitlistEntry

__all__ = [
    "AdvanceReservation",
    "AuditEvent",
    "Base",
    "Book",
    "BookHold",
    "BookTranslation",
    "Cart",
    "CartItem",
    "Challenge",
    "ChallengeEntry",
    "ChildProfile",
    "Collection",
    "CollectionBook",
    "LibrarySettings",
    "Notification",
    "Order",
    "OrderItem",
    "Passkey",
    "PickupPoint",
    "PurchaseRequest",
    "PurchaseVote",
    "PushSubscription",
    "ReadingListEntry",
    "ReadingLogEntry",
    "RefreshToken",
    "Review",
    "Series",
    "Stocktake",
    "StocktakeCount",
    "Tag",
    "User",
    "UserIdentity",
    "WaitlistEntry",
    "book_tags",
]
