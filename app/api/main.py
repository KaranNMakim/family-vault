"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import get_settings
from app.logs import configure_logging


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    api = FastAPI(title="family-vault (DEMO — synthetic data only)", version=__version__)
    api.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @api.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__, "llm_mode": settings.llm_mode, "demo": True}

    return api


app = create_app()
