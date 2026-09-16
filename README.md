# SIGMA Mantención · Minera Cerro Sauce

Sistema de gestión de mantención **ficticio**, construido como caso de capacitación para
*Copilot para Profesionales* (OVO Consulting). Es el sistema que las cápsulas «Copilot desde TI»
conectan a Microsoft 365 Copilot de tres maneras: conector sincronizado, conector federado (MCP) y
repositorio en GitHub.

## Qué es

Una sola aplicación (FastAPI + SQLite) con tres caras sobre los mismos datos:

| Ruta | Qué es | Quién la usa |
|---|---|---|
| `/` | Frontend: tablero, órdenes de trabajo, equipos, integraciones en vivo | El jefe de mantención (y la cámara) |
| `/api/…` | API REST (`/api/docs`) | El conector sincronizado de Copilot y el frontend |
| `/mcp` | Servidor MCP (streamable HTTP) | El conector federado de Copilot |

Toda llamada a `/api` y `/mcp` queda registrada en la **bitácora de integraciones**, que el frontend
muestra en vivo: ahí se ve a Microsoft llamar al sistema mientras Copilot responde.

## Datos

200 órdenes de trabajo, agosto 2025 – julio 2026. Las 173 correctivas salen **fila por fila** de las
planillas de detenciones del caso (`CerroSauce-Detenciones-2026.xlsx` y `…-Julio.xlsx`), así que lo
que Copilot responde desde SIGMA calza con lo que la clase muestra desde SharePoint: Chancado junio
46,5 h en 4 eventos, julio 52,0 h en 5. Se agregan la OT pendiente de repuesto del revestimiento de
CV-03 (05-06-2026), la intervención menor del 18-06 que no generó detención, y preventivas por área.

Se regeneran con `python tools/generar_seed.py "<carpeta A1 - Cerro Sauce>"`.

## Correr en local

```powershell
pip install -r requirements.txt
uvicorn sigma.main:app --port 8000 --reload
```

Abre `http://127.0.0.1:8000`. La base se crea en `data/sigma.db` al primer arranque.

## Variables de entorno

| Variable | Para qué |
|---|---|
| `SIGMA_URL_PUBLICA` | URL pública (para las citas de Copilot) |
| `SIGMA_HOSTS` | Hosts públicos permitidos para el MCP, separados por coma (en Render se toma solo de `RENDER_EXTERNAL_HOSTNAME`) |
| `PERMITIR_ESCRITURA=1` | Registra la herramienta MCP `close_work_order` (Copilot la filtra en conectores; solo un agente con acciones la usa) |
| `DEMO_KEY` | Si se define, `POST /api/admin/*` exige la cabecera `X-Demo-Key` |
| `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET`, `M365_CONNECTION_ID` | Conector sincronizado: `POST /api/admin/sincronizar-m365` empuja las OT al índice de Microsoft 365 |

## Restablecer la demo

`POST /api/admin/restablecer` vuelve la base al seed y vacía historial y bitácora.

---
Datos ficticios. Minera Cerro Sauce no existe.

## Despliegue (Render)

`render.yaml` describe el servicio. En Render: **New → Blueprint** → elegir el repo → Apply. Después, en
**Environment**, cargar a mano las variables sensibles. El plan gratuito no tiene disco: la base se recrea
desde el seed en cada arranque (por eso `SIGMA_DB=/tmp/sigma.db`), lo que para una demo es una ventaja.
El servicio se apaga tras unos minutos sin tráfico y tarda ~30 s en despertar: para grabar, mantenerlo
despierto con un ping periódico a `/salud` (por ejemplo desde cron-job.org) o pasar al plan de pago.
