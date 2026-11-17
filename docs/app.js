const PARTIDOS = window.PARTIDOS;
const JUGADORAS = window.JUGADORAS;
const CLUB = "Club Aguirre";
const CLASIFICACION = window.CLASIFICACION || [];
const LIGA = window.LIGA || {};

/* Colores de camiseta (texto libre del CSV -> color CSS). Admite "NEGRA/amarilla". */
const COLORES = [
  ["celeste", "#6ec1ea"], ["clarito", "#8fc5f0"], ["granate", "#7b1e3a"], ["coral", "#ff7f6e"], ["rosa", "#f08cb4"],
  ["verde", "#089369"], ["amarill", "#f2c500"], ["negr", "#222222"], ["blanc", "#ffffff"],
  ["azul", "#1f5fbf"], ["roj", "#d12b2b"], ["naranja", "#f28a1c"], ["morad", "#6a3fa0"], ["gris", "#8a8a8a"],
];
function colorCss(txt) {
  const t = (txt || "").toLowerCase();
  const hit = COLORES.find(([k]) => t.includes(k));
  return hit ? hit[1] : null;
}
function camiseta(txt) {
  if (!txt) return "";
  const partes = txt.split("/").map((s) => s.trim()).filter(Boolean);
  const cols = partes.map(colorCss);
  const fondo = cols.length > 1 && cols.every(Boolean)
    ? `linear-gradient(90deg, ${cols[0]} 50%, ${cols[1]} 50%)`
    : cols[0] || "transparent";
  const etiqueta = partes.map((s) => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase()).join(" y ");
  return `<span class="camiseta"><span class="muestra" style="background:${fondo}" aria-hidden="true"></span>${esc(etiqueta)}</span>`;
}

/* ---------- Almacenamiento (Firestore o modo local) ---------- */

async function crearStore() {
  const cfg = window.FIREBASE_CONFIG;
  if (cfg) {
    try {
      const V = "10.12.2";
      const { initializeApp } = await import(`https://www.gstatic.com/firebasejs/${V}/firebase-app.js`);
      const fs = await import(`https://www.gstatic.com/firebasejs/${V}/firebase-firestore.js`);
      const db = fs.getFirestore(initializeApp(cfg));
      const ref = (j) => fs.doc(db, "partidos", "j" + j);
      return {
        modo: "nube",
        suscribir(cb) {
          return fs.onSnapshot(fs.collection(db, "partidos"), (snap) => {
            const out = {};
            snap.forEach((d) => (out[Number(d.id.slice(1))] = d.data()));
            cb(out);
          }, (e) => { console.error(e); cb(null, e); });
        },
        // arrayUnion/arrayRemove evitan pisar cambios simultáneos de varios padres
        setDisponible: (j, nombre, si) =>
          fs.setDoc(ref(j), { noDisp: si ? fs.arrayRemove(nombre) : fs.arrayUnion(nombre) }, { merge: true }),
        setConvocadas: (j, lista) => fs.setDoc(ref(j), { conv: lista }, { merge: true }),
        // Entrenamientos: un documento por fecha ISO (entrenamientos/2026-11-16)
        suscribirEntrenos(cb) {
          return fs.onSnapshot(fs.collection(db, "entrenamientos"), (snap) => {
            const out = {};
            snap.forEach((d) => (out[d.id] = d.data()));
            cb(out);
          }, (e) => { console.error(e); cb(null, e); });
        },
        setAsistencia: (f, nombre, si) =>
          fs.setDoc(fs.doc(db, "entrenamientos", f), { asisten: si ? fs.arrayUnion(nombre) : fs.arrayRemove(nombre) }, { merge: true }),
        setAsistentes: (f, lista) => fs.setDoc(fs.doc(db, "entrenamientos", f), { asisten: lista }, { merge: true }),
        setSinEntreno: (f, si) => fs.setDoc(fs.doc(db, "entrenamientos", f), { cancelado: si }, { merge: true }),
        setNotas: (f, txt) => fs.setDoc(fs.doc(db, "entrenamientos", f), { notas: txt }, { merge: true }),
      };
    } catch (e) {
      console.error("No se pudo iniciar Firebase, uso modo local", e);
    }
  }
  return storeLocal();
}

function storeLocal() {
  const K = "aguirre-infantil-fem-2627";
  const leer = () => { try { return JSON.parse(localStorage.getItem(K)) || {}; } catch { return {}; } };
  const guardar = (o) => { try { localStorage.setItem(K, JSON.stringify(o)); } catch {} };
  let cb = () => {};
  window.addEventListener("storage", (e) => { if (e.key === K) cb(leer()); });
  const mod = (j, fn) => { const o = leer(); o[j] = o[j] || {}; fn(o[j]); guardar(o); cb(o); };
  const KE = K + "-entrenos";
  const leerE = () => { try { return JSON.parse(localStorage.getItem(KE)) || {}; } catch { return {}; } };
  let cbE = () => {};
  window.addEventListener("storage", (e) => { if (e.key === KE) cbE(leerE()); });
  const modE = (f, fn) => {
    const o = leerE(); o[f] = o[f] || {}; fn(o[f]);
    try { localStorage.setItem(KE, JSON.stringify(o)); } catch {}
    cbE(o);
  };
  return {
    modo: "local",
    suscribir(f) { cb = f; f(leer()); return () => {}; },
    async setDisponible(j, nombre, si) {
      mod(j, (p) => {
        const s = new Set(p.noDisp || []);
        si ? s.delete(nombre) : s.add(nombre);
        p.noDisp = [...s];
      });
    },
    async setConvocadas(j, lista) { mod(j, (p) => { p.conv = lista; }); },
    // Entrenamientos (misma estructura que en Firestore, clave aparte)
    suscribirEntrenos(f) { cbE = f; f(leerE()); return () => {}; },
    async setAsistencia(f, nombre, si) {
      modE(f, (d) => { const s = new Set(d.asisten || []); si ? s.add(nombre) : s.delete(nombre); d.asisten = [...s]; });
    },
    async setAsistentes(f, lista) { modE(f, (d) => { d.asisten = lista; }); },
    async setSinEntreno(f, si) { modE(f, (d) => { d.cancelado = si; }); },
    async setNotas(f, txt) { modE(f, (d) => { d.notas = txt; }); },
  };
}

/* ---------- Utilidades ---------- */

const MIN_JUGADORAS = window.MIN_JUGADORAS || 7;
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fechaCorta = (iso) => {
  const d = new Date(iso + "T12:00:00");
  const q = (o) => d.toLocaleDateString("es-ES", o).replace(".", "");
  return { dia: q({ weekday: "short" }), num: d.getDate(), mes: q({ month: "short" }) };
};
const fechaLarga = (iso) =>
  new Date(iso + "T12:00:00").toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" });
const hoyISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const toast = (msg) => {
  const t = document.getElementById("toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => (t.hidden = true), 2500);
};

/* Estado de sincronización: solo se muestra cuando hay algo que contar */
const estEl = document.getElementById("estado");
let base = { txt: "", cls: "" };
function pintarEstado(txt, cls) { estEl.textContent = txt; estEl.className = "estado" + (cls ? " " + cls : ""); }
function setBase(txt, cls) { base = { txt, cls }; pintarEstado(txt, cls); }
function guardado() {
  pintarEstado("Guardado", "ok");
  clearTimeout(guardado.t);
  guardado.t = setTimeout(() => pintarEstado(base.txt, base.cls), 2000);
}

/* Calendario (.ics): hora local, 90 min de duración y aviso 2 h antes */
function descargarIcs(p) {
  const pad = (n) => String(n).padStart(2, "0");
  const txt = (t) => String(t).replace(/\\/g, "\\\\").replace(/;/g, "\;").replace(/,/g, "\\,").replace(/\n/g, "\\n");
  const f = p.fecha.replace(/-/g, "");
  let fechas;
  if (p.hora) {
    const [h, m] = p.hora.split(":").map(Number);
    const fin = Math.min(h * 60 + m + 90, 23 * 60 + 59);
    fechas = [`DTSTART:${f}T${pad(h)}${pad(m)}00`, `DTEND:${f}T${pad(Math.floor(fin / 60))}${pad(fin % 60)}00`];
  } else {
    const sig = new Date(p.fecha + "T12:00:00"); sig.setDate(sig.getDate() + 1);
    const g = `${sig.getFullYear()}${pad(sig.getMonth() + 1)}${pad(sig.getDate())}`;
    fechas = [`DTSTART;VALUE=DATE:${f}`, `DTEND;VALUE=DATE:${g}`];
  }
  const titulo = `${p.local} vs ${p.visitante} (J${p.jornada})`;
  const lineas = [
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Club Aguirre Infantil Femenino//ES", "CALSCALE:GREGORIAN",
    "BEGIN:VEVENT",
    `UID:j${p.jornada}-infantil-fem-2627@clubaguirre`,
    `DTSTAMP:${new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+/, "")}`,
    ...fechas,
    `SUMMARY:${txt(titulo)}`,
    ...(p.instalacion ? [`LOCATION:${txt(p.instalacion + ", Madrid")}`] : []),
    `DESCRIPTION:${txt("Fútbol sala · Infantil Femenino · Jornada " + p.jornada)}`,
    "BEGIN:VALARM", "TRIGGER:-PT2H", "ACTION:DISPLAY", `DESCRIPTION:${txt(titulo)}`, "END:VALARM",
    "END:VEVENT", "END:VCALENDAR",
  ];
  const url = URL.createObjectURL(new Blob([lineas.join("\r\n") + "\r\n"], { type: "text/calendar;charset=utf-8" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: `aguirre-jornada-${p.jornada}.ics` });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const resultadoClub = (p) => {
  if (!p.finalizado) return null;
  const d = p.local === CLUB ? p.golesLocal - p.golesVisitante : p.golesVisitante - p.golesLocal;
  return d > 0 ? { t: "Victoria", c: "v" } : d < 0 ? { t: "Derrota", c: "d" } : { t: "Empate", c: "e" };
};

/* ---------- Estado ---------- */

let datos = {};              // jornada -> { noDisp: [], conv: [] }
let esEntrenadora = sessionStorage.getItem("entrenadora") === "1";
const abiertos = new Set();  // jornadas desplegadas
let jugadosAbierto = false;
let editarOtras = false;     // familia: permitir tocar a jugadoras que no son la suya
let vista = "partidos";
let inicial = true;

const CLAVE_MIA = "aguirre-mi-jugadora-2627";
let mia = (() => {
  try { const v = localStorage.getItem(CLAVE_MIA); return JUGADORAS.includes(v) ? v : ""; } catch { return ""; }
})();

let entrenos = {};           // fecha ISO -> { asisten: [], cancelado: bool }
const entrAbiertos = new Set();
let entrInicial = true;
const notasBorrador = {};    // fecha -> nota en edición aún sin guardar
const NOTAS_MAX = 1000;
let entrVisibles = 4;        // sesiones mostradas en la lista (se amplía de 4 en 4)
let asistRango = "todo";     // resumen de asistencia: "todo" | "semana" (últimos 7 días)

const proximo = PARTIDOS.find((p) => p.fecha >= hoyISO()) || null;

const borradores = {};       // jornada -> convocatoria en edición (sin publicar)
const sinPublicar = (j) => {
  if (!borradores[j]) return false;
  const a = borradores[j].join("|"), b = estadoDe(j).conv.join("|");
  return a !== b;
};

const estadoDe = (j) => {
  const d = datos[j] || {};
  const noDisp = new Set(d.noDisp || []);
  const disponibles = JUGADORAS.filter((n) => !noDisp.has(n));
  const conv = JUGADORAS.filter((n) => (d.conv || []).includes(n) && !noDisp.has(n));
  return { noDisp, disponibles, conv };
};

/* ---------- Render ---------- */

function chip({ nombre, j, tipo, marcado, soloLectura, esMia, bloqueada }) {
  const clase = tipo === "disp" ? (marcado ? "on" : "off") : marcado ? "conv" : "";
  return `<li class="chip ${clase}${soloLectura ? " solo" : ""}${esMia ? " mia" : ""}${bloqueada ? " bloqueada" : ""}"><label>
    <input type="checkbox" data-tipo="${tipo}" data-j="${j}" data-n="${esc(nombre)}" ${marcado ? "checked" : ""} ${soloLectura ? "disabled" : ""}>
    <span class="ini" aria-hidden="true">${esc(nombre.charAt(0).toUpperCase())}</span>
    <span class="nombre">${esc(nombre)}</span>${esMia ? '<span class="mia-tag">Mía</span>' : ""}</label></li>`;
}

const ICONO_PIN = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>`;
const ICONO_CHEVRON = `<svg class="chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>`;
const ICONO_CAL = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>`;

function tarjeta(p) {
  const estado = estadoDe(p.jornada);
  const { noDisp, disponibles } = estado;
  const editando = esEntrenadora && p.fecha >= hoyISO();
  const conv = editando && borradores[p.jornada]
    ? JUGADORAS.filter((n) => borradores[p.jornada].includes(n) && !noDisp.has(n))
    : estado.conv;
  const dirty = editando && sinPublicar(p.jornada);
  const pasado = p.fecha < hoyISO();
  const esProx = proximo && proximo.jornada === p.jornada;
  const abierto = abiertos.has(p.jornada);
  const pocas = !pasado && disponibles.length < MIN_JUGADORAS;
  const res = resultadoClub(p);
  const suspendido = !!p.suspendido; // Estado «S» del CSV: se quita solo al reprogramarse
  const resHtml = (res ? `<span class="res ${res.c}">${res.t}</span>` : "") + (suspendido ? '<span class="suspendido">Suspendido</span>' : "");
  const mapa = p.instalacion
    ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(p.instalacion + " Madrid")}`
    : null;
  const equipo = (n) => (n === CLUB ? `<span class="aguirre">${n}</span>` : esc(n));

  // Disponibilidad: la familia solo toca a su jugadora (salvo que desbloquee al resto); los partidos jugados no se editan.
  const bloquearOtras = !esEntrenadora && !pasado && (!mia || !editarOtras);
  const orden = mia ? [mia, ...JUGADORAS.filter((n) => n !== mia)] : JUGADORAS;
  const ayudaDisp = pasado
    ? "Partido jugado: ya no se puede modificar."
    : esEntrenadora ? "Desmarca a la jugadora que no pueda acudir"
    : mia ? (editarOtras ? "Desmarca a la jugadora que no pueda acudir" : "Solo puedes cambiar a tu jugadora")
    : "Elige «Mi jugadora» arriba para poder indicar la disponibilidad.";
  const btnOtras = !esEntrenadora && !pasado && mia
    ? `<div class="acciones"><button class="btn btn-ghost" data-accion="otras" data-j="${p.jornada}" type="button" aria-pressed="${editarOtras}">${editarOtras ? "Volver a bloquear al resto" : "Editar otras jugadoras"}</button></div>` : "";
  const bloqueDisp = `
    <h3>Disponibilidad <small>${pocas ? '<span class="aviso">Pocas jugadoras</span> ' : ""}${disponibles.length} de ${JUGADORAS.length} pueden ir</small></h3>
    <ul class="chips">${orden.map((n) => {
      const esMia = n === mia && !esEntrenadora;
      const lock = pasado || (bloquearOtras && n !== mia);
      return chip({ nombre: n, j: p.jornada, tipo: "disp", marcado: !noDisp.has(n), soloLectura: lock, esMia, bloqueada: lock && !pasado });
    }).join("")}</ul>
    <p class="vacio ayuda">${ayudaDisp}</p>${btnOtras}`;

  let bloqueConv;
  if (esEntrenadora && !pasado) {
    bloqueConv = `
      <h3>Convocatoria <small>${conv.length} convocadas</small></h3>
      <ul class="chips">${disponibles.map((n) => chip({ nombre: n, j: p.jornada, tipo: "conv", marcado: conv.includes(n) })).join("")}</ul>
      <div class="acciones">
        <button class="btn" data-accion="guardar" data-j="${p.jornada}" type="button" ${dirty ? "" : "disabled"}>Guardar convocatoria</button>
        <button class="btn btn-ghost" data-accion="todas" data-j="${p.jornada}" type="button">Convocar a todas</button>
        <button class="btn btn-ghost" data-accion="ninguna" data-j="${p.jornada}" type="button">Quitar todas</button>
        <button class="btn" data-accion="copiar" data-j="${p.jornada}" type="button">Copiar para WhatsApp</button>
      </div>
      <p class="vacio ayuda" role="status">${dirty ? "Cambios sin publicar: las familias aún no los ven." : "Las familias ven la convocatoria guardada."}</p>`;
  } else {
    bloqueConv = `
      <h3>Convocatoria <small>${conv.length} convocadas</small></h3>
      ${conv.length
        ? `<ul class="convocadas-lectura">${conv.map((n) => `<li><span class="ini" aria-hidden="true">${esc(n.charAt(0).toUpperCase())}</span>${esc(n)}</li>`).join("")}</ul>`
        : `<p class="vacio">${pasado ? "No se publicó convocatoria." : "La entrenadora aún no ha publicado la convocatoria."}</p>`}`;
  }

  const sede = p.local === CLUB ? "Local" : "Visitante";
  // Con resultado: una línea por equipo y los goles en una casilla con fondo propio
  const fila = (n, g) => `<span class="fila-eq"><span class="nom">${equipo(n)}</span><b class="goles">${g}</b></span>`;
  const cruce = p.finalizado
    ? `<div class="cruce con-resultado" role="group" aria-label="Resultado: ${esc(p.local)} ${p.golesLocal}, ${esc(p.visitante)} ${p.golesVisitante}">${fila(p.local, p.golesLocal)}${fila(p.visitante, p.golesVisitante)}</div>`
    : `<div class="cruce">${equipo(p.local)} <span class="vs">${esProx ? "— vs —" : "vs"}</span> ${equipo(p.visitante)}</div>`;
  const hora = p.hora ? p.hora + " h" : "Hora por confirmar";
  let resumen;
  if (esProx) {
    const f = fechaCorta(p.fecha);
    const miCamiseta = p.local === CLUB ? p.camisetaLocal : p.camisetaVisitante;
    resumen = `
      <div class="meta"><span class="etiqueta">Próximo partido</span><span>Jornada ${p.jornada}</span>${resHtml}</div>
      ${ICONO_CHEVRON}
      <div class="destacado-fecha"><span class="sr-only">${esc(fechaLarga(p.fecha))}, ${hora}</span>
        <b aria-hidden="true">${f.num}</b>
        <span class="destacado-dm" aria-hidden="true"><span>${esc(f.dia)}<br>${esc(f.mes)}</span><span class="destacado-hora">${hora}</span></span></div>
      ${cruce}
      <div class="destacado-lugar">${ICONO_PIN}<span>${p.instalacion ? "Campo: " + esc(p.instalacion) : "Instalación por confirmar"} · ${sede}${miCamiseta ? ` · camiseta ${esc(miCamiseta.toLowerCase())}` : ""}</span></div>
      <div class="disp-barra"><div class="disp-texto"><span>${pocas ? '<span class="aviso">Pocas jugadoras</span>' : "Disponibles"}</span><b>${disponibles.length} de ${JUGADORAS.length}</b></div>
        <div class="segmentos${pocas ? " baja" : ""}" style="--n:${JUGADORAS.length}" aria-hidden="true">${JUGADORAS.map((_, i) => `<span${i < disponibles.length ? ' class="on"' : ""}></span>`).join("")}</div></div>
      <span class="ver-conv">Ver convocatoria</span>`;
  } else {
    const f = fechaCorta(p.fecha);
    resumen = `
      <div class="fecha-bloque" aria-hidden="true"><span>${esc(f.dia)}</span><b>${f.num}</b><span>${esc(f.mes)}</span></div>
      <div class="partido-info">
        ${cruce}
        <div class="meta"><span class="j">Jornada ${p.jornada}</span><span>${fechaLarga(p.fecha)}</span><span>${hora}</span><span class="sede ${sede === "Local" ? "local" : ""}">${sede}</span>${resHtml}${pocas ? '<span class="aviso">Pocas jugadoras</span>' : ""}</div>
      </div>
      ${ICONO_CHEVRON}`;
  }

  return `
  <details class="partido${pasado ? " pasado" : ""}${esProx ? " proximo" : ""}" data-j="${p.jornada}" ${abierto ? "open" : ""}>
    <summary>${resumen}</summary>
    <div class="cuerpo">
      <p class="lugar">${ICONO_PIN}<span class="lugar-txt">${p.instalacion
        ? `Campo: ${esc(p.instalacion)}<a href="${mapa}" target="_blank" rel="noopener">Ver mapa</a>`
        : "Instalación por confirmar"}</span></p>
      ${pasado ? "" : `<div class="acciones-partido"><button class="btn btn-ghost btn-ics" data-accion="ics" data-j="${p.jornada}" type="button">${ICONO_CAL}Añadir al calendario</button></div>`}
      <div class="camisetas">
        <h3>Camisetas</h3>
        <p><span class="quien">${esc(p.local)}</span>${camiseta(p.camisetaLocal) || '<span class="camiseta">Por confirmar</span>'}</p>
        <p><span class="quien">${esc(p.visitante)}</span>${camiseta(p.camisetaVisitante) || '<span class="camiseta">Por confirmar</span>'}</p>
      </div>
      ${bloqueConv}
      ${bloqueDisp}
    </div>
  </details>`;
}

/* Entrenadora: cuadro jugadoras × jornadas con las convocatorias guardadas */
function bloqueEstadistica() {
  const cols = PARTIDOS.map((p) => ({ p, conv: estadoDe(p.jornada).conv }));
  const publicadas = cols.filter((c) => c.conv.length).length;
  const cabecera = cols.map((c) => `<th scope="col" title="${esc(fechaLarga(c.p.fecha))}">J${c.p.jornada}</th>`).join("");
  const filas = JUGADORAS.map((n) => {
    let veces = 0;
    const celdas = cols.map((c) => {
      if (!c.conv.length) return `<td class="sin"><span aria-hidden="true">·</span><span class="sr-only">Sin convocatoria</span></td>`;
      if (c.conv.includes(n)) { veces++; return `<td class="si"><span aria-hidden="true">✓</span><span class="sr-only">Convocada</span></td>`; }
      return `<td class="no"><span aria-hidden="true">✗</span><span class="sr-only">No convocada</span></td>`;
    }).join("");
    return `<tr><th scope="row">${esc(n)}</th>${celdas}<td class="total">${veces}</td></tr>`;
  }).join("");
  return `<h2 class="seccion">Convocatorias por jugadora <small>${publicadas} ${publicadas === 1 ? "jornada" : "jornadas"} con lista</small></h2>
    <div class="cuadro-scroll" tabindex="0" role="region" aria-label="Cuadro de convocatorias por jugadora y jornada">
      <table class="cuadro"><thead><tr><th scope="col">Jugadora</th>${cabecera}<th scope="col">Total</th></tr></thead><tbody>${filas}</tbody></table>
    </div>
    <p class="vacio ayuda">✓ convocada · ✗ no convocada · · sin lista publicada aún</p>`;
}

/* Entrenadora: registro de asistencia a los entrenamientos (lunes y miércoles desde INICIO_ENTRENAMIENTOS) */
const DIAS_ENTRENO = window.DIAS_ENTRENAMIENTO || [1, 3];
function sesionesEntreno() {
  const ini = window.INICIO_ENTRENAMIENTOS, hoy = hoyISO(), out = [];
  if (!ini) return out;
  for (const d = new Date(ini + "T12:00:00"); ; d.setDate(d.getDate() + 1)) {
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    if (iso > hoy) break;
    if (DIAS_ENTRENO.includes(d.getDay())) out.push(iso);
  }
  return out.reverse();   // la más reciente primero
}
// Una sesión cuenta cuando se ha pasado lista (existe el campo asisten) y no está marcada «sin entrenamiento»
const entrenoContado = (f) => { const d = entrenos[f]; return !!d && Array.isArray(d.asisten) && !d.cancelado; };

function bloqueAsistencia() {
  const sesiones = sesionesEntreno();
  if (!sesiones.length) {
    const ini = window.INICIO_ENTRENAMIENTOS;
    return `<h2 class="seccion">Asistencia a entrenamientos</h2>
      <p class="vacio">${ini ? `El registro empieza el ${esc(fechaLarga(ini))}.` : "Aún no hay entrenamientos configurados."}</p>`;
  }
  if (entrInicial) { entrInicial = false; entrAbiertos.add(sesiones[0]); }
  const desde = new Date(hoyISO() + "T12:00:00"); desde.setDate(desde.getDate() - 6);
  const desdeISO = `${desde.getFullYear()}-${String(desde.getMonth() + 1).padStart(2, "0")}-${String(desde.getDate()).padStart(2, "0")}`;
  const contadas = sesiones.filter((f) => entrenoContado(f) && (asistRango === "todo" || f >= desdeISO));
  const resumen = JUGADORAS.map((n) => {
    const veces = contadas.filter((f) => entrenos[f].asisten.includes(n)).length;
    return { n, veces, pct: contadas.length ? Math.round((veces / contadas.length) * 100) : null };
  });
  const filas = resumen.map((r) => `<tr><th scope="row">${esc(r.n)}</th>
      <td class="total">${r.veces}/${contadas.length}</td>
      <td class="${r.pct === null ? "sin" : r.pct >= 75 ? "si" : r.pct < 50 ? "no" : ""}">${r.pct === null ? "·" : r.pct + " %"}</td></tr>`).join("");
  const tarjetaSesion = (f) => {
    const d = entrenos[f] || {};
    const cancelado = !!d.cancelado, lista = Array.isArray(d.asisten);
    const asisten = new Set(d.asisten || []);
    const fc = fechaCorta(f);
    const nota = f in notasBorrador ? notasBorrador[f] : (d.notas || "");
    const notaSucia = nota.trim() !== (d.notas || "");
    const estado = cancelado ? "Sin entrenamiento" : lista ? `${asisten.size}/${JUGADORAS.length} asistentes` : "Pendiente de pasar lista";
    return `<details class="partido pasado sesion" data-f="${f}" ${entrAbiertos.has(f) ? "open" : ""}>
      <summary>
        <div class="fecha-bloque" aria-hidden="true"><span>${esc(fc.dia)}</span><b>${fc.num}</b><span>${esc(fc.mes)}</span></div>
        <div class="partido-info"><div class="cruce">Entrenamiento</div>
          <div class="meta"><span>${esc(fechaLarga(f))}</span><span class="${cancelado ? "" : lista ? "res v" : "aviso"}">${estado}</span>${d.notas ? '<span class="res">Con nota</span>' : ""}</div></div>
        ${ICONO_CHEVRON}
      </summary>
      <div class="cuerpo">
        <h3>Asistencia <small>${cancelado ? "no cuenta en el porcentaje" : `${asisten.size} de ${JUGADORAS.length}`}</small></h3>
        <ul class="chips">${JUGADORAS.map((n) => `<li class="chip ${asisten.has(n) ? "conv" : ""}${cancelado ? " solo bloqueada" : ""}"><label>
          <input type="checkbox" data-f="${f}" data-n="${esc(n)}" ${asisten.has(n) ? "checked" : ""} ${cancelado ? "disabled" : ""}>
          <span class="ini" aria-hidden="true">${esc(n.charAt(0).toUpperCase())}</span><span class="nombre">${esc(n)}</span></label></li>`).join("")}</ul>
        <div class="acciones">
          ${cancelado ? "" : `<button class="btn" data-accion="todas" data-f="${f}" type="button">Marcar todas</button>
          <button class="btn btn-ghost" data-accion="ninguna" data-f="${f}" type="button">Quitar todas</button>`}
          <button class="btn btn-ghost" data-accion="sin-entreno" data-f="${f}" type="button" aria-pressed="${cancelado}">${cancelado ? "Hubo entrenamiento" : "Sin entrenamiento"}</button>
        </div>
        <p class="vacio ayuda">${cancelado ? "Esta sesión no cuenta (festivo, partido, pabellón cerrado…)." : "Cada cambio se guarda al momento."}</p>
        <h3><label for="nota-${f}">Notas del entrenamiento</label></h3>
        <textarea id="nota-${f}" class="nota" data-f="${f}" rows="3" maxlength="${NOTAS_MAX}" placeholder="Ejercicios, lesiones, avisos, quién llegó tarde…">${esc(nota)}</textarea>
        <div class="acciones">
          <button class="btn" data-accion="guardar-nota" data-f="${f}" type="button" ${notaSucia ? "" : "disabled"}>Guardar nota</button>
          <span class="nota-estado vacio" role="status">${notaSucia ? "Nota sin guardar" : d.notas ? "Nota guardada" : ""}</span>
        </div>
      </div>
    </details>`;
  };
  const filtro = `<div class="filtro" role="group" aria-label="Periodo del resumen">
      <button type="button" class="btn btn-ghost" data-rango="todo" aria-pressed="${asistRango === "todo"}">Toda la temporada</button>
      <button type="button" class="btn btn-ghost" data-rango="semana" aria-pressed="${asistRango === "semana"}">Última semana</button></div>`;
  return `<h2 class="seccion">Asistencia por jugadora <small>${contadas.length} ${contadas.length === 1 ? "sesión" : "sesiones"} con lista</small></h2>
    ${filtro}
    <div class="cuadro-scroll" tabindex="0" role="region" aria-label="Asistencia acumulada por jugadora">
      <table class="cuadro"><thead><tr><th scope="col">Jugadora</th><th scope="col">Asistió</th><th scope="col">%</th></tr></thead><tbody>${filas}</tbody></table>
    </div>
    <p class="vacio ayuda">${asistRango === "semana" ? "Últimos 7 días. " : ""}Solo cuentan las sesiones con lista guardada y no marcadas como «sin entrenamiento».</p>
    <h2 class="seccion">Entrenamientos <small>lunes y miércoles</small></h2>
    ${sesiones.slice(0, entrVisibles).map(tarjetaSesion).join("")}
    ${sesiones.length > entrVisibles
      ? `<div class="acciones"><button class="btn btn-ghost" type="button" data-mas="1">Cargar las 4 siguientes <small>(${sesiones.length - entrVisibles} más)</small></button></div>` : ""}`;
}

function renderAsistencia() {
  const cont = document.getElementById("asistencia");
  const a = document.activeElement;
  if (a && a.tagName === "TEXTAREA" && cont.contains(a)) return;   // no pisar lo que se está escribiendo
  const foco = a && cont.contains(a)
    ? (a.dataset.n ? `input[data-f="${a.dataset.f}"][data-n="${CSS.escape(a.dataset.n)}"]`
      : a.dataset.mas ? "[data-mas]"
      : a.dataset.rango ? `[data-rango="${a.dataset.rango}"]`
      : a.dataset.accion ? `[data-accion="${a.dataset.accion}"][data-f="${a.dataset.f}"]`
      : a.tagName === "SUMMARY" ? `details[data-f="${a.parentElement.dataset.f}"] > summary` : null)
    : null;
  const y = window.scrollY;
  cont.innerHTML = esEntrenadora ? bloqueAsistencia() : "";
  window.scrollTo(0, y);
  if (foco) cont.querySelector(foco)?.focus({ preventScroll: true });
}

/* Selector de elemento enfocado, para no perder el foco al repintar */
function selectorFoco(a, cont) {
  if (!a || !cont.contains(a)) return null;
  const d = a.dataset || {};
  if (d.n) return `input[data-tipo="${d.tipo}"][data-j="${d.j}"][data-n="${CSS.escape(d.n)}"]`;
  if (d.accion) return `[data-accion="${d.accion}"][data-j="${d.j}"]`;
  if (a.tagName === "SUMMARY") {
    const p = a.parentElement;
    if (p.dataset.j) return `details[data-j="${p.dataset.j}"] > summary`;
    if (p.dataset.grupo) return `details[data-grupo="${p.dataset.grupo}"] > summary`;
  }
  return null;
}

function actualizarCabecera() {
  const partidos = vista === "partidos";
  estEl.parentElement.hidden = !partidos;
  document.getElementById("mi-fila").hidden = !partidos || esEntrenadora;
}

function render() {
  const cont = document.getElementById("lista");
  const y = window.scrollY;
  const foco = selectorFoco(document.activeElement, cont);
  const hoy = hoyISO();
  const futuros = PARTIDOS.filter((p) => p !== proximo && p.fecha >= hoy);
  const jugados = PARTIDOS.filter((p) => p.fecha < hoy).reverse();
  cont.innerHTML =
    (proximo ? `<h2 class="sr-only">Próximo partido</h2>${tarjeta(proximo)}` : "") +
    (futuros.length ? `<h2 class="seccion">Calendario<span class="cinta-rep" aria-hidden="true">${"✦ Calendario ".repeat(6)}</span></h2>${futuros.map(tarjeta).join("")}` : "") +
    (jugados.length ? `<details class="jugados" data-grupo="jugados" ${jugadosAbierto ? "open" : ""}>
      <summary>Partidos jugados <small>${jugados.length}</small>${ICONO_CHEVRON}</summary>
      <div class="jugados-lista">${jugados.map(tarjeta).join("")}</div></details>` : "") +
    "";
  document.getElementById("convocatorias").innerHTML = esEntrenadora ? bloqueEstadistica() : "";
  renderAsistencia();
  document.getElementById("tab-conv").hidden = !esEntrenadora;
  document.getElementById("tab-asist").hidden = !esEntrenadora;
  if (!esEntrenadora && (vista === "convocatorias" || vista === "asistencia")) mostrarVista("partidos");
  window.scrollTo(0, y);
  const b = document.getElementById("btn-entrenadora");
  const etq = esEntrenadora ? "Salir del modo entrenadora" : "Acceso entrenadora";
  b.setAttribute("aria-label", etq); b.title = etq;
  b.setAttribute("aria-pressed", esEntrenadora);
  b.classList.toggle("activo", esEntrenadora);
  document.getElementById("pill-ent").hidden = !esEntrenadora;
  actualizarCabecera();
  if (inicial && proximo) {
    inicial = false;
    abiertos.add(proximo.jornada);
    cont.querySelector(`[data-j="${proximo.jornada}"]`)?.setAttribute("open", "");
  }
  if (foco) cont.querySelector(foco)?.focus({ preventScroll: true });
}

/* ---------- Mi jugadora ---------- */

const selMia = document.getElementById("mi-jugadora");
selMia.innerHTML = `<option value="">Sin elegir</option>` +
  JUGADORAS.map((n) => `<option value="${esc(n)}"${n === mia ? " selected" : ""}>${esc(n)}</option>`).join("");
selMia.addEventListener("change", () => {
  mia = selMia.value; editarOtras = false;
  try { mia ? localStorage.setItem(CLAVE_MIA, mia) : localStorage.removeItem(CLAVE_MIA); } catch {}
  render();
});

/* ---------- Eventos ---------- */

const lista = document.getElementById("lista");
let store;

lista.addEventListener("toggle", (e) => {
  const t = e.target;
  if (t.dataset?.grupo === "jugados") { jugadosAbierto = t.open; return; }
  const j = Number(t.dataset?.j);
  if (!j) return;
  t.open ? abiertos.add(j) : abiertos.delete(j);
}, true);

lista.addEventListener("change", async (e) => {
  const el = e.target;
  if (el.type !== "checkbox") return;
  const j = Number(el.dataset.j), n = el.dataset.n;
  if (el.dataset.tipo === "disp" && !esEntrenadora && !mia) {
    el.checked = !el.checked; toast("Elige «Mi jugadora» primero"); return;
  }
  try {
    if (el.dataset.tipo === "disp") {
      await store.setDisponible(j, n, el.checked);
      // si deja de estar disponible, tampoco puede estar convocada
      if (!el.checked && estadoDe(j).conv.includes(n)) {
        await store.setConvocadas(j, estadoDe(j).conv.filter((x) => x !== n));
      }
      if (!el.checked && borradores[j]) borradores[j] = borradores[j].filter((x) => x !== n);
    } else if (esEntrenadora) {
      const s = new Set(borradores[j] || estadoDe(j).conv);
      el.checked ? s.add(n) : s.delete(n);
      borradores[j] = JUGADORAS.filter((x) => s.has(x));
      render();
      return;
    }
    guardado();
  } catch (err) {
    console.error(err);
    toast("No se pudo guardar. Revisa la conexión.");
    render();
  }
});

lista.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-accion]");
  if (!b) return;
  const j = Number(b.dataset.j), acc = b.dataset.accion;
  const p = PARTIDOS.find((x) => x.jornada === j);
  if (acc === "ics") { descargarIcs(p); return; }
  if (acc === "otras") { editarOtras = !editarOtras; render(); return; }
  if (!esEntrenadora) return;
  const { disponibles, conv } = estadoDe(j);
  if (acc === "todas") { borradores[j] = disponibles; render(); return; }
  if (acc === "ninguna") { borradores[j] = []; render(); return; }
  if (acc === "guardar") {
    try {
      await store.setConvocadas(j, borradores[j] || conv);
      delete borradores[j];
      render(); guardado();
    } catch (err) {
      console.error(err); toast("No se pudo guardar. Revisa la conexión.");
    }
    return;
  }
  if (acc === "copiar") {
    if (sinPublicar(j)) { toast("Guarda la convocatoria antes de copiarla"); return; }
    const txt = `⚽ Convocatoria Jornada ${j}\n${p.local} vs ${p.visitante}\n${fechaLarga(p.fecha)}${p.hora ? " · " + p.hora + " h" : ""}\n${p.instalacion || ""}\n\n` +
      (conv.length ? conv.map((n) => "• " + n).join("\n") : "(sin convocar)");
    try { await navigator.clipboard.writeText(txt); toast("Convocatoria copiada"); }
    catch { toast("No se pudo copiar"); }
  }
});

const asistenciaEl = document.getElementById("asistencia");
asistenciaEl.addEventListener("toggle", (e) => {
  const f = e.target.dataset?.f;
  if (f) e.target.open ? entrAbiertos.add(f) : entrAbiertos.delete(f);
}, true);
asistenciaEl.addEventListener("input", (e) => {
  if (!e.target.matches("textarea.nota")) return;
  const f = e.target.dataset.f;
  notasBorrador[f] = e.target.value;
  const sucia = e.target.value.trim() !== ((entrenos[f] || {}).notas || "");
  const cuerpo = e.target.closest(".cuerpo");
  cuerpo.querySelector('[data-accion="guardar-nota"]').disabled = !sucia;
  cuerpo.querySelector(".nota-estado").textContent = sucia ? "Nota sin guardar" : ((entrenos[f] || {}).notas ? "Nota guardada" : "");
});
asistenciaEl.addEventListener("change", async (e) => {
  const el = e.target;
  if (!esEntrenadora || el.type !== "checkbox" || !el.dataset.f) return;
  try { await store.setAsistencia(el.dataset.f, el.dataset.n, el.checked); guardado(); }
  catch (err) { console.error(err); toast("No se pudo guardar. Revisa la conexión."); renderAsistencia(); }
});
asistenciaEl.addEventListener("click", async (e) => {
  const r = e.target.closest("[data-rango]");
  if (e.target.closest("[data-mas]")) { entrVisibles += 4; renderAsistencia(); return; }
  if (r) { asistRango = r.dataset.rango; renderAsistencia(); return; }
  const b = e.target.closest("[data-accion]");
  if (!b || !esEntrenadora) return;
  const f = b.dataset.f, acc = b.dataset.accion;
  try {
    if (acc === "guardar-nota") {
      const t = asistenciaEl.querySelector(`textarea.nota[data-f="${f}"]`);
      await store.setNotas(f, t.value.trim());
      delete notasBorrador[f];
      renderAsistencia();
    }
    else if (acc === "todas") await store.setAsistentes(f, [...JUGADORAS]);
    else if (acc === "ninguna") await store.setAsistentes(f, []);
    else if (acc === "sin-entreno") await store.setSinEntreno(f, !(entrenos[f] || {}).cancelado);
    else return;
    guardado();
  } catch (err) { console.error(err); toast("No se pudo guardar. Revisa la conexión."); }
});

/* PIN entrenadora */
const dlg = document.getElementById("dlg-pin");
const pinInput = document.getElementById("pin");
const pinError = document.getElementById("pin-error");

document.getElementById("btn-entrenadora").addEventListener("click", () => {
  if (esEntrenadora) {
    esEntrenadora = false; for (const k in borradores) delete borradores[k]; sessionStorage.removeItem("entrenadora"); render(); return;
  }
  pinInput.value = ""; pinError.hidden = true; dlg.showModal(); pinInput.focus();
});
document.getElementById("pin-cancel").addEventListener("click", () => dlg.close());
document.getElementById("form-pin").addEventListener("submit", (e) => {
  if (pinInput.value.trim() === window.PIN_ENTRENADORA) {
    esEntrenadora = true; sessionStorage.setItem("entrenadora", "1"); render();
    toast("Modo entrenadora activado");
  } else {
    e.preventDefault(); pinError.hidden = false; pinInput.select();
  }
});

/* ---------- Clasificación y pestañas ---------- */

function renderClasificacion() {
  const cont = document.getElementById("clasificacion");
  if (!CLASIFICACION.length) { cont.innerHTML = '<h2 class="sr-only">Clasificación</h2><p class="vacio">La clasificación aún no está disponible.</p>'; return; }
  const sinJugar = CLASIFICACION.every((e) => e.pj === 0);
  const filas = CLASIFICACION.map((e) => `
    <tr class="${e.equipo.startsWith(CLUB) ? "es-club" : ""}">
      <td class="pos">${e.pos}</td><th scope="row">${esc(e.equipo)}</th>
      <td class="pts">${e.pts}</td><td>${e.pj}</td><td>${e.g}</td><td>${e.e}</td><td>${e.p}</td>
      <td>${e.gf}</td><td>${e.gc}</td><td>${e.gf - e.gc > 0 ? "+" : ""}${e.gf - e.gc}</td>
    </tr>`).join("");
  const mio = CLASIFICACION.find((e) => e.equipo.startsWith(CLUB));
  const resumenClub = mio ? `
    <div class="club-resumen"><b>${mio.pos}<sup>º</sup></b>
      <span class="club-datos"><strong>${esc(mio.equipo)}</strong><span class="club-chip">${mio.pts} puntos · ${mio.pj} jugados</span></span></div>` : "";
  cont.innerHTML = `<h2 class="sr-only">Clasificación</h2>` + resumenClub + `
    <div class="tabla-wrap"><table class="tabla">
      <caption class="sr-only">Clasificación del grupo</caption>
      <thead><tr><th scope="col">#</th><th scope="col">Equipo</th><th scope="col" title="Puntos">Pts</th>
        <th scope="col" title="Jugados">PJ</th><th scope="col" title="Ganados">G</th><th scope="col" title="Empatados">E</th>
        <th scope="col" title="Perdidos">P</th><th scope="col" title="Goles a favor">GF</th>
        <th scope="col" title="Goles en contra">GC</th><th scope="col" title="Diferencia de goles">DG</th></tr></thead>
      <tbody>${filas}</tbody>
    </table></div>
    <p class="vacio ayuda">${sinJugar ? "Aún no se ha jugado ninguna jornada. " : ""}Victoria 3 puntos, empate 1.${LIGA.actualizado ? ` Datos actualizados el ${esc(LIGA.actualizado)}.` : ""}</p>`;
}

function mostrarVista(v, enfocar) {
  vista = v;
  document.getElementById("lista").hidden = v !== "partidos";
  document.getElementById("clasificacion").hidden = v !== "clasificacion";
  document.getElementById("normas").hidden = v !== "normas";
  document.getElementById("convocatorias").hidden = v !== "convocatorias";
  document.getElementById("asistencia").hidden = v !== "asistencia";
  actualizarCabecera();
  document.querySelectorAll(".tab").forEach((t) => {
    const on = t.dataset.vista === v;
    t.classList.toggle("activa", on);
    t.setAttribute("aria-selected", on);
    t.tabIndex = on ? 0 : -1;
    if (on && enfocar) t.focus();
  });
}
const tabsEl = document.querySelector(".tabs");
tabsEl.addEventListener("click", (e) => {
  const t = e.target.closest(".tab");
  if (t) mostrarVista(t.dataset.vista);
});
tabsEl.addEventListener("keydown", (e) => {
  const tabs = [...document.querySelectorAll(".tab")].filter((t) => !t.hidden);
  const i = tabs.findIndex((t) => t.dataset.vista === vista);
  const nuevo = { ArrowRight: (i + 1) % tabs.length, ArrowLeft: (i - 1 + tabs.length) % tabs.length, Home: 0, End: tabs.length - 1 }[e.key];
  if (nuevo === undefined) return;
  e.preventDefault();
  mostrarVista(tabs[nuevo].dataset.vista, true);
});
renderClasificacion();

/* ---------- Arranque ---------- */

(async function init() {
  store = await crearStore();
  if (store.modo === "local") setBase("Modo local: los cambios solo se guardan en este dispositivo", "local");
  render();
  store.suscribir((d, err) => {
    if (err) { setBase("Sin conexión con la base de datos", "error"); return; }
    if (store.modo === "nube" && base.cls === "error") setBase("", "");
    datos = d || {};
    render();
  });
  store.suscribirEntrenos((d) => {
    if (d) entrenos = d;
    renderAsistencia();
  });
})();

/* ---------- Tema claro/oscuro ---------- */

const btnTema = document.getElementById("btn-tema");
const temaActual = () => document.documentElement.dataset.theme || "dark"; // el diseño por defecto es el oscuro
function etiquetaTema() {
  const q = temaActual() === "dark" ? "Cambiar a modo claro" : "Cambiar a modo oscuro";
  btnTema.setAttribute("aria-label", q); btnTema.title = q;
}
btnTema.addEventListener("click", () => {
  const nuevo = temaActual() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = nuevo;
  try { localStorage.setItem("aguirre-tema", nuevo); } catch {}
  etiquetaTema();
});
etiquetaTema();
