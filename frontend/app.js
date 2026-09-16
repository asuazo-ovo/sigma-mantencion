/* SIGMA Mantención · frontend sin framework. Habla con /api; el MCP lo usa Copilot, no esta pantalla. */
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const api = async (p, opt = {}) => {
    // X-Sigma-UI: el servidor no anota en la bitácora las llamadas del propio frontend, solo las externas
    const r = await fetch("/api" + p, { ...opt, headers: { ...(opt.headers || {}), "X-Sigma-UI": "1" } });
    if (!r.ok) throw Object.assign(new Error(r.statusText), { status: r.status, body: await r.text() });
    return r.json();
  };
  const clp = n => "$" + Math.round(n).toLocaleString("es-CL");
  const h = n => (Math.round(n * 100) / 100).toLocaleString("es-CL", { maximumFractionDigits: 2 }) + " h";
  const fecha = iso => { const d = new Date(iso); return d.toLocaleDateString("es-CL", { day: "2-digit", month: "2-digit", year: "numeric" }); };
  const hora = iso => new Date(iso).toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  const MESES = { "01": "ene", "02": "feb", "03": "mar", "04": "abr", "05": "may", "06": "jun", "07": "jul", "08": "ago", "09": "sep", "10": "oct", "11": "nov", "12": "dic" };
  const mesCorto = m => MESES[m.slice(5, 7)] + " " + m.slice(2, 4);
  const mesLargo = m => ({ "01": "enero", "02": "febrero", "03": "marzo", "04": "abril", "05": "mayo", "06": "junio", "07": "julio", "08": "agosto", "09": "septiembre", "10": "octubre", "11": "noviembre", "12": "diciembre" })[m.slice(5, 7)] + " de " + m.slice(0, 4);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const UMBRAL = 40;
  let todas = [];   // todas las OT (198): sirve para filtros, equipos y meses

  // ---------- rutas ----------
  const vistas = { tablero: cargarTablero, ordenes: cargarOrdenes, equipos: cargarEquipos, integraciones: cargarIntegraciones };
  function ruta() {
    const r = (location.hash.replace(/^#\/?/, "") || "tablero").split("/")[0];
    const v = vistas[r] ? r : "tablero";
    $$(".vista").forEach(s => s.classList.toggle("activa", s.id === "v-" + v));
    $$("nav a").forEach(a => a.classList.toggle("activa", a.dataset.ruta === v));
    vistas[v]();
  }
  window.addEventListener("hashchange", ruta);

  // ---------- tablero ----------
  async function cargarTablero() {
    const [res, pend] = await Promise.all([api("/resumen?desde=2025-08&hasta=2026-07"), api("/pendientes")]);
    const filas = res.filas, costos = Object.fromEntries(res.costos_hora.map(c => [c.area, c.costo_hora_clp]));
    const meses = [...new Set(filas.map(f => f.mes))].sort();
    const ultimo = meses[meses.length - 1];
    const areas = [...new Set(filas.map(f => f.area))].sort();
    const sobre = filas.filter(f => f.sobre_umbral);
    const ch = filas.filter(f => f.area === "Chancado" && f.mes === ultimo)[0];
    const consecutivos = areas.filter(a => meses.slice(-2).every(m => filas.some(f => f.area === a && f.mes === m && f.sobre_umbral)));
    $("#kpis").innerHTML = [
      { v: h(filas.filter(f => f.mes === ultimo).reduce((s, f) => s + f.horas, 0)), l: "horas de detención · " + mesLargo(ultimo) },
      { v: ch ? h(ch.horas) : "—", l: "Chancado · " + mesLargo(ultimo) + (ch && ch.sobre_umbral ? " · sobre el umbral" : ""), c: ch && ch.sobre_umbral ? "alerta" : "" },
      { v: consecutivos.length ? consecutivos.join(", ") : "ninguna", l: "áreas con 2 meses seguidos sobre 40 h · revisar contrato (§6)", c: consecutivos.length ? "alerta" : "" },
      { v: pend.pendientes.length, l: "OT pendientes de repuesto · " + (pend.pendientes.filter(p => p.escalar_comite).length) + " sobre 30 días (§8)", c: "cobre" },
    ].map(k => `<div class="kpi ${k.c || ""}"><div class="v">${esc(k.v)}</div><div class="l">${esc(k.l)}</div></div>`).join("");

    const sel = $("#sel-area-graf");
    if (!sel.options.length) { sel.innerHTML = areas.map(a => `<option ${a === "Chancado" ? "selected" : ""}>${a}</option>`).join(""); sel.onchange = () => dibujar(); }
    function dibujar() {
      const a = sel.value, datos = meses.map(m => ({ m, f: filas.find(x => x.area === a && x.mes === m) }));
      const W = 900, H = 260, pl = 40, pb = 34, pt = 18, w = (W - pl - 10) / datos.length;
      const max = Math.max(UMBRAL * 1.35, ...datos.map(d => d.f ? d.f.horas : 0));
      const y = v => pt + (H - pt - pb) * (1 - v / max);
      let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">`;
      [0, 20, 40, 60].filter(v => v <= max).forEach(v => { svg += `<line x1="${pl}" x2="${W - 10}" y1="${y(v)}" y2="${y(v)}" stroke="#eef1f3"/><text x="${pl - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`; });
      datos.forEach((d, i) => {
        const v = d.f ? d.f.horas : 0, x = pl + i * w + w * 0.18, bw = w * 0.64, al = v > UMBRAL;
        svg += `<rect class="barra ${al ? "alerta" : ""}" x="${x}" y="${y(v)}" width="${bw}" height="${Math.max(0, y(0) - y(v))}" rx="3"><title>${d.m}: ${v} h · ${d.f ? d.f.eventos : 0} eventos · ${clp(v * (costos[a] || 0))}</title></rect>`;
        svg += `<text x="${x + bw / 2}" y="${H - pb + 16}" text-anchor="middle">${mesCorto(d.m)}</text>`;
        if (v) svg += `<text class="val" x="${x + bw / 2}" y="${y(v) - 5}" text-anchor="middle">${v.toLocaleString("es-CL")}</text>`;
      });
      svg += `<line class="umbral" x1="${pl}" x2="${W - 10}" y1="${y(UMBRAL)}" y2="${y(UMBRAL)}"/><text x="${pl + 4}" y="${y(UMBRAL) - 5}" fill="#E08A1E">umbral 40 h</text></svg>`;
      $("#grafico").innerHTML = svg;
    }
    dibujar();

    $("#pendientes").innerHTML = pend.pendientes.length ? pend.pendientes.map(p => `
      <div class="pend ${p.escalar_comite ? "alerta" : ""}" data-ot="${p.id}">
        <div class="d">${p.dias_pendiente} días</div>
        <div><b class="id">${p.id}</b> · ${esc(p.equipo)}</div>
        <div class="t">${esc(p.descripcion)}</div>
        <div class="t">${p.escalar_comite ? "Supera los 30 días: corresponde escalar al comité de operaciones (OP-PR-014 §8)." : "Dentro del plazo."}</div>
      </div>`).join("") : `<div class="vacio">Sin pendientes de repuesto.</div>`;
    $$("#pendientes .pend").forEach(el => el.onclick = () => abrirOT(el.dataset.ot));

    const selM = $("#sel-mes-tabla");
    if (!selM.options.length) { selM.innerHTML = meses.slice().reverse().map(m => `<option value="${m}">${mesLargo(m)}</option>`).join(""); selM.onchange = tablaAreas; }
    function tablaAreas() {
      const m = selM.value; $("#mes-tabla").textContent = mesLargo(m);
      const rows = areas.map(a => filas.find(f => f.area === a && f.mes === m) || { area: a, horas: 0, eventos: 0, costo_estimado_clp: 0, sobre_umbral: false }).sort((x, y2) => y2.horas - x.horas);
      $("#tabla-areas").innerHTML = `<thead><tr><th>Área</th><th class="num">Eventos</th><th class="num">Horas</th><th class="num">Costo hora</th><th class="num">Costo estimado</th><th>Estado</th></tr></thead><tbody>` +
        rows.map(r => `<tr class="clic" data-area="${r.area}" data-mes="${m}"><td><b>${r.area}</b></td><td class="num">${r.eventos}</td><td class="num">${h(r.horas)}</td><td class="num">${clp(costos[r.area] || 0)}</td><td class="num">${clp(r.costo_estimado_clp)}</td><td>${r.sobre_umbral ? '<span class="chip alerta">sobre 40 h</span>' : '<span class="chip ok">normal</span>'}</td></tr>`).join("") + "</tbody>";
      $$("#tabla-areas tr.clic").forEach(tr => tr.onclick = () => { location.hash = `#/ordenes?area=${encodeURIComponent(tr.dataset.area)}&mes=${tr.dataset.mes}`; });
    }
    tablaAreas();
  }

  // ---------- órdenes ----------
  async function todasOT() { if (!todas.length) todas = (await api("/ordenes?limite=5000")).ordenes; return todas; }
  async function cargarOrdenes() {
    const ot = await todasOT();
    const q = new URLSearchParams(location.hash.split("?")[1] || "");
    const fill = (id, vals) => { const s = $(id); if (s.options.length <= 1) vals.forEach(v => s.add(new Option(v, v))); };
    fill("#f-area", [...new Set(ot.map(o => o.area))].sort());
    const selMes = $("#f-mes"); if (selMes.options.length <= 1) [...new Set(ot.map(o => o.fecha.slice(0, 7)))].sort().reverse().forEach(m => selMes.add(new Option(mesLargo(m), m)));
    fill("#f-contratista", [...new Set(ot.map(o => o.contratista))].sort());
    if (q.get("area")) $("#f-area").value = q.get("area");
    if (q.get("mes")) $("#f-mes").value = q.get("mes");
    if (q.get("equipo")) $("#f-q").value = q.get("equipo");
    const render = () => {
      const f = { area: $("#f-area").value, mes: $("#f-mes").value, tipo: $("#f-tipo").value, estado: $("#f-estado").value, contratista: $("#f-contratista").value, q: $("#f-q").value.toLowerCase() };
      const sel = ot.filter(o => (!f.area || o.area === f.area) && (!f.mes || o.fecha.startsWith(f.mes)) && (!f.tipo || o.tipo === f.tipo) && (!f.estado || o.estado === f.estado) && (!f.contratista || o.contratista === f.contratista) &&
        (!f.q || [o.id, o.equipo, o.descripcion, o.causa, o.nota, o.area].join(" ").toLowerCase().includes(f.q)));
      $("#ot-resumen").textContent = `${sel.length} de ${ot.length} órdenes` + (f.area ? ` · ${f.area}` : "") + (f.mes ? ` · ${mesLargo(f.mes)}` : "");
      $("#tabla-ot").innerHTML = `<thead><tr><th>OT</th><th>Fecha</th><th>Área</th><th>Equipo</th><th>Tipo</th><th>Causa</th><th class="num">Horas</th><th>Contratista</th><th>Detención</th><th>Estado</th></tr></thead><tbody>` +
        sel.map(o => `<tr class="clic" data-ot="${o.id}"><td class="id">${o.id}</td><td>${fecha(o.fecha)}</td><td>${esc(o.area)}</td><td>${esc(o.equipo)}</td><td>${esc(o.tipo)}</td><td>${esc(o.causa || "")}</td><td class="num">${o.horas.toLocaleString("es-CL")}</td><td>${esc(o.contratista)}</td><td><span class="punto ${o.detencion_registrada ? "" : "no"}"></span>${o.detencion_registrada ? "registrada" : "sin registro"}</td><td>${o.estado === "Cerrada" ? '<span class="chip ok">Cerrada</span>' : `<span class="chip cobre">${esc(o.estado)}</span>`}</td></tr>`).join("") + "</tbody>";
      $$("#tabla-ot tr.clic").forEach(tr => tr.onclick = () => abrirOT(tr.dataset.ot));
      const con = sel.filter(o => o.detencion_registrada), sin = sel.filter(o => !o.detencion_registrada);
      const sum = a => a.reduce((s, o) => s + o.horas, 0);
      $("#ot-totales").innerHTML = `<span>Total <b>${h(sum(sel))}</b></span><span>Con registro de detención <b>${h(sum(con))}</b> · ${con.length} OT</span><span>Sin registro <b>${h(sum(sin))}</b> · ${sin.length} OT</span><span>Repuestos <b>${clp(sel.reduce((s, o) => s + o.costo_repuestos_clp, 0))}</b></span>`;
    };
    $$("#v-ordenes .sel").forEach(el => el.oninput = render);
    $("#f-limpiar").onclick = () => { $$("#v-ordenes .sel").forEach(el => el.value = ""); render(); };
    render();
  }

  // ---------- equipos ----------
  async function cargarEquipos() {
    const ot = await todasOT();
    const porEq = {}; ot.forEach(o => { (porEq[o.equipo] ||= { area: o.area, n: 0, h: 0, ots: [] }); porEq[o.equipo].n++; porEq[o.equipo].h += o.horas; porEq[o.equipo].ots.push(o); });
    const lista = Object.entries(porEq).sort((a, b) => b[1].h - a[1].h);
    const q = new URLSearchParams(location.hash.split("?")[1] || "");
    let actual = q.get("equipo") || (porEq["Correa CV-03"] ? "Correa CV-03" : lista[0][0]);
    const render = () => {
      const f = $("#eq-buscar").value.toLowerCase();
      $("#lista-equipos").innerHTML = lista.filter(([e, d]) => !f || (e + d.area).toLowerCase().includes(f)).map(([e, d]) => `<li class="${e === actual ? "activa" : ""}" data-eq="${esc(e)}"><span><b>${esc(e)}</b><small>${esc(d.area)}</small></span><span class="chip">${d.n} OT · ${h(d.h)}</span></li>`).join("");
      $$("#lista-equipos li").forEach(li => li.onclick = () => { actual = li.dataset.eq; render(); });
      const d = porEq[actual]; $("#eq-titulo").textContent = actual + " · " + d.area; $("#eq-total").textContent = `${d.n} OT · ${h(d.h)}`;
      $("#linea-tiempo").innerHTML = d.ots.slice().sort((a, b) => b.fecha.localeCompare(a.fecha)).map(o => `<li class="${o.estado !== "Cerrada" ? "pend" : o.tipo === "Correctiva menor" ? "menor" : ""}" data-ot="${o.id}"><div class="f">${fecha(o.fecha)} · ${esc(o.turno || "")} · <span class="id">${o.id}</span></div><div class="h">${esc(o.tipo)} · ${o.horas.toLocaleString("es-CL")} h · ${esc(o.contratista)}</div><div>${esc(o.descripcion)}</div>${o.nota ? `<div class="ayuda">${esc(o.nota)}</div>` : ""}${o.estado !== "Cerrada" ? `<span class="chip cobre">${esc(o.estado)}</span>` : ""}</li>`).join("");
      $$("#linea-tiempo li").forEach(li => li.onclick = () => abrirOT(li.dataset.ot));
    };
    $("#eq-buscar").oninput = render; render();
  }

  // ---------- integraciones (en vivo) ----------
  let ultimoN = 0, timer = null, vistos = new Set();
  const CANAL = { mcp: '<span class="chip mcp">MCP</span>', api: '<span class="chip api">API</span>' };
  function filaInt(e, nuevo) {
    let det = e.detalle || "";
    try { const j = JSON.parse(det); if (j.tool) det = `${j.tool}(${Object.entries(j.arguments || {}).filter(([, v]) => v !== "" && v != null).map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(", ")})`; else if (j.client) det = `cliente ${j.client} · protocolo ${j.protocolVersion}`; } catch {}
    const origen = /^(20\.|40\.|52\.|13\.|104\.)/.test(e.origen || "") ? `${esc(e.origen)}<br><small>Microsoft</small>` : esc(e.origen || "");
    return `<tr class="${nuevo ? "nuevo" : ""}"><td>${hora(e.ts)}</td><td>${CANAL[e.canal] || esc(e.canal)}</td><td>${origen}</td><td><b>${esc(e.metodo)}</b></td><td class="det">${esc(det)}</td><td>${e.estado}</td><td class="num">${e.duracion_ms ?? ""}</td></tr>`;
  }
  async function sondear(inicial) {
    if (!$("#v-integraciones").classList.contains("activa")) return;
    try {
      const d = await api(`/integraciones?desde=${inicial ? 0 : ultimoN}&limite=${inicial ? 60 : 50}`);
      const nuevos = d.eventos.filter(e => !vistos.has(e.n)).sort((a, b) => a.n - b.n);
      if (nuevos.length) {
        if (!$("#int-pausa").checked) {
          const tb = $("#tabla-int tbody");
          nuevos.forEach(e => { vistos.add(e.n); tb.insertAdjacentHTML("afterbegin", filaInt(e, !inicial)); });
          while (tb.rows.length > 300) tb.deleteRow(-1);
          $("#int-vacio").style.display = tb.rows.length ? "none" : "";
          if (!inicial) { const p = $("#pulso"); p.classList.remove("on"); void p.offsetWidth; p.classList.add("on"); }
        }
        ultimoN = Math.max(ultimoN, ...d.eventos.map(e => e.n));
      }
    } catch (e) { /* servidor reiniciando: se reintenta */ }
  }
  async function cargarIntegraciones() {
    clearInterval(timer);
    if (!vistos.size) await sondear(true);
    timer = setInterval(() => sondear(false), 1500);
    $("#int-limpiar").onclick = () => { $("#tabla-int tbody").innerHTML = ""; $("#int-vacio").style.display = ""; };
    const m = await api("/admin/estado-m365");
    $("#m365").innerHTML = `<dl class="m365">
      <dt>Conector sincronizado</dt><dd>${m.configurado ? `<span class="chip ok">configurado</span> · conexión <span class="id">${esc(m.connection_id)}</span>` : `<span class="chip">sin credenciales</span><small>faltan: ${esc(m.faltan.join(", "))}</small>`}</dd>
      <dt>Última sincronización</dt><dd>${m.ultima_sincronizacion ? hora(m.ultima_sincronizacion) + " · " + fecha(m.ultima_sincronizacion) : "nunca"}</dd>
      <dt>Conector federado (MCP)</dt><dd>endpoint <span class="id">${location.origin}/mcp</span><small>Copilot lo llama en vivo; cada llamada aparece en la bitácora.</small></dd></dl>
      <button id="btn-sync" class="btn cobre" ${m.configurado ? "" : "disabled"} style="margin-top:10px">Sincronizar con Microsoft 365</button>`;
    $("#btn-sync").onclick = () => admin("/admin/sincronizar-m365", "#btn-sync", r => r.ok ? `${r.enviados} ítems enviados al índice de Microsoft 365 (${hora(r.cuando)})${r.pasos.length ? " · " + r.pasos.join(", ") : ""}` : `Error en ${r.paso || "sincronización"}: ${JSON.stringify(r.detalle || r.errores || r.faltan)}`);
    $("#btn-reset").onclick = () => { if (confirm("¿Volver la base al estado inicial? Se pierden cambios y bitácora.")) admin("/admin/restablecer", "#btn-reset", r => { todas = []; vistos.clear(); ultimoN = 0; $("#tabla-int tbody").innerHTML = ""; return `Restablecido: ${r.ordenes} OT (${hora(r.restablecido)})`; }); };
  }
  let claveDemo = sessionStorage.getItem("demoKey") || "";
  async function admin(path, btn, fmt) {
    const b = $(btn), msg = $("#admin-msg"); b.disabled = true; msg.textContent = "Trabajando…";
    try {
      const r = await api(path, { method: "POST", headers: claveDemo ? { "X-Demo-Key": claveDemo } : {} });
      msg.textContent = fmt(r);
    } catch (e) {
      if (e.status === 401) { claveDemo = prompt("Clave de demo (X-Demo-Key):") || ""; sessionStorage.setItem("demoKey", claveDemo); msg.textContent = claveDemo ? "Clave guardada; vuelve a intentar." : "Cancelado."; }
      else msg.textContent = "Error: " + (e.body || e.message);
    } finally { b.disabled = false; }
  }

  // ---------- panel de detalle ----------
  async function abrirOT(id) {
    const o = await api("/ordenes/" + encodeURIComponent(id)).catch(() => null);
    if (!o) return;
    $("#p-titulo").textContent = o.id;
    const campo = (k, v) => `<dt>${k}</dt><dd>${v}</dd>`;
    $("#p-cuerpo").innerHTML = `
      <div>${o.estado === "Cerrada" ? '<span class="chip ok">Cerrada</span>' : `<span class="chip cobre">${esc(o.estado)}</span>`} <span class="chip">${esc(o.tipo)}</span> ${o.detencion_registrada ? '<span class="chip alerta">generó detención</span>' : '<span class="chip">sin registro de detención</span>'}</div>
      <dl class="campos">${campo("Equipo", esc(o.equipo))}${campo("Área", esc(o.area))}${campo("Fecha", fecha(o.fecha) + " · " + esc(o.turno || ""))}${campo("Duración", h(o.horas))}${campo("Contratista", esc(o.contratista))}${campo("Causa", esc(o.causa || "—"))}${campo("Costo de repuestos", clp(o.costo_repuestos_clp))}${campo("Registrado por", esc(o.registrado_por || "—"))}${campo("Origen del registro", o.origen === "planilla" ? "planilla de detenciones de Operaciones" : "SIGMA")}</dl>
      <p>${esc(o.descripcion)}</p>${o.nota ? `<div class="nota">${esc(o.nota)}</div>` : ""}
      <h3 style="color:var(--azul);font-size:14px;margin:18px 0 8px">Historial</h3>
      <ul class="hist">${(o.historial || []).length ? o.historial.map(x => `<li><span class="ts">${hora(x.ts)} ${fecha(x.ts)}</span> · <b>${esc(x.cambio)}</b> · ${esc(x.actor)}${x.detalle ? ` — ${esc(x.detalle)}` : ""}</li>`).join("") : `<li class="ayuda">Sin cambios desde su creación (${fecha(o.fecha)}).</li>`}</ul>
      <p class="ayuda" style="margin-top:18px">Ver en <a href="#/equipos?equipo=${encodeURIComponent(o.equipo)}" onclick="document.getElementById('p-cerrar').click()">historial del equipo</a> · URL de esta OT: <span class="id">${location.origin}/ot/${o.id}</span></p>`;
    $("#panel").classList.add("abierto"); $("#panel").setAttribute("aria-hidden", "false"); $("#velo").classList.add("on");
  }
  const cerrar = () => { $("#panel").classList.remove("abierto"); $("#panel").setAttribute("aria-hidden", "true"); $("#velo").classList.remove("on"); };
  $("#p-cerrar").onclick = cerrar; $("#velo").onclick = cerrar;
  document.addEventListener("keydown", e => { if (e.key === "Escape") cerrar(); });

  // ---------- arranque ----------
  const ot = new URLSearchParams(location.search).get("ot");  // /ot/<id> redirige a /?ot=<id>
  ruta();
  if (ot) { history.replaceState(null, "", location.pathname + location.hash); abrirOT(ot); }
  // el pulso del menú sigue vivo aunque no estés en Integraciones
  setInterval(async () => { if ($("#v-integraciones").classList.contains("activa")) return; try { const d = await api(`/integraciones?desde=${ultimoN}&limite=5`); const n = d.eventos.filter(e => !vistos.has(e.n)); if (n.length && ultimoN) { const p = $("#pulso"); p.classList.remove("on"); void p.offsetWidth; p.classList.add("on"); } if (!ultimoN && d.eventos.length) ultimoN = Math.max(...d.eventos.map(e => e.n)); } catch {} }, 4000);
})();
