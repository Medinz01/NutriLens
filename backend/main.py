from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from database import init_db
from routers import extract, verify, rank, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create DB tables if they don't exist
    await init_db()
    yield
    # Shutdown: nothing to clean up yet


app = FastAPI(
    title="NutriLens API",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow Chrome extension to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten to extension origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(extract.router, prefix="/api/v1")
app.include_router(verify.router,  prefix="/api/v1")
app.include_router(rank.router,    prefix="/api/v1")
app.include_router(admin.router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}