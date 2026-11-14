#!/usr/bin/env python3
"""Descarga a source/ los CSV más recientes de partidos y clasificaciones de Datos Madrid.

Conjunto: «Competiciones deportivas municipales de deportes colectivos. Temporada en curso»
(https://datos.madrid.es/dataset/211549-0-juegos-deportivos-actual). Se actualiza cada miércoles.

    python3 -I scripts/descargar_csv.py --comprobar   # solo muestra qué hay publicado y qué bajaría
    python3 -I scripts/descargar_csv.py               # descarga a source/

- Pregunta a la API (package_show) las URLs vigentes: llevan la fecha en el nombre y cambian cada semana.
- Descarga a una carpeta temporal, valida la cabecera y solo entonces guarda en source/ como
  partidos_AAAAMMDD.csv / clasificaciones_AAAAMMDD.csv.
- Si el contenido es idéntico al CSV que ya tienes de ese tipo, no guarda nada.
- No regenera docs/datos-liga.js: después hay que ejecutar scripts/generar_datos.py (o /actualizar-datos-liga).
"""
import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SOURCE = RAIZ / "source"
API = "https://datos.madrid.es/api/3/action/package_show?id=211549-0-juegos-deportivos-actual"
USER_AGENT = "descargar-csv-liga/1.0"
TIMEOUT = 120

# tipo -> (descripción del recurso en la API, columna que debe tener la cabecera, prefijo del fichero, tamaño mínimo en bytes)
TIPOS = {
    "partidos": ("Partidos", "Codigo_equipo1", "partidos", 1_000_000),
    "clasificaciones": ("Clasificaciones", "Puntos", "clasificaciones", 10_000),
}


def abrir(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=TIMEOUT)


def recursos_vigentes():
    """Devuelve {tipo: recurso} con el CSV publicado más reciente de cada tipo."""
    try:
        with abrir(API) as r:
            datos = json.load(r)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        sys.exit(f"No se pudo consultar la API de Datos Madrid: {e}")
    if not datos.get("success"):
        sys.exit(f"La API respondió con error: {datos.get('error')}")
    salida = {}
    for tipo, (descripcion, _, _, _) in TIPOS.items():
        cands = [
            x for x in datos["result"]["resources"]
            if (x.get("format") or "").upper() == "CSV" and (x.get("description") or "").strip() == descripcion
        ]
        if not cands:
            sys.exit(f"La API no publica ningún CSV de «{descripcion}»: ¿ha cambiado el conjunto de datos?")
        salida[tipo] = max(cands, key=lambda x: x.get("last_modified") or "")
    return salida


def sha(ruta):
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def cabecera(ruta):
    with ruta.open("r", encoding="latin1") as f:
        return f.readline().strip().split(";")


def existentes(columna, destino):
    """CSV de source/ cuya cabecera contiene `columna`, del más reciente al más antiguo."""
    if not destino.is_dir():
        return []
    return sorted((p for p in destino.glob("*.csv") if columna in cabecera(p)), key=lambda p: p.stat().st_mtime, reverse=True)


def nombre_fichero(prefijo, url):
    """partidos_20261112.csv a partir de la URL (…/partidos_20261112.csv); si no lleva fecha, se usa el nombre tal cual."""
    return Path(url.split("?")[0]).name if Path(url).stem.startswith(prefijo) else f"{prefijo}.csv"


def main():
    ap = argparse.ArgumentParser(description="Descarga a source/ los CSV de partidos y clasificaciones de Datos Madrid")
    ap.add_argument("--comprobar", action="store_true", help="solo muestra qué hay publicado; no descarga nada")
    ap.add_argument("--destino", default=str(SOURCE), help="carpeta de destino (por defecto source/)")
    args = ap.parse_args()
    destino = Path(args.destino)

    vigentes = recursos_vigentes()
    for tipo, r in vigentes.items():
        print(f"{tipo:16} publicado {r.get('last_modified', '?')[:16]} · {Path(r['url']).name}")
    if args.comprobar:
        return

    destino.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="liga_csv_"))
    try:
        for tipo, r in vigentes.items():
            _, columna, prefijo, minimo = TIPOS[tipo]
            nombre = nombre_fichero(prefijo, r["url"])
            bajado = tmp / nombre
            try:
                with abrir(r["url"]) as resp, bajado.open("wb") as f:
                    shutil.copyfileobj(resp, f)
            except (urllib.error.URLError, TimeoutError) as e:
                sys.exit(f"No se pudo descargar {tipo} ({r['url']}): {e}")
            if bajado.stat().st_size < minimo or columna not in cabecera(bajado):
                sys.exit(f"{nombre} no parece un CSV de {tipo} (tamaño {bajado.stat().st_size} B, cabecera sin «{columna}»). No se guarda nada más.")
            previos = existentes(columna, destino)
            if previos and sha(previos[0]) == sha(bajado):
                print(f"= {tipo}: idéntico a {previos[0].name}; ya tienes la última versión")
                continue
            shutil.move(str(bajado), str(destino / nombre))
            print(f"+ {tipo}: guardado {destino / nombre} ({(destino / nombre).stat().st_size:,} B)".replace(",", "."))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
