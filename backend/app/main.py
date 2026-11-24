from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.api import contracts, findings, runs
from app.config import get_settings
from app.db import mark_stale_runs_failed
from app.services import Services, build_services


def create_app(services: Services | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        svc = services or build_services(get_settings())
        app.state.services = svc
        with Session(svc.engine) as session:
            mark_stale_runs_failed(session)
        try:
            yield
        finally:
            if svc.close is not None:
                svc.close()

    app = FastAPI(title="ClauseLens", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(contracts.router)
    app.include_router(runs.router)
    app.include_router(findings.router)
    return app


app = create_app()
