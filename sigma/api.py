"""API REST de SIGMA Mantención. Es la cara que lee el conector sincronizado (y el frontend)."""
from __future__ import annotations

import os

from fastapi import APIRouter, Header, HTTPException

from . import db, m365_sync

router = APIRouter(prefix="/api")


def _clave_ok(x_demo_key: str | None) -> None:
    esperada = os.environ.get("DEMO_KEY", "")
    if esperada and x_demo_key != esperada:
        raise HTTPException(status_code=401, detail="Falta la clave de demo (cabecera X-Demo-Key).")


@router.get("/ordenes")
def ordenes(area: str = "", mes: str = "", estado: str = "", tipo: str = "", equipo: str = "",
            contratista: str = "", q: str = "", limite: int = 500):
    filas = db.listar_ordenes(area, mes, estado, tipo, equipo, contratista, q, limite)
    return {"count": len(filas), "ordenes": filas}


@router.get("/ordenes/{id}")
def orden(id: str):
    o = db.obtener_orden(id)
    if not o:
        raise HTTPException(status_code=404, detail=f"No existe la orden de trabajo {id}")
    return o


@router.get("/resumen")
def resumen(desde: str = "2025-08", hasta: str = "2026-07"):
    return {"umbral_horas": 40, "filas": db.resumen_horas(desde, hasta), "costos_hora": db.costos_hora()}


@router.get("/pendientes")
def pendientes():
    return {"pendientes": db.pendientes_repuesto()}


@router.get("/equipos/{equipo}")
def equipo(equipo: str):
    filas = db.listar_ordenes(equipo=equipo, limite=1000)
    return {"equipo": equipo, "count": len(filas), "horas_totales": round(sum(o["horas"] for o in filas), 2), "ordenes": filas}


@router.get("/integraciones")
def integraciones(desde: int = 0, limite: int = 200):
    return {"eventos": db.listar_integraciones(desde, limite)}


@router.post("/admin/restablecer")
def restablecer(x_demo_key: str | None = Header(default=None)):
    _clave_ok(x_demo_key)
    return db.restablecer()


@router.post("/admin/sincronizar-m365")
def sincronizar(x_demo_key: str | None = Header(default=None)):
    """Empuja las órdenes al índice de Microsoft 365 (conector sincronizado). Requiere las credenciales de la
    app de Entra en variables de entorno; sin ellas responde 503 y explica qué falta."""
    _clave_ok(x_demo_key)
    return m365_sync.sincronizar()


@router.get("/admin/estado-m365")
def estado_m365():
    return m365_sync.estado()
