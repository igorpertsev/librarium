from fastapi import APIRouter, Depends

from app.api.dependencies import storable_parameters
from app.api.prefix import API_PREFIX
from app.api.routes import (
    admin,
    auth,
    books,
    calendar,
    cart,
    catalog,
    health,
    library,
    orders,
    purchases,
    reading_list,
    reviews,
    share,
    telegram,
    users,
    waitlist,
)

__all__ = ["API_PREFIX", "api_router"]

api_router = APIRouter(prefix=API_PREFIX, dependencies=[Depends(storable_parameters)])
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(calendar.router)
api_router.include_router(telegram.router)
api_router.include_router(books.router)
api_router.include_router(catalog.router)
api_router.include_router(cart.router)
api_router.include_router(orders.router)
api_router.include_router(library.router)
api_router.include_router(waitlist.router)
api_router.include_router(reading_list.router)
api_router.include_router(share.router)
api_router.include_router(reviews.router)
api_router.include_router(purchases.router)
api_router.include_router(admin.router)
