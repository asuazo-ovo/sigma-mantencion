"""Base de datos de SIGMA Mantención: SQLite, sin ORM. Una tabla de órdenes de trabajo, su historial,
la bitácora de integraciones y los costos hora. `restablecer()` vuelve al seed: es el botón de la demo."""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sqlite3
import threading

RAIZ = pathlib.Path(__file__).resolve().parent
SEED = RAIZ / "seed"
RUTA_DB = pathlib.Path(os.environ.get("SIGMA_DB", RAIZ.parent / "data" / "sigma.db"))

_lock = threading.Lock()

ESQUEMA = """
CREATE TABLE IF NOT EXISTS ordenes (
  id TEXT PRIMARY KEY, fecha TEXT NOT NULL, area TEXT NOT NULL, equipo TEXT NOT NULL, tipo TEXT NOT NULL,
  turno TEXT, causa TEXT, descripcion TEXT, horas REAL NOT NULL DEFAULT 0, contratista TEXT, estado TEXT NOT NULL,
  costo_repuestos_clp INTEGER NOT NULL DEFAULT 0, detencion_registrada INTEGER NOT NULL DEFAULT 0,
  origen TEXT, registrado_por TEXT, nota TEXT, actualizado TEXT
);
CREATE INDEX IF NOT EXISTS ix_ordenes_area_fecha ON ordenes(area, fecha);
CREATE TABLE IF NOT EXISTS historial (
  n INTEGER PRIMARY KEY AUTOINCREMENT, orden_id TEXT NOT NULL, ts TEXT NOT NULL, actor TEXT NOT NULL,
  cambio TEXT NOT NULL, detalle TEXT
);
CREATE TABLE IF NOT EXISTS integraciones (
  n INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, canal TEXT NOT NULL, origen TEXT, metodo TEXT NOT NULL,
  detalle TEXT, estado INTEGER, duracion_ms INTEGER, agente TEXT
);
CREATE TABLE IF NOT EXISTS costos (area TEXT PRIMARY KEY, costo_hora_clp INTEGER NOT NULL, base TEXT, vigencia TEXT);
CREATE TABLE IF NOT EXISTS meta (clave TEXT PRIMARY KEY, valor TEXT);
"""


def conectar() -> sqlite3.Connection:
    RUTA_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(RUTA_DB, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def ahora() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def inicializar() -> None:
    con = conectar()
    with con:
        con.executescript(ESQUEMA)
        if con.execute("SELECT COUNT(*) FROM ordenes").fetchone()[0] == 0:
            _cargar_seed(con)
    con.close()


def restablecer() -> dict:
    """Vuelve la base al estado del seed y vacía historial y bitácora."""
    con = conectar()
    with _lock, con:
        for t in ("ordenes", "historial", "integraciones", "costos", "meta"):
            con.execute(f"DELETE FROM {t}")
        _cargar_seed(con)
        n = con.execute("SELECT COUNT(*) FROM ordenes").fetchone()[0]
    con.close()
    return {"ok": True, "ordenes": n, "restablecido": ahora()}


def _cargar_seed(con: sqlite3.Connection) -> None:
    ordenes = json.loads((SEED / "ordenes.json").read_text(encoding="utf-8"))
    con.executemany(
        """INSERT INTO ordenes (id, fecha, area, equipo, tipo, turno, causa, descripcion, horas, contratista, estado,
           costo_repuestos_clp, detencion_registrada, origen, registrado_por, nota, actualizado)
           VALUES (:id, :fecha, :area, :equipo, :tipo, :turno, :causa, :descripcion, :horas, :contratista, :estado,
           :costo_repuestos_clp, :detencion_registrada, :origen, :registrado_por, :nota, :fecha)""",
        ordenes)
    costos = json.loads((SEED / "costos.json").read_text(encoding="utf-8"))
    con.executemany("INSERT INTO costos VALUES (:area, :costo_hora_clp, :base, :vigencia)", costos)
    con.execute("INSERT OR REPLACE INTO meta VALUES ('seed_cargado', ?)", (ahora(),))


# ---------- consultas ----------

def fila(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    if "detencion_registrada" in d:
        d["detencion_registrada"] = bool(d["detencion_registrada"])
    return d


def listar_ordenes(area: str = "", mes: str = "", estado: str = "", tipo: str = "", equipo: str = "",
                   contratista: str = "", q: str = "", limite: int = 500) -> list[dict]:
    sql, args = "SELECT * FROM ordenes WHERE 1=1", []
    for campo, valor in (("area", area), ("estado", estado), ("tipo", tipo), ("contratista", contratista)):
        if valor:
            sql += f" AND lower({campo}) LIKE lower(?)"; args.append(f"%{valor}%")
    if mes:
        sql += " AND substr(fecha,1,7) = ?"; args.append(mes)
    if equipo:
        sql += " AND lower(equipo) LIKE lower(?)"; args.append(f"%{equipo}%")
    if q:
        sql += " AND lower(id||' '||area||' '||equipo||' '||tipo||' '||causa||' '||descripcion||' '||contratista||' '||estado||' '||coalesce(nota,'')) LIKE lower(?)"
        args.append(f"%{q}%")
    sql += " ORDER BY fecha LIMIT ?"; args.append(limite)
    con = conectar()
    try:
        return [fila(r) for r in con.execute(sql, args)]
    finally:
        con.close()


def obtener_orden(id_: str) -> dict | None:
    clave = id_.replace("-", "").upper()
    con = conectar()
    try:
        r = con.execute("SELECT * FROM ordenes WHERE replace(upper(id),'-','') = ?", (clave,)).fetchone()
        o = fila(r)
        if o:
            o["historial"] = [dict(h) for h in con.execute(
                "SELECT ts, actor, cambio, detalle FROM historial WHERE orden_id=? ORDER BY n", (o["id"],))]
        return o
    finally:
        con.close()


def resumen_horas(mes_desde: str = "2025-07", mes_hasta: str = "2026-07") -> list[dict]:
    """Horas de detención registrada por área y mes (lo que muestra la planilla), más costo estimado."""
    con = conectar()
    try:
        costos = {r["area"]: r["costo_hora_clp"] for r in con.execute("SELECT area, costo_hora_clp FROM costos")}
        filas = con.execute(
            """SELECT area, substr(fecha,1,7) AS mes, SUM(horas) AS horas, COUNT(*) AS eventos
               FROM ordenes WHERE detencion_registrada=1 AND substr(fecha,1,7) BETWEEN ? AND ?
               GROUP BY area, mes ORDER BY mes, area""", (mes_desde, mes_hasta))
        return [{"area": r["area"], "mes": r["mes"], "horas": round(r["horas"], 2), "eventos": r["eventos"],
                 "sobre_umbral": r["horas"] > 40, "costo_estimado_clp": int(round(r["horas"] * costos.get(r["area"], 0)))}
                for r in filas]
    finally:
        con.close()


def pendientes_repuesto(hoy: dt.date | None = None) -> list[dict]:
    hoy = hoy or dt.date.today()
    out = []
    for o in listar_ordenes(estado="Pendiente de repuesto"):
        o["dias_pendiente"] = (hoy - dt.date.fromisoformat(o["fecha"][:10])).days
        o["escalar_comite"] = o["dias_pendiente"] > 30  # OP-PR-014 §8
        out.append(o)
    return out


def costos_hora() -> list[dict]:
    con = conectar()
    try:
        return [dict(r) for r in con.execute("SELECT * FROM costos ORDER BY costo_hora_clp DESC")]
    finally:
        con.close()


# ---------- escrituras ----------

def cambiar_estado(id_: str, estado_nuevo: str, actor: str, comentario: str = "") -> dict:
    o = obtener_orden(id_)
    if not o:
        return {"error": f"No existe la orden de trabajo {id_}"}
    con = conectar()
    with _lock, con:
        con.execute("UPDATE ordenes SET estado=?, actualizado=? WHERE id=?", (estado_nuevo, ahora(), o["id"]))
        con.execute("INSERT INTO historial (orden_id, ts, actor, cambio, detalle) VALUES (?,?,?,?,?)",
                    (o["id"], ahora(), actor, f"{o['estado']} → {estado_nuevo}", comentario))
    con.close()
    return {"ok": True, "id": o["id"], "estado_anterior": o["estado"], "estado_nuevo": estado_nuevo}


# ---------- bitácora de integraciones ----------

def registrar_integracion(canal: str, origen: str, metodo: str, detalle: str, estado: int, duracion_ms: int,
                          agente: str) -> None:
    con = conectar()
    with _lock, con:
        con.execute("INSERT INTO integraciones (ts, canal, origen, metodo, detalle, estado, duracion_ms, agente) "
                    "VALUES (?,?,?,?,?,?,?,?)", (ahora(), canal, origen, metodo, detalle[:2000], estado, duracion_ms, agente[:200]))
    con.close()


def listar_integraciones(desde_n: int = 0, limite: int = 200) -> list[dict]:
    con = conectar()
    try:
        return [dict(r) for r in con.execute(
            "SELECT * FROM integraciones WHERE n > ? ORDER BY n DESC LIMIT ?", (desde_n, limite))]
    finally:
        con.close()
