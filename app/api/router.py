from fastapi import APIRouter

from app.api.routes.authors import router as authors_router
from app.api.routes.comments import router as comments_router
from app.api.routes.crawl import router as crawl_router
from app.api.routes.health import router as health_router
from app.api.routes.posts import router as posts_router
from app.api.routes.tasks import router as tasks_router

api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(posts_router)
api_router.include_router(authors_router)
api_router.include_router(tasks_router)
api_router.include_router(comments_router)
api_router.include_router(crawl_router)
