from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers.chat import router as chat_router
from app.services.hr_runtime import bootstrap_runtime


@asynccontextmanager
async def lifespan(_: FastAPI):
    bootstrap_runtime()
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(chat_router, prefix=settings.api_prefix)