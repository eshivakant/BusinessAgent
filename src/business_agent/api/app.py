from fastapi import FastAPI

from business_agent.api.routes import router
from business_agent.dependencies import get_app_database, get_memory_store


def create_app() -> FastAPI:
    app = FastAPI(
        title="BusinessAgent",
        version="0.1.0",
        description="Multi-agent business assistant scaffold",
    )
    app.include_router(router)

    @app.on_event("startup")
    def _startup() -> None:
        get_memory_store().ensure_collection()
        app_database = get_app_database()
        if app_database is not None:
            app_database.ensure_schema()

    return app
