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
  };
}

/* ---------- Utilidades ---------- */

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
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

/* ---------- Estado ---------- */

let datos = {};              // jornada -> { noDisp: [], conv: [] }
let esEntrenadora = sessionStorage.getItem("entrenadora") === "1";
const abiertos = new Set();  // jornadas desplegadas
let inicial = true;

const proximo = PARTIDOS.find((p) => p.fecha >= hoyISO()) || null;

const estadoDe = (j) => {
  const d = datos[j] || {};
  const noDisp = new Set(d.noDisp || []);
  const disponibles = JUGADORAS.filter((n) => !noDisp.has(n));
  const conv = JUGADORAS.filter((n) => (d.conv || []).includes(n) && !noDisp.has(n));
  return { noDisp, disponibles, conv };
};

/* ---------- Render ---------- */

function chip({ nombre, j, tipo, marcado, soloLectura }) {
  const clase = tipo === "disp" ? (marcado ? "on" : "off") : marcado ? "conv" : "";
  return `<li class="chip ${clase}${soloLectura ? " solo" : ""}"><label>
    <input type="checkbox" data-tipo="${tipo}" data-j="${j}" data-n="${esc(nombre)}" ${marcado ? "checked" : ""} ${soloLectura ? "disabled" : ""}>
    <span class="ini" aria-hidden="true">${esc(nombre.charAt(0).toUpperCase())}</span>
    <span class="nombre">${esc(nombre)}</span></label></li>`;
}

const ICONO_PIN = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>`;
const ICONO_CHEVRON = `<svg class="chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>`;

function tarjeta(p) {
  const { noDisp, disponibles, conv } = estadoDe(p.jornada);
  const pasado = p.fecha < hoyISO();
  const esProx = proximo && proximo.jornada === p.jornada;
  const abierto = abiertos.has(p.jornada);
  const mapa = p.instalacion
    ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(p.instalacion + " Madrid")}`
    : null;
  const equipo = (n) => (n === CLUB ? `<span class="aguirre">${n}</span>` : esc(n));

  const bloqueDisp = `
    <h3>Disponibilidad <small>${disponibles.length} de ${JUGADORAS.length} pueden ir</small></h3>
    <ul class="chips">${JUGADORAS.map((n) => chip({ nombre: n, j: p.jornada, tipo: "disp", marcado: !noDisp.has(n) })).join("")}</ul>
    <p class="vacio ayuda">Desmarca a la jugadora que no pueda acudir</p>`;

  let bloqueConv;
  if (esEntrenadora) {
    bloqueConv = `
      <h3>Convocatoria <small>${conv.length} convocadas</small></h3>
      <ul class="chips">${disponibles.map((n) => chip({ nombre: n, j: p.jornada, tipo: "conv", marcado: conv.includes(n) })).join("")}</ul>
      <div class="acciones">
        <button class="btn btn-ghost" data-accion="todas" data-j="${p.jornada}" type="button">Convocar a todas</button>
        <button class="btn btn-ghost" data-accion="ninguna" data-j="${p.jornada}" type="button">Quitar todas</button>
        <button class="btn" data-accion="copiar" data-j="${p.jornada}" type="button">Copiar para WhatsApp</button>
      </div>`;
  } else {
    bloqueConv = `
      <h3>Convocatoria <small>${conv.length} convocadas</small></h3>
      ${conv.length
        ? `<ul class="convocadas-lectura">${conv.map((n) => `<li><span class="ini" aria-hidden="true">${esc(n.charAt(0).toUpperCase())}</span>${esc(n)}</li>`).join("")}</ul>`
        : `<p class="vacio">La entrenadora aún no ha publicado la convocatoria.</p>`}`;
  }

  return `
  <details class="partido${pasado ? " pasado" : ""}${esProx ? " proximo" : ""}" data-j="${p.jornada}" ${abierto ? "open" : ""}>
    <summary>
      <div class="meta">
        ${esProx ? '<span class="etiqueta">Próximo</span>' : ""}
        <span class="j">Jornada ${p.jornada}</span>
        <span>${fechaLarga(p.fecha)}</span>
        <span>${p.hora ? p.hora + " h" : "Hora por confirmar"}</span>
      </div>
      ${ICONO_CHEVRON}
      <div class="cruce">${equipo(p.local)} <span class="vs">${p.finalizado ? `<b class="marcador">${p.golesLocal} - ${p.golesVisitante}</b>` : "vs"}</span> ${equipo(p.visitante)}</div>
      <div class="resumen"><span><b>${disponibles.length}</b> disponibles</span><span><b>${conv.length}</b> convocadas</span></div>
    </summary>
    <div class="cuerpo">
      <p class="lugar">${ICONO_PIN}<span>${p.instalacion
        ? `${esc(p.instalacion)} · <a href="${mapa}" target="_blank" rel="noopener">Ver mapa</a>`
        : "Instalación por confirmar"}</span></p>
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

function render() {
  const cont = document.getElementById("lista");
  const y = window.scrollY;
  cont.innerHTML = PARTIDOS.map(tarjeta).join("");
  window.scrollTo(0, y);
  const b = document.getElementById("btn-entrenadora");
  b.textContent = esEntrenadora ? "Salir modo entrenadora" : "Soy la entrenadora";
  b.classList.toggle("activo", esEntrenadora);
  if (inicial && proximo) {
    inicial = false;
    abiertos.add(proximo.jornada);
    cont.querySelector(`[data-j="${proximo.jornada}"]`)?.setAttribute("open", "");
  }
}

/* ---------- Eventos ---------- */

const lista = document.getElementById("lista");
let store;

lista.addEventListener("toggle", (e) => {
  const j = Number(e.target.dataset?.j);
  if (!j) return;
  e.target.open ? abiertos.add(j) : abiertos.delete(j);
}, true);

lista.addEventListener("change", async (e) => {
  const el = e.target;
  if (el.type !== "checkbox") return;
  const j = Number(el.dataset.j), n = el.dataset.n;
  try {
    if (el.dataset.tipo === "disp") {
      await store.setDisponible(j, n, el.checked);
      // si deja de estar disponible, tampoco puede estar convocada
      if (!el.checked && estadoDe(j).conv.includes(n)) {
        await store.setConvocadas(j, estadoDe(j).conv.filter((x) => x !== n));
      }
    } else if (esEntrenadora) {
      const s = new Set(estadoDe(j).conv);
      el.checked ? s.add(n) : s.delete(n);
      await store.setConvocadas(j, JUGADORAS.filter((x) => s.has(x)));
    }
  } catch (err) {
    console.error(err);
    toast("No se pudo guardar. Revisa la conexión.");
    render();
  }
});

lista.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-accion]");
  if (!b || !esEntrenadora) return;
  const j = Number(b.dataset.j), { disponibles, conv } = estadoDe(j);
  if (b.dataset.accion === "todas") await store.setConvocadas(j, disponibles);
  if (b.dataset.accion === "ninguna") await store.setConvocadas(j, []);
  if (b.dataset.accion === "copiar") {
    const p = PARTIDOS.find((x) => x.jornada === j);
    const txt = `⚽ Convocatoria Jornada ${j}\n${p.local} vs ${p.visitante}\n${fechaLarga(p.fecha)}${p.hora ? " · " + p.hora + " h" : ""}\n${p.instalacion || ""}\n\n` +
      (conv.length ? conv.map((n) => "• " + n).join("\n") : "(sin convocar)");
    try { await navigator.clipboard.writeText(txt); toast("Convocatoria copiada"); }
    catch { toast("No se pudo copiar"); }
  }
});

/* PIN entrenadora */
const dlg = document.getElementById("dlg-pin");
const pinInput = document.getElementById("pin");
const pinError = document.getElementById("pin-error");

document.getElementById("btn-entrenadora").addEventListener("click", () => {
  if (esEntrenadora) {
    esEntrenadora = false; sessionStorage.removeItem("entrenadora"); render(); return;
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
  if (!CLASIFICACION.length) { cont.innerHTML = '<p class="vacio">La clasificación aún no está disponible.</p>'; return; }
  const sinJugar = CLASIFICACION.every((e) => e.pj === 0);
  const filas = CLASIFICACION.map((e) => `
    <tr class="${e.equipo.startsWith(CLUB) ? "es-club" : ""}">
      <td class="pos">${e.pos}</td><th scope="row">${esc(e.equipo)}</th>
      <td class="pts">${e.pts}</td><td>${e.pj}</td><td>${e.g}</td><td>${e.e}</td><td>${e.p}</td>
      <td>${e.gf}</td><td>${e.gc}</td><td>${e.gf - e.gc > 0 ? "+" : ""}${e.gf - e.gc}</td>
    </tr>`).join("");
  cont.innerHTML = `
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

function mostrarVista(v) {
  const clasif = v === "clasificacion";
  document.getElementById("lista").hidden = clasif;
  document.getElementById("intro").hidden = clasif;
  document.getElementById("clasificacion").hidden = !clasif;
  document.querySelectorAll(".tab").forEach((t) => {
    const on = t.dataset.vista === v;
    t.classList.toggle("activa", on);
    t.setAttribute("aria-selected", on);
  });
}
document.querySelector(".tabs").addEventListener("click", (e) => {
  const t = e.target.closest(".tab");
  if (t) mostrarVista(t.dataset.vista);
});
renderClasificacion();

/* ---------- Arranque ---------- */

(async function init() {
  store = await crearStore();
  const est = document.getElementById("estado");
  if (store.modo === "local") {
    est.textContent = "Modo local: los cambios solo se guardan en este dispositivo";
    est.classList.add("local");
  } else {
    est.textContent = "Sincronizado en tiempo real";
  }
  render();
  store.suscribir((d, err) => {
    if (err) { est.textContent = "Sin conexión con la base de datos"; est.classList.add("local"); return; }
    est.textContent = store.modo === "nube" ? "Sincronizado en tiempo real" : est.textContent;
    est.classList.toggle("local", store.modo === "local");
    datos = d || {};
    // no repintar mientras se está escribiendo el PIN
    render();
  });
})();
