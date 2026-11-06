from fastapi import APIRouter

from app.api.routes import (
    admin,
    auth,
    books,
    cart,
    catalog,
    health,
    library,
    orders,
    reading_list,
    reviews,
    share,
    users,
    waitlist,
)

API_PREFIX = "/api/v1"

api_router = APIRouter(prefix=API_PREFIX)
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(books.router)
api_router.include_router(catalog.router)
api_router.include_router(cart.router)
api_router.include_router(orders.router)
api_router.include_router(library.router)
api_router.include_router(waitlist.router)
api_router.include_router(reading_list.router)
api_router.include_router(share.router)
api_router.include_router(reviews.router)
api_router.include_router(admin.router)
