"""SIGMA Mantención · Minera Cerro Sauce — sistema de gestión de mantención (ficticio, para capacitación).

Un solo proceso con tres caras sobre la misma base de datos:
  /          frontend (carpeta frontend/)
  /api/...   API REST (la lee el conector sincronizado de Copilot y el frontend)
  /mcp       servidor MCP (lo llama el conector federado de Copilot)
Toda llamada a /api y /mcp queda en la bitácora de integraciones que el frontend muestra en vivo.

Arranque local:  uvicorn sigma.main:app --port 8000 --reload
Variables:       SIGMA_URL_PUBLICA, SIGMA_HOSTS (hosts públicos permitidos, separados por coma),
                 PERMITIR_ESCRITURA=1, DEMO_KEY, y las de m365_sync.py.
"""
from __future__ import annotations

import contextlib
import os
import pathlib

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.transport_security import TransportSecuritySettings

from . import api, db
from .bitacora import BitacoraMiddleware
from .mcp_server import mcp

FRONTEND = pathlib.Path(__file__).resolve().parents[1] / "frontend"


def _hosts_permitidos() -> list[str]:
    hosts = ["127.0.0.1:*", "localhost:*"]
    hosts += [h.strip() for h in os.environ.get("SIGMA_HOSTS", "").split(",") if h.strip()]
    if os.environ.get("RENDER_EXTERNAL_HOSTNAME"):  # Render lo inyecta solo
        hosts.append(os.environ["RENDER_EXTERNAL_HOSTNAME"])
    return hosts


hosts = _hosts_permitidos()
mcp_app = mcp.streamable_http_app(
    streamable_http_path="/", json_response=False, stateless_http=False,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=hosts,
        allowed_origins=[f"https://{h}" for h in hosts] + [f"http://{h}" for h in hosts]),
)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    db.inicializar()
    print("SIGMA Mantención · hosts permitidos para MCP:", hosts, flush=True)
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="SIGMA Mantención · Minera Cerro Sauce", version="0.1", lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json")
app.include_router(api.router)
app.mount("/mcp", mcp_app)


@app.get("/ot/{id}")
def ficha_ot(id: str):
    """URL «humana» de una OT: es la que Copilot cita. El frontend la abre en el detalle."""
    return RedirectResponse(url=f"/?ot={id}")


@app.get("/salud")
def salud():
    return {"ok": True, "app": "SIGMA Mantención", "ordenes": len(db.listar_ordenes(limite=10000))}


if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")

class _RutaMcp:
    """`/mcp` y `/mcp/` son lo mismo: el mount de Starlette solo resuelve la segunda."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") == "/mcp":
            scope = dict(scope, path="/mcp/", raw_path=b"/mcp/")
        await self.app(scope, receive, send)


app = BitacoraMiddleware(_RutaMcp(app))  # type: ignore[assignment]
