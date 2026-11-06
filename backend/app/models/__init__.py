"""ORM models. Importing this package registers every table on ``Base.metadata``."""

from app.models.base import Base
from app.models.book import Book
from app.models.cart import Cart, CartItem
from app.models.library_settings import LibrarySettings
from app.models.notification import Notification
from app.models.order import Order, OrderItem
from app.models.reading_list import ReadingListEntry
from app.models.refresh_token import RefreshToken
from app.models.series import Series
from app.models.tag import Tag, book_tags
from app.models.translation import BookTranslation
from app.models.user import User
from app.models.waitlist import WaitlistEntry

__all__ = [
    "Base",
    "Book",
    "BookTranslation",
    "Cart",
    "CartItem",
    "LibrarySettings",
    "Notification",
    "Order",
    "OrderItem",
    "ReadingListEntry",
    "RefreshToken",
    "Series",
    "Tag",
    "User",
    "WaitlistEntry",
    "book_tags",
]
