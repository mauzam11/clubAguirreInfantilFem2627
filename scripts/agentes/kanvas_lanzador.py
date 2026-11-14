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
Las tareas del grupo DL («Datos de la liga») no se lanzan nunca solas: se hacen en una sesión de Claude Code.

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


def listas(tareas):
    estado = {t["id"]: t["state"] for t in tareas}
    return sorted(
        [t for t in tareas if t["state"] == "todo" and all(estado.get(d) == "done" for d in (t.get("deps") or []))],
        key=lambda t: (t["id"].split("-")[0], int(t["id"].split("-")[1])),
    )


def cli(board, agente, *args, check=False):
    env = dict(os.environ, KANVAS_AGENT=agente)
    r = subprocess.run(["python3", CLI, "--board", board, *args], capture_output=True, text=True, env=env)
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

        # 2) lanzar nuevas
        seriales_activos = any(e.kind in SERIALES for e in activos.values())
        for t in listas(leer_tablero(board)):
            tid, kind = t["id"], tipo_tarea(t)
            if len(activos) >= args.max_paralelo:
                break
            if args.solo is not None and tid not in args.solo:
                continue
            if t.get("group") in GRUPOS_MANUALES:
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
