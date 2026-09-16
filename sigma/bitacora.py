"""Middleware ASGI que registra en la base cada llamada que llega a la API (/api) o al MCP (/mcp).
Es lo que la pantalla «Integraciones» muestra en vivo: quién llamó, qué pidió, cuándo. Para el MCP se
decodifica el método JSON-RPC y, si es tools/call, la herramienta y sus argumentos."""
from __future__ import annotations

import json
import time

from . import db

CANALES = {"/mcp": "mcp", "/api": "api"}
IGNORAR = ("/api/integraciones",)  # el sondeo del frontend no se registra a sí mismo


class BitacoraMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        canal = next((c for p, c in CANALES.items() if path.startswith(p)), None)
        if not canal or path.startswith(IGNORAR):
            return await self.app(scope, receive, send)

        cuerpo, mensajes = b"", []
        while True:
            m = await receive()
            mensajes.append(m)
            cuerpo += m.get("body", b"")
            if not m.get("more_body"):
                break
        hdr = {k.decode().lower(): v.decode(errors="replace") for k, v in scope.get("headers", [])}
        if hdr.get("x-sigma-ui") == "1":  # el propio frontend: no es una integración
            it0 = iter(mensajes)

            async def replay0():
                try:
                    return next(it0)
                except StopIteration:
                    return await receive()
            return await self.app(scope, replay0, send)
        origen = (hdr.get("x-forwarded-for", "").split(",")[0].strip()
                  or (scope.get("client") or ("?", 0))[0])
        agente = hdr.get("user-agent", "")
        metodo, detalle = f"{scope['method']} {path}", ""
        if canal == "mcp" and cuerpo:
            try:
                j = json.loads(cuerpo)
                metodo = j.get("method") or ("respuesta" if "result" in j else metodo)
                if metodo == "tools/call":
                    p = j.get("params", {})
                    detalle = json.dumps({"tool": p.get("name"), "arguments": p.get("arguments")}, ensure_ascii=False)
                elif metodo == "initialize":
                    p = j.get("params", {})
                    detalle = json.dumps({"protocolVersion": p.get("protocolVersion"),
                                          "client": (p.get("clientInfo") or {}).get("name")}, ensure_ascii=False)
            except Exception:
                detalle = "(cuerpo no JSON)"
        elif canal == "api":
            qs = scope.get("query_string", b"").decode()
            detalle = qs

        it = iter(mensajes)

        async def replay():
            try:
                return next(it)
            except StopIteration:
                return await receive()

        estado = {"code": 0}
        t0 = time.perf_counter()

        async def send_wrap(msg):
            if msg["type"] == "http.response.start":
                estado["code"] = msg["status"]
            await send(msg)

        try:
            await self.app(scope, replay, send_wrap)
        finally:
            if metodo != "notifications/initialized":
                db.registrar_integracion(canal, origen, metodo, detalle, estado["code"],
                                         int((time.perf_counter() - t0) * 1000), agente)
