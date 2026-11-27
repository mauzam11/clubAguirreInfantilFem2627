#!/usr/bin/env python3
"""
Lanzador de agentes para el tablero Kanvas.

Kanvas no arranca agentes: es un tablero y los agentes tiran de él. Este script cierra ese hueco. Cada INTERVALO segundos
mira el tablero y, por cada tarea aprobada y lista (estado `todo` con todas sus dependencias en `done`), arranca una
sesión de Claude Code sin interfaz (`claude -p`) que la ejecuta siguiendo la skill de Kanvas.

    python3 scripts/agentes/kanvas_lanzador.py --dry-run --una-vez   # solo muestra qué lanzaría
    python3 scripts/agentes/kanvas_lanzador.py                       # bucle; Ctrl-C para parar
    python3 scripts/agentes/kanvas_lanzador.py --max-paralelo 3 --presupuesto 3

Tipos de tarea (por el prefijo del título):
  - trabajo      → worktree propio `tarea/<ID>` creado desde `main`; el agente NO commitea.
  - «Commit: …»  → commitea la rama `tarea/<ID>` y la fusiona en `main` local con --no-ff (sin push).
  - «Push: …»    → sube `main` a origin (`git push origin main`). Se lanza al aprobarla: la aprobación es la autorización.
Las tareas «commit» y «push» operan sobre el repositorio principal: nunca se ejecutan dos a la vez.
Las tareas del grupo DL («Datos de la liga») no se lanzan solas, salvo las que se titulan «Actualizar datos de la liga…»: esas se
ejecutan como tarea de trabajo (el agente descarga los CSV él mismo en su worktree). Cualquier otra tarea DL se hace en una sesión.
Cuando una tarea de trabajo llega a revisión, el lanzador propone solo sus tareas «Commit: …» y «Push: …» (encadenadas a ella);
quedan como propuestas hasta que las apruebes en el tablero.

Seguridad: los agentes de trabajo y de commit usan scripts/agentes/agente.settings.json (deniega cualquier push y rm -rf).
Los de «Push» usan agente_push.settings.json: solo permiten `git push origin main` (sin -C, sin forzar, sin borrar ramas).
Estado, logs y worktrees van a ~/.kanvas-agentes-aguirre/.
"""
import argparse
import glob
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BOARD_DEFECTO = os.path.join(REPO, "kanvas.json")
CLI = os.path.join(REPO, ".agents", "skills", "kanvas", "kanvas.py")
SKILL = os.path.join(REPO, ".agents", "skills", "kanvas", "SKILL.md")
CLAUDE_MD = os.path.join(REPO, "CLAUDE.md")
SETTINGS = os.path.join(os.path.dirname(__file__), "agente.settings.json")
SETTINGS_PUSH = os.path.join(os.path.dirname(__file__), "agente_push.settings.json")
ESTADO = os.path.expanduser("~/.kanvas-agentes-aguirre")
LOGS, WORKTREES = os.path.join(ESTADO, "logs"), os.path.join(ESTADO, "worktrees")
RAMA_BASE = "main"

SERIALES = ("commit", "push")  # tocan el repositorio principal: de uno en uno
GRUPOS_MANUALES = ("DL",)  # «Datos de la liga»: necesitan los CSV de source/ (ignorados por git, no existen en un worktree); se hacen en sesión
PREFIJO_ACTUALIZAR_LIGA = "actualizar datos de la liga"  # excepción: estas tareas DL sí se lanzan (descargan los CSV en el worktree)


def ahora():
    return datetime.now().strftime("%H:%M:%S")


def log(msg):
    print(f"[{ahora()}] {msg}", flush=True)


def localizar_claude():
    if os.environ.get("CLAUDE_BIN"):
        return os.environ["CLAUDE_BIN"]
    en_path = shutil.which("claude")
    if en_path:
        return en_path
    cands = glob.glob(os.path.expanduser("~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude"))
    if not cands:
        sys.exit("No encuentro el binario de Claude Code. Define CLAUDE_BIN=/ruta/a/claude")
    cands.sort(key=lambda p: [int(x) for x in re.findall(r"\d+", re.search(r"claude-code-([\d.]+)", p).group(1))])
    return cands[-1]


def leer_tablero(board):
    with open(board, encoding="utf-8") as f:
        return json.load(f)["tasks"]


def tipo_tarea(t):
    titulo = t["title"].strip().lower()
    if titulo.startswith("commit:"):
        return "commit"
    if titulo.startswith("push:"):
        return "push"
    return "trabajo"


def es_manual(t):
    """Tarea que el lanzador no coge: grupo manual, salvo «Actualizar datos de la liga…» y su Commit/Push (a demanda)."""
    if t.get("group") not in GRUPOS_MANUALES:
        return False
    titulo = re.sub(r"^(commit|push):\s*", "", t["title"].strip().lower())  # sus «Commit:»/«Push:» de cierre también
    return not titulo.startswith(PREFIJO_ACTUALIZAR_LIGA)


def listas(tareas):
    estado = {t["id"]: t["state"] for t in tareas}
    return sorted(
        [t for t in tareas if t["state"] == "todo" and all(estado.get(d) == "done" for d in (t.get("deps") or []))],
        key=lambda t: (t["id"].split("-")[0], int(t["id"].split("-")[1])),
    )


def cierres_pendientes(tareas):
    """Tareas de trabajo en revisión a las que aún no cuelga ninguna tarea «Commit: …»."""
    con_commit = {d for t in tareas if tipo_tarea(t) == "commit" for d in (t.get("deps") or [])}
    return [
        t for t in tareas
        if t["state"] == "review" and tipo_tarea(t) == "trabajo" and not es_manual(t) and t["id"] not in con_commit
    ]


def propuesta_de_cierre(t):
    """Lote para `kanvas batch`: «Commit: …» (depende de la tarea) y «Push: …» (depende del commit)."""
    tid, titulo, grupo = t["id"], t["title"].strip(), t.get("group") or "-"
    titulo_commit, titulo_push = f"Commit: {titulo}", f"Push: {titulo}"
    return {"tasks": [
        {"title": titulo_commit, "group": grupo, "deps": [tid],
         "desc": f"Cierre de {tid}: guarda en el historial el cambio «{titulo}» y lo deja en la rama {RAMA_BASE} local, sin publicarlo.\n\n"
                 f"Qué hace: commitea en la rama tarea/{tid} los cambios del worktree (mensaje en español) y los fusiona en {RAMA_BASE} con --no-ff. No hace push.\n\n"
                 f"Aprobar esta tarea equivale a pedir el commit; revisa antes el resultado de {tid}."},
        {"title": titulo_push, "group": grupo, "deps": [titulo_commit],
         "desc": f"Cierre de {tid}: publica en GitHub la rama {RAMA_BASE} con el commit anterior; GitHub Pages actualiza la web en un par de minutos.\n\n"
                 f"Qué hace: git push origin {RAMA_BASE} (solo {RAMA_BASE}, sin forzar). Si el remoto tuviera commits que no tenemos, no hace nada y pregunta.\n\n"
                 f"Aprobar esta tarea equivale a pedir el push. Después, comprueba la web pasados unos minutos."},
    ]}


def cli(board, agente, *args, check=False, entrada=None):
    env = dict(os.environ, KANVAS_AGENT=agente)
    r = subprocess.run(["python3", CLI, "--board", board, *args], capture_output=True, text=True, env=env, input=entrada)
    if check and r.returncode != 0:
        raise RuntimeError((r.stdout + r.stderr).strip())
    return (r.stdout + r.stderr).strip()


def git(*args, cwd=REPO, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {(r.stdout + r.stderr).strip()}")
    return r.stdout.strip()


def tarea_origen(t):
    """ID de la tarea de trabajo que cierra una tarea de commit (aparece como «Cierre de XXX-NN:»)."""
    m = re.match(r"\s*Cierre de ([A-Z]+-\d+)", t.get("desc") or "")
    return m.group(1) if m else None


def preparar_worktree(tid):
    """Crea (o reutiliza) el worktree `tarea/<ID>` desde la rama base."""
    os.makedirs(WORKTREES, exist_ok=True)
    ruta = os.path.join(WORKTREES, tid)
    rama = f"tarea/{tid}"
    if not os.path.isdir(ruta):
        existe = subprocess.run(["git", "rev-parse", "--verify", "-q", rama], cwd=REPO, capture_output=True).returncode == 0
        if existe:
            git("worktree", "add", ruta, rama)
        else:
            git("worktree", "add", "-b", rama, ruta, RAMA_BASE)
    return ruta


def prompt_para(t, kind, board, cwd, origen=None, ruta_origen=None):
    tid = t["id"]
    cabecera = (
        f"Eres un agente autónomo de este repositorio. Tu tarea en el tablero Kanvas es {tid}: «{t['title']}».\n"
        f"Herramienta del tablero (usa siempre exactamente esta forma, con rutas absolutas y `--as` para firmar):\n"
        f"  python3 {CLI} --board {board} --as claude-code-{tid} <comando>\n"
        f"IMPORTANTE: NO antepongas variables de entorno a los comandos (`KANVAS_AGENT=… python3 …`) ni encadenes varios comandos con `&&`: "
        f"los permisos de este agente solo admiten cada orden por separado.\n"
        f"Lee primero las reglas del flujo en {SKILL} (skill de Kanvas) y sigue la guía del proyecto en {CLAUDE_MD}.\n\n"
        f"Pasos obligatorios: 1) `show {tid}` y lee la descripción y TODAS las notas; 2) `start {tid} -m \"Plan: …\"`; "
        f"3) haz el trabajo; 4) `finish {tid} -m \"…\"` con un resumen para una persona (qué cambia, cómo se verificó, qué debe comprobar). "
        f"No cojas otra tarea. Si necesitas una respuesta humana usa `ask {tid} \"…\"`, deja de trabajar y termina.\n\n"
    )
    if kind == "push":
        return cabecera + (
            f"Directorio de trabajo: {cwd} (repositorio principal). Esta tarea publica la rama `{RAMA_BASE}` en el remoto con `git push origin {RAMA_BASE}`; "
            f"aprobarla en el tablero equivale a aprobar ese push. Ejecuta los comandos de git SIN `-C` (ya estás en el repositorio) y uno por uno.\n"
            f"1) Comprueba con `git branch --show-current` que estás en `{RAMA_BASE}` y con `git status --short` que no hay cambios sin guardar en ficheros versionados. "
            f"Si algo no cuadra, no sigas: explícalo con `ask`.\n"
            f"2) `git fetch origin` y revisa con `git log --oneline origin/{RAMA_BASE}..{RAMA_BASE}` los commits que se van a subir: deben corresponder a las tareas anteriores. "
            f"Si `origin/{RAMA_BASE}` tiene commits que tú no tienes, NO hagas pull, merge, rebase ni push forzado: explícalo con `ask` y termina.\n"
            f"3) `git push origin {RAMA_BASE}`. Después comprueba con `git status -sb` que `{RAMA_BASE}` quedó al día con `origin/{RAMA_BASE}`.\n"
            f"4) En el resumen indica qué commits se subieron y que GitHub Pages tarda un par de minutos en publicar `docs/` (no lo vigiles). "
            f"No subas otras ramas ni etiquetas."
        )
    cabecera += "No hagas push.\n\n"
    if kind == "trabajo" and not es_manual(t) and t.get("group") in GRUPOS_MANUALES:
        return cabecera + (
            f"Directorio de trabajo: {cwd} (worktree en la rama `tarea/{tid}`, creada desde `{RAMA_BASE}`). "
            f"Esta tarea actualiza los datos de la liga: sigue la skill {REPO}/.claude/skills/actualizar-datos-liga/SKILL.md, "
            f"pero ejecutando los scripts DESDE ESTE WORKTREE (sus rutas son relativas a él): `python3 -I scripts/descargar_csv.py` y después "
            f"`python3 scripts/generar_datos.py`, cada uno por separado. En el worktree no hay `source/`: lo crea la descarga; no uses el del repositorio principal. "
            f"Si la descarga dice que no hay datos nuevos, no cambies nada y dilo en el resumen. Si algo falla, no inventes datos: usa `ask`. "
            f"NO edites `docs/datos-liga.js` a mano ni toques Firestore. NO hagas commit: lo hará la tarea de cierre. "
            f"En el `finish`, resume la sección «Cambios respecto a la versión anterior» destacando cambios de fecha, hora o instalación, "
            f"resultados nuevos, movimientos en la tabla y si la clasificación es «calculada» o viene del CSV."
        )
    if kind == "trabajo":
        return cabecera + (
            f"Directorio de trabajo: {cwd} (worktree en la rama `tarea/{tid}`, creada desde `{RAMA_BASE}`). "
            f"Implementa lo que pide la tarea y verifica el resultado como indique el CLAUDE.md. "
            f"NO hagas commit: lo hará la tarea de cierre que sigue. Deja los cambios sin commitear en este worktree y menciona en el resumen "
            f"qué ficheros tocaste."
        )
    extra = (
        f"Esta tarea cierra {origen}. Los cambios de {origen} están SIN commitear en el worktree {ruta_origen} (rama `tarea/{origen}`).\n"
        f"1) Revisa el diff (`git -C {ruta_origen} diff` y `git -C {ruta_origen} status`) y comprueba que coincide con lo que describe {origen}.\n"
        f"2) Verifica los cambios dentro de {ruta_origen} como indique el CLAUDE.md.\n"
        f"3) Commit en la rama `tarea/{origen}` (`git -C {ruta_origen} add` de los ficheros relevantes y `git -C {ruta_origen} commit`; mensaje en español, "
        f"con la línea final `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`). Después, en el repositorio principal ({REPO}, rama `{RAMA_BASE}`), "
        f"fusiona con `git -C {REPO} merge --no-ff tarea/{origen}`. NO hagas push. Aprobar esta tarea en el tablero equivale a aprobar este commit. "
        f"Si la fusión da conflictos, no los resuelvas a ciegas: aborta (`git merge --abort`), explícalo con `ask`."
    )
    return cabecera + f"Directorio de trabajo: {cwd}.\n" + extra


class Ejecucion:
    def __init__(self, tarea, kind, proc, logpath, fh, cwd=None):
        self.tarea, self.kind, self.proc, self.logpath, self.fh, self.cwd = tarea, kind, proc, logpath, fh, cwd
        self.inicio = time.time()


def nota_cierre(ej, dur):
    """Nota objetiva del lanzador al terminar un agente: código de salida, duración y, en tareas de trabajo,
    los ficheros que tocó de verdad (para contrastar con el resumen del propio agente)."""
    lineas = [f"Lanzador: el agente terminó con código {ej.proc.returncode} en {dur}s."]
    if ej.kind == "trabajo" and ej.cwd and os.path.isdir(ej.cwd):
        try:
            stat = git("diff", "--stat", "HEAD", cwd=ej.cwd, check=False)
            nuevos = [l[3:] for l in git("status", "--short", cwd=ej.cwd, check=False).splitlines() if l.startswith("??")]
            if stat or nuevos:
                lineas.append("Cambios en el worktree (sin commit):")
                lineas.append(stat or "(solo ficheros nuevos)")
                if nuevos:
                    lineas.append("Nuevos: " + ", ".join(nuevos[:10]))
            else:
                lineas.append("Sin cambios en el código del worktree.")
        except Exception as e:  # noqa: BLE001
            lineas.append(f"No se pudo leer el worktree: {e}")
    lineas.append(f"Log completo: {ej.logpath}")
    return "\n".join(lineas)


def lanzar(t, kind, args, claude, board):
    tid = t["id"]
    if not os.path.exists(claude):  # la extensión de VS Code se actualizó y borró la carpeta de la versión anterior
        try:
            nuevo = localizar_claude()
        except SystemExit as e:
            raise RuntimeError(str(e))
        log(f"el binario de claude ya no existe ({claude}); uso {nuevo}")
        claude = nuevo
    os.makedirs(LOGS, exist_ok=True)
    origen = ruta_origen = None
    if kind == "trabajo":
        cwd = os.path.join(WORKTREES, tid) if args.dry_run else preparar_worktree(tid)
    else:
        cwd = REPO
        if kind == "commit":
            origen = tarea_origen(t)
            if not origen:
                raise RuntimeError(f"{tid}: no encuentro «Cierre de XXX-NN» en la descripción")
            ruta_origen = os.path.join(WORKTREES, origen)
            if not os.path.isdir(ruta_origen):
                raise RuntimeError(f"{tid}: no existe el worktree de {origen} ({ruta_origen})")
    prompt = prompt_para(t, kind, board, cwd, origen, ruta_origen)
    cmd = [claude, "-p", prompt, "--permission-mode", "acceptEdits", "--settings", SETTINGS_PUSH if kind == "push" else SETTINGS,
           "--add-dir", WORKTREES, "--add-dir", ESTADO, "--max-budget-usd", str(args.presupuesto),
           "--no-session-persistence", "--output-format", "text"]
    if args.modelo:
        cmd += ["--model", args.modelo]
    logpath = os.path.join(LOGS, f"{tid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    if args.dry_run:
        log(f"[dry-run] lanzaría {tid} ({kind}) en {cwd}\n    log: {logpath}")
        return None
    fh = open(logpath, "w", encoding="utf-8")
    env = dict(os.environ, KANVAS_AGENT=f"claude-code-{tid}", KANVAS_BOARD=board)
    proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT, env=env, start_new_session=True)
    log(f"lanzado {tid} ({kind}) pid {proc.pid} · log {logpath}")
    return Ejecucion(t, kind, proc, logpath, fh, cwd)


def notificar(titulo, texto):
    subprocess.run(["osascript", "-e", f'display notification "{texto}" with title "{titulo}"'], capture_output=True)


ARCHIVOS_VIGILADOS = (
    os.path.abspath(__file__),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "agente.settings.json"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "agente_push.settings.json"),
)


def huella_codigo():
    """(ruta, mtime) del script y de los permisos: si cambia, el servicio corre con código o permisos antiguos."""
    res = []
    for ruta in ARCHIVOS_VIGILADOS:
        try:
            res.append((ruta, os.stat(ruta).st_mtime_ns))
        except OSError:
            res.append((ruta, None))
    return tuple(res)


def codigo_valido():
    """El script actual compila (evita reiniciar en bucle si se guardó a medias)."""
    try:
        with open(ARCHIVOS_VIGILADOS[0], "rb") as f:
            compile(f.read(), ARCHIVOS_VIGILADOS[0], "exec")
        return True
    except (OSError, SyntaxError, ValueError):
        return False


def main():
    ap = argparse.ArgumentParser(description="Lanza agentes de Claude Code para las tareas listas del tablero Kanvas")
    ap.add_argument("--board", default=BOARD_DEFECTO)
    ap.add_argument("--max-paralelo", type=int, default=2, help="agentes simultáneos (por defecto 2)")
    ap.add_argument("--intervalo", type=int, default=60, help="segundos entre consultas al tablero")
    ap.add_argument("--presupuesto", type=float, default=5.0, help="USD máximos por tarea (por defecto 5)")
    ap.add_argument("--modelo", default=None, help="modelo de Claude (por defecto, el configurado)")
    ap.add_argument("--solo", nargs="*", default=None, help="limitar a estos IDs de tarea")
    ap.add_argument("--una-vez", action="store_true", help="una sola pasada; no queda en bucle")
    ap.add_argument("--dry-run", action="store_true", help="solo muestra qué lanzaría")
    args = ap.parse_args()

    board = os.path.abspath(args.board)
    if not os.path.isfile(board):
        sys.exit(f"No existe el tablero {board}")
    claude = localizar_claude()
    log(f"tablero {board} · claude {claude}")
    log(f"máx. {args.max_paralelo} en paralelo · presupuesto {args.presupuesto} USD/tarea" + (" · DRY-RUN" if args.dry_run else ""))

    activos, fallos, avisadas = {}, {}, set()
    parar = {"v": False}
    huella_inicial = huella_codigo()
    reinicio = False  # código o permisos cambiados: no se lanza nada nuevo y se sale al quedar sin agentes
    signal.signal(signal.SIGINT, lambda *_: parar.__setitem__("v", True))
    signal.signal(signal.SIGTERM, lambda *_: parar.__setitem__("v", True))

    while not parar["v"]:
        # 1) recoger los que terminaron
        for tid, ej in list(activos.items()):
            if ej.proc.poll() is None:
                continue
            ej.fh.close()
            del activos[tid]
            t_now = next((x for x in leer_tablero(board) if x["id"] == tid), None)
            est = t_now["state"] if t_now else "?"
            dur = int(time.time() - ej.inicio)
            log(f"terminó {tid} (código {ej.proc.returncode}, {dur}s) · estado en el tablero: {est}")
            if est in ("doing", "review"):  # una tarea ya hecha no admite notas
                cli(board, "lanzador", "note", tid, nota_cierre(ej, dur))
            if est == "doing":
                cli(board, f"claude-code-{tid}", "pause", tid, "-m",
                    f"El agente terminó (código {ej.proc.returncode}) sin cerrar la tarea. Ver {ej.logpath}")
                fallos[tid] = fallos.get(tid, 0) + 1
                notificar("Kanvas: tarea pausada", f"{tid} terminó sin cerrarse")
            elif est == "todo":
                fallos[tid] = fallos.get(tid, 0) + 1
                log(f"  {tid} no llegó a empezar; fallos acumulados: {fallos[tid]} (log {ej.logpath})")
            elif est == "review":
                notificar("Kanvas: tarea en revisión", f"{tid}: {t_now['title'][:60]}")

        # 2) proponer «Commit» y «Push» para las tareas de trabajo que ya esperan revisión
        for t in cierres_pendientes(leer_tablero(board)):
            if args.dry_run:
                if t["id"] not in avisadas:
                    avisadas.add(t["id"])
                    log(f"[dry-run] proponería «Commit» y «Push» para {t['id']}")
                continue
            try:
                log(f"{t['id']} espera revisión: " + cli(board, "lanzador", "batch", check=True,
                                                          entrada=json.dumps(propuesta_de_cierre(t))).replace("\n", " · "))
            except Exception as e:  # noqa: BLE001
                if t["id"] not in avisadas:
                    avisadas.add(t["id"])
                    log(f"no se pudieron proponer las tareas de cierre de {t['id']}: {e}")

        # 2b) ¿cambió el código o los permisos? Reinicio limpio: sin tocar los agentes en vuelo
        if not reinicio and not args.una_vez and huella_codigo() != huella_inicial:
            if codigo_valido():
                reinicio = True
                log("código o permisos cambiados: no se lanzan tareas nuevas y se reinicia al terminar los agentes en curso")
            else:
                huella_inicial = huella_codigo()  # no reintentar hasta el siguiente cambio
                log("código o permisos cambiados, pero el script no compila: no se reinicia")
        if reinicio:
            if not activos:
                log("sin agentes en curso: saliendo para que launchd me relance con el código nuevo")
                return
            time.sleep(args.intervalo)
            continue

        # 3) lanzar nuevas
        seriales_activos = any(e.kind in SERIALES for e in activos.values())
        for t in listas(leer_tablero(board)):
            tid, kind = t["id"], tipo_tarea(t)
            if len(activos) >= args.max_paralelo:
                break
            if args.solo is not None and tid not in args.solo:
                continue
            if es_manual(t):
                if tid not in avisadas:
                    avisadas.add(tid)
                    log(f"{tid}: es del grupo {t['group']}, que se hace en una sesión de Claude Code; no se lanza solo")
                continue
            if tid in activos or fallos.get(tid, 0) >= 2:
                if fallos.get(tid, 0) >= 2 and tid not in avisadas:
                    avisadas.add(tid)
                    log(f"{tid}: demasiados fallos, no se relanza (revisa el log y reinicia el lanzador)")
                continue
            if kind in SERIALES and seriales_activos:
                continue
            try:
                ej = lanzar(t, kind, args, claude, board)
            except Exception as e:  # noqa: BLE001
                fallos[tid] = fallos.get(tid, 0) + 1
                log(f"no se pudo lanzar {tid}: {e}")
                continue
            if ej:
                activos[tid] = ej
                seriales_activos = seriales_activos or kind in SERIALES

        if args.una_vez and not activos:
            break
        if args.dry_run and args.una_vez:
            break
        time.sleep(args.intervalo if activos or not args.una_vez else 1)

    if activos:
        log("deteniendo agentes en curso…")
        for ej in activos.values():
            if ej.proc.poll() is not None:  # ya terminó (si no, macOS da PermissionError al señalar su grupo)
                continue
            try:
                os.killpg(ej.proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        time.sleep(5)
        for tid, ej in activos.items():
            t_now = next((x for x in leer_tablero(board) if x["id"] == tid), None)
            if t_now and t_now["state"] == "doing":
                cli(board, f"claude-code-{tid}", "pause", tid, "-m", "Interrumpido al detener el lanzador.")
    log("fin")


if __name__ == "__main__":
    main()
