"""Conector sincronizado de Microsoft 365 Copilot, desde el servidor: crea la conexión y el esquema si no
existen y empuja cada orden de trabajo como ítem del índice (Microsoft Graph, permisos de APLICACIÓN).

Variables de entorno (nunca en el código ni en el repo):
  TENANT_ID, CLIENT_ID, CLIENT_SECRET   — la app de Entra con ExternalConnection/ExternalItem.ReadWrite.OwnedBy
  M365_CONNECTION_ID                    — id de la conexión (3-32 alfanuméricos), p. ej. sigmamantencion
Es el mismo flujo del script conector_cerrosauce.py de la cápsula TI-1, ahora disparado desde un botón."""
from __future__ import annotations

import os
import time

import requests

from . import db

GRAPH = "https://graph.microsoft.com/v1.0"


def _cfg() -> dict:
    return {k: os.environ.get(k, "") for k in ("TENANT_ID", "CLIENT_ID", "CLIENT_SECRET", "M365_CONNECTION_ID")}


def estado() -> dict:
    c = _cfg()
    faltan = [k for k, v in c.items() if not v]
    import json as _json
    progreso = _meta("sync_progreso")
    return {"configurado": not faltan, "faltan": faltan, "connection_id": c["M365_CONNECTION_ID"] or None,
            "ultima_sincronizacion": _meta("ultima_sincronizacion"),
            "en_curso": _meta("sync_en_curso") == "1",
            "progreso": _json.loads(progreso) if progreso else None}


def _progreso(**kw) -> None:
    import json as _json
    kw.setdefault("cuando", db.ahora())
    _set_meta("sync_progreso", _json.dumps(kw, ensure_ascii=False))


def sincronizar_en_segundo_plano() -> dict:
    """Lanza la sincronización en un hilo y responde de inmediato; el frontend sigue el progreso en estado()."""
    import threading
    if _meta("sync_en_curso") == "1":
        return {"ok": True, "en_curso": True, "mensaje": "Ya hay una sincronización en curso."}
    st = estado()
    if not st["configurado"]:
        return {"ok": False, "error": "Faltan variables de entorno", "faltan": st["faltan"]}
    _set_meta("sync_en_curso", "1")
    _progreso(paso="iniciando", mensaje="Autenticando la aplicación en Microsoft Entra…")

    def correr():
        try:
            r = sincronizar()
            _progreso(paso="listo" if r.get("ok") else "error", resultado=r,
                      mensaje=(f"{r.get('enviados', 0)} ítems enviados al índice de Microsoft 365" if r.get("ok")
                               else (f"{r.get('enviados', 0)} enviados; falló {r['errores'][0]['id']} "
                                     f"(HTTP {r['errores'][0]['status']}): {r['errores'][0]['detalle'][:120]}"
                                     if r.get("errores") else f"Error en {r.get('paso', 'sincronización')}: {str(r.get('detalle', ''))[:160]}")))
        except Exception as e:  # noqa: BLE001
            _progreso(paso="error", mensaje=str(e)[:300])
        finally:
            _set_meta("sync_en_curso", "0")

    threading.Thread(target=correr, daemon=True).start()
    return {"ok": True, "en_curso": True, "mensaje": "Sincronización iniciada."}


def _meta(clave: str):
    con = db.conectar()
    try:
        r = con.execute("SELECT valor FROM meta WHERE clave=?", (clave,)).fetchone()
        return r[0] if r else None
    finally:
        con.close()


def _set_meta(clave: str, valor: str) -> None:
    con = db.conectar()
    with con:
        con.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (clave, valor))
    con.close()


def _token(c: dict) -> str:
    import msal
    app = msal.ConfidentialClientApplication(c["CLIENT_ID"], authority=f"https://login.microsoftonline.com/{c['TENANT_ID']}",
                                             client_credential=c["CLIENT_SECRET"])
    r = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in r:
        raise RuntimeError(f"Autenticación de aplicación fallida: {r.get('error_description')}")
    return r["access_token"]


def _call(method: str, path: str, tk: str, body=None) -> requests.Response:
    r = requests.request(method, f"{GRAPH}{path}", json=body,
                         headers={"Authorization": f"Bearer {tk}", "Content-Type": "application/json"}, timeout=60)
    return r


ESQUEMA = {
    "baseType": "microsoft.graph.externalItem",
    "properties": [
        {"name": "titulo", "type": "String", "isSearchable": True, "isRetrievable": True, "labels": ["title"]},
        {"name": "url", "type": "String", "isRetrievable": True, "labels": ["url"]},
        {"name": "equipo", "type": "String", "isSearchable": True, "isQueryable": True, "isRetrievable": True},
        {"name": "area", "type": "String", "isQueryable": True, "isRetrievable": True, "isRefinable": True},
        {"name": "tipo", "type": "String", "isQueryable": True, "isRetrievable": True, "isRefinable": True},
        {"name": "estado", "type": "String", "isQueryable": True, "isRetrievable": True, "isRefinable": True},
        {"name": "contratista", "type": "String", "isQueryable": True, "isRetrievable": True},
        {"name": "horas", "type": "Double", "isQueryable": True, "isRetrievable": True},
        {"name": "costoRepuestosClp", "type": "Int64", "isQueryable": True, "isRetrievable": True},
        {"name": "fecha", "type": "DateTime", "isQueryable": True, "isRetrievable": True, "labels": ["lastModifiedDateTime"]},
    ],
}


def sincronizar() -> dict:
    c = _cfg()
    st = estado()
    if not st["configurado"]:
        return {"ok": False, "error": "Faltan variables de entorno", "faltan": st["faltan"]}
    tk = _token(c)
    cid = c["M365_CONNECTION_ID"]
    pasos = []

    _progreso(paso="conexion", mensaje=f"Verificando la conexión «{cid}» en Microsoft Graph…")
    r = _call("GET", f"/external/connections/{cid}", tk)
    if r.status_code == 404:
        _progreso(paso="conexion", mensaje="Creando la conexión y registrando el esquema (Microsoft tarda 2–15 min)…")
        r = _call("POST", "/external/connections", tk, {
            "id": cid, "name": "SIGMA Mantención · Cerro Sauce",
            "description": "Órdenes de trabajo del sistema de gestión de mantención de Minera Cerro Sauce.",
            "configuration": {"authorizedAppIds": [c["CLIENT_ID"]]}})
        if r.status_code >= 400:
            return {"ok": False, "paso": "crear conexión", "status": r.status_code, "detalle": r.text[:500]}
        pasos.append("conexión creada")
        r = _call("PATCH", f"/external/connections/{cid}/schema", tk, ESQUEMA)
        if r.status_code >= 400:
            return {"ok": False, "paso": "esquema", "status": r.status_code, "detalle": r.text[:500]}
        op = r.headers.get("Location")
        for _ in range(40):  # hasta ~20 min
            s = requests.get(op, headers={"Authorization": f"Bearer {tk}"}, timeout=30).json()
            if s.get("status") in ("completed", "failed"):
                break
            time.sleep(30)
        if s.get("status") != "completed":
            return {"ok": False, "paso": "esquema", "detalle": s}
        pasos.append("esquema provisionado")
    elif r.status_code >= 400:
        return {"ok": False, "paso": "leer conexión", "status": r.status_code, "detalle": r.text[:500]}

    publica = os.environ.get("SIGMA_URL_PUBLICA", "http://127.0.0.1:8000")
    enviados, errores = 0, []
    ordenes = db.listar_ordenes(limite=5000)
    for i, o in enumerate(ordenes):
        if i % 20 == 0:
            _progreso(paso="items", mensaje=f"Enviando órdenes al índice: {i} de {len(ordenes)}…")
        texto = (f"Orden de trabajo {o['id']} del sistema SIGMA Mantención. Área: {o['area']}. Equipo: {o['equipo']}. "
                 f"Tipo: {o['tipo']}. Estado: {o['estado']}. Fecha: {o['fecha'][:10]}. Duración: {o['horas']} horas. "
                 f"Contratista: {o['contratista']}. Causa: {o.get('causa') or '-'}. Descripción: {o['descripcion']} "
                 + (f"Nota: {o['nota']} " if o.get("nota") else "")
                 + ("Generó registro de detención en la planilla de Operaciones." if o["detencion_registrada"]
                    else "No generó registro de detención en la planilla de Operaciones."))
        body = {
            "acl": [{"type": "everyone", "value": c["TENANT_ID"], "accessType": "grant"}],
            "properties": {
                "titulo@odata.type": "String", "titulo": f"{o['id']} · {o['equipo']} · {o['tipo']}",
                "url": f"{publica}/ot/{o['id']}",
                "equipo@odata.type": "String", "equipo": o["equipo"], "area@odata.type": "String", "area": o["area"],
                "tipo@odata.type": "String", "tipo": o["tipo"], "estado@odata.type": "String", "estado": o["estado"],
                "contratista@odata.type": "String", "contratista": o["contratista"],
                "horas": o["horas"], "costoRepuestosClp": o["costo_repuestos_clp"],
                "fecha": o["fecha"] + ("Z" if len(o["fecha"]) == 19 else ""),
            },
            "content": {"value": texto, "type": "text"},
        }
        r = _call("PUT", f"/external/connections/{cid}/items/{o['id'].replace('-', '')}", tk, body)
        if r.status_code >= 400:
            errores.append({"id": o["id"], "status": r.status_code, "detalle": r.text[:200]})
            if len(errores) > 5:
                break
        else:
            enviados += 1
    ahora = db.ahora()
    _set_meta("ultima_sincronizacion", ahora)
    db.registrar_integracion("api", "servidor", "sincronizar-m365", f"{enviados} ítems enviados", 200, 0, "SIGMA")
    return {"ok": not errores, "pasos": pasos, "enviados": enviados, "errores": errores, "cuando": ahora}
