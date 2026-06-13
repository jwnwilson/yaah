import os

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from interactors.api.envelope import err, ok
from interactors.api.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="yaah")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)  # alembic replaces this once the schema stabilises
    app.state.settings = settings
    app.state.session_factory = make_session_factory(engine)

    # Starlette base class so unknown-route 404s are enveloped too
    # (fastapi.HTTPException subclasses StarletteHTTPException)
    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=err(str(exc.detail)))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content=err(str(exc.errors())))

    from pydantic import ValidationError

    from domain.errors import IntegrityConflict, InvalidFilter, RecordNotFound
    from domain.transitions import InvalidTransition

    def _envelope_handler(status_code: int):
        async def handler(_: Request, exc: Exception) -> JSONResponse:
            return JSONResponse(status_code=status_code, content=err(str(exc)))

        return handler

    app.add_exception_handler(RecordNotFound, _envelope_handler(404))
    app.add_exception_handler(IntegrityConflict, _envelope_handler(409))
    app.add_exception_handler(InvalidTransition, _envelope_handler(409))
    app.add_exception_handler(InvalidFilter, _envelope_handler(400))
    app.add_exception_handler(ValidationError, _envelope_handler(422))

    @app.get("/health")
    def health() -> dict:
        return ok({"status": "ok"})

    from interactors.api.routes import (
        agents,
        capabilities,
        notifications,
        projects,
        runs,
        teams,
        work_items,
    )

    app.include_router(projects.router)
    app.include_router(work_items.router)
    app.include_router(teams.router)
    app.include_router(runs.router)
    app.include_router(capabilities.skills_router)
    app.include_router(capabilities.mcp_router)
    app.include_router(capabilities.secrets_router)
    app.include_router(agents.router)
    app.include_router(notifications.router)

    ui_dist = os.path.join(os.path.dirname(__file__), "..", "..", "..", "ui", "dist")
    if os.path.isdir(ui_dist):
        app.mount("/", StaticFiles(directory=ui_dist, html=True), name="ui")

    return app
