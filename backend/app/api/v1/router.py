from fastapi import APIRouter
from .books import router as books_router
from .bundles import router as bundles_router
from .search import router as search_router
from .admin import router as admin_router
from .auth import router as auth_router
from .purchases import router as purchases_router
from .webhooks import router as webhooks_router
from .categories import router as categories_router
from .authors import router as authors_router
from .reviews import router as reviews_router
from .wishlist import router as wishlist_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(books_router)
api_router.include_router(bundles_router)
api_router.include_router(search_router)
api_router.include_router(admin_router)
api_router.include_router(auth_router)
api_router.include_router(purchases_router)
api_router.include_router(webhooks_router)
api_router.include_router(categories_router)
api_router.include_router(authors_router)
api_router.include_router(reviews_router)
api_router.include_router(wishlist_router)