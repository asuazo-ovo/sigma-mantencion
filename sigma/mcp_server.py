"""Servidor MCP de SIGMA Mantención (SDK mcp 2.x). Es la cara que usa el conector federado de Copilot.

Patrón que Copilot acepta (verificado el 16-sep-2026): herramientas tipo search / fetch / list con título,
anotación readOnlyHint y salida en texto JSON. Copilot filtra las herramientas sin readOnlyHint cuando
el servidor se usa como conector; solo un agente con acciones puede llamarlas. La de escritura se
registra únicamente con PERMITIR_ESCRITURA=1 y, si se llama, cambia de verdad el estado en la base."""
from __future__ import annotations

import json
import os

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from . import db

URL_PUBLICA = os.environ.get("SIGMA_URL_PUBLICA", "http://127.0.0.1:8000")
SOLO_LECTURA = dict(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

mcp = MCPServer(
    "SIGMA Mantención · Cerro Sauce",
    instructions=(
        "Maintenance management system (CMMS) of Minera Cerro Sauce. Contains the work orders (OT) of the plant "
        "equipment: area, equipment, type, date, hours, contractor, status and spare-parts cost, plus downtime "
        "hour totals by area and month. Use it for any question about work orders, maintenance interventions, "
        "pending spare parts or downtime as seen by Maintenance. / Sistema de gestión de mantención de Minera "
        "Cerro Sauce: órdenes de trabajo, intervenciones, repuestos pendientes y detenciones. Datos ficticios."
    ),
)


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _texto(o: dict) -> str:
    partes = [
        f"Orden de trabajo {o['id']} · {o['equipo']} · {o['tipo']} · estado: {o['estado']}.",
        f"Área: {o['area']}. Fecha: {o['fecha'][:10]}. Turno: {o.get('turno') or '-'}. Duración: {o['horas']} horas. "
        f"Contratista: {o['contratista']}. Causa: {o.get('causa') or '-'}.",
        f"Costo de repuestos: {o['costo_repuestos_clp']:,} CLP.".replace(",", "."),
        f"Descripción: {o['descripcion']}",
    ]
    if o.get("nota"):
        partes.append(f"Nota: {o['nota']}")
    partes.append("Generó registro de detención en la planilla de Operaciones." if o["detencion_registrada"]
                  else "No generó registro de detención en la planilla de Operaciones.")
    return " ".join(partes)


def _resultado(o: dict) -> dict:
    return {
        "id": o["id"], "title": f"{o['id']} · {o['equipo']} · {o['tipo']}", "text": _texto(o),
        "url": f"{URL_PUBLICA}/ot/{o['id']}",
        "metadata": {k: o.get(k) for k in ("area", "equipo", "tipo", "estado", "turno", "causa", "horas",
                                            "contratista", "detencion_registrada", "costo_repuestos_clp")}
        | {"fecha": o["fecha"][:10]},
    }


@mcp.tool(name="search", title="Search work orders (SIGMA Mantención)",
          annotations=ToolAnnotations(title="Search work orders", **SOLO_LECTURA), structured_output=False)
def search(query: str) -> str:
    """Search work orders (órdenes de trabajo) of the Cerro Sauce maintenance system by free text: area
    (e.g. Chancado), equipment (e.g. CV-03), type, status (e.g. pendiente de repuesto), contractor, cause,
    month (e.g. 2026-06) or work order id. Returns a JSON list with id, title, text and url. Use fetch for
    the full record."""
    palabras = [p for p in query.lower().split() if len(p) > 2]
    res = [o for o in db.listar_ordenes(limite=5000)
           if all(p in " ".join(str(v) for v in o.values()).lower() for p in palabras)]
    return _json({"query": query, "count": len(res), "results": [_resultado(o) for o in res[:50]]})


@mcp.tool(name="fetch", title="Fetch one work order (SIGMA Mantención)",
          annotations=ToolAnnotations(title="Fetch work order", **SOLO_LECTURA), structured_output=False)
def fetch(id: str) -> str:
    """Fetch the full record of one work order by its id, e.g. OT-2026-0167 (OT20260167 also accepted),
    including its change history."""
    o = db.obtener_orden(id)
    if not o:
        return _json({"error": f"Work order {id} not found"})
    r = _resultado(o)
    r["metadata"] |= {"descripcion": o["descripcion"], "nota": o.get("nota", ""), "historial": o.get("historial", [])}
    return _json(r)


@mcp.tool(name="list_work_orders", title="List work orders with hour totals (SIGMA Mantención)",
          annotations=ToolAnnotations(title="List work orders", **SOLO_LECTURA), structured_output=False)
def list_work_orders(area: str = "", month: str = "", status: str = "", type: str = "", equipment: str = "",
                     contractor: str = "") -> str:
    """List work orders filtered by area (e.g. Chancado), month YYYY-MM (e.g. 2026-06), status (Cerrada,
    Pendiente de repuesto), type (Correctiva, Correctiva menor, Preventiva), equipment (e.g. CV-03) and/or
    contractor. Returns JSON with the matching orders and total hours, split between orders that generated
    a downtime record in Operations and those that did not. Best tool for 'how many hours in Chancado in
    June 2026'."""
    sel = db.listar_ordenes(area=area, mes=month, estado=status, tipo=type, equipo=equipment, contratista=contractor)
    con = [o for o in sel if o["detencion_registrada"]]
    sin = [o for o in sel if not o["detencion_registrada"]]
    return _json({
        "filter": {"area": area, "month": month, "status": status, "type": type, "equipment": equipment, "contractor": contractor},
        "count": len(sel), "total_hours": round(sum(o["horas"] for o in sel), 2),
        "hours_with_downtime_record": round(sum(o["horas"] for o in con), 2),
        "hours_without_downtime_record": round(sum(o["horas"] for o in sin), 2),
        "results": [_resultado(o) for o in sel[:100]],
    })


@mcp.tool(name="downtime_summary", title="Downtime hours by area and month (SIGMA Mantención)",
          annotations=ToolAnnotations(title="Downtime summary", **SOLO_LECTURA), structured_output=False)
def downtime_summary(month_from: str = "2026-01", month_to: str = "2026-07") -> str:
    """Registered downtime hours per area and month between two YYYY-MM months, with event counts, whether the
    area exceeded the 40 h/month alert threshold (procedure OP-PR-014 §6) and the estimated cost using the
    standard cost per hour of each area. Best tool for 'which areas were over the threshold' questions."""
    return _json({"threshold_hours": 40, "rows": db.resumen_horas(month_from, month_to), "cost_per_hour": db.costos_hora()})


def _registrar_escritura() -> None:
    @mcp.tool(name="close_work_order", title="Close a work order (SIGMA Mantención) — writes",
              annotations=ToolAnnotations(title="Close work order", readOnlyHint=False, destructiveHint=True,
                                          idempotentHint=True, openWorldHint=False), structured_output=False)
    def close_work_order(id: str, comentario: str = "") -> str:
        """Close a work order: sets its status to Cerrada and records the change with a comment. Modifies data."""
        r = db.cambiar_estado(id, "Cerrada", actor="Copilot (MCP)", comentario=comentario)
        return _json(r)


if os.environ.get("PERMITIR_ESCRITURA") == "1":
    _registrar_escritura()
