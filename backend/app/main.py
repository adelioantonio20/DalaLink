from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import admin, auth, corporate, driver, info, mobility, owner
from app.core.config import now_luanda, settings
from app.core.security import decode_access_token
from app.db.seed import seed_database
from app.db.seed_info import seed_mobility_info_data
from app.db.session import Base, SessionLocal, engine
from app.models import *  # noqa: F401, F403 - register all models with Base.metadata
from app.services.realtime_hub import realtime_hub


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_database(db)
        seed_mobility_info_data(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Plataforma de Inteligência e Intermediação de Informação para Mobilidade Urbana em Luanda, Angola. "
        "Disponibiliza indicadores de procura e oferta de táxis por via e paragem em tempo real."
    ),
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.CORS_ORIGINS.split(",")] if settings.CORS_ORIGINS else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active MVP Routers (Information Intermediation & Intelligence)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(info.router, prefix="/api/v1")

# Preserved Legacy Finance / Ridesharing Routers (disabled in MVP per Section 3 & 14)
if settings.ENABLE_LEGACY_FINANCE_MODULES:
    app.include_router(mobility.router, prefix="/api/v1")
    app.include_router(driver.router, prefix="/api/v1")
    app.include_router(corporate.router, prefix="/api/v1")
    app.include_router(owner.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")


@app.get("/api/v1/health")
def health_check():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "mode": "MOBILITY_INFORMATION_MVP",
        "legacy_finance_enabled": settings.ENABLE_LEGACY_FINANCE_MODULES,
        "timezone": settings.TIMEZONE,
        "server_time_luanda": now_luanda().isoformat(),
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(default="")):
    payload = decode_access_token(token) if token else None
    if not payload or "sub" not in payload:
        await websocket.close(code=4401)
        return

    user_id = payload["sub"]
    role = payload.get("role", "PASSENGER")
    channels = [f"user:{user_id}", f"role:{role}"]
    await realtime_hub.connect(websocket, channels)
    try:
        await websocket.send_json({"event": "CONNECTED", "data": {"user_id": user_id, "role": role}})
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"event": "PONG", "data": {"ts": now_luanda().isoformat()}})
    except WebSocketDisconnect:
        realtime_hub.disconnect(websocket)
    except Exception:
        realtime_hub.disconnect(websocket)
