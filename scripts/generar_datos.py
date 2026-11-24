#!/usr/bin/env python3
"""Genera docs/datos-liga.js a partir de los CSV más recientes de source/.

- Detecta el CSV de partidos y el de clasificación por su cabecera (no por el nombre).
- Si hay varios de cada tipo, usa el más reciente (fecha de modificación).
- Se queda con el grupo donde juega CLUB en la categoría/deporte configurados.
- Conserva solo los partidos del Club Aguirre, pero la clasificación es la del grupo entero.
"""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SOURCE = RAIZ / "source"
SALIDA = RAIZ / "docs" / "datos-liga.js"

CLUB = "Club Aguirre"
DEPORTE = "FUTBOL SALA"
CATEGORIA = "INFANTIL FEMENINO"

# Correcciones manuales sobre lo que dice el CSV, por número de jornada. Solo se aplican mientras el CSV siga
# diciendo lo de «csv» (fecha y suspendido); en cuanto la federación lo actualice, se avisa y hay que borrar la entrada.
AJUSTES = {
    1: {  # Dragones de Lavapiés A - Aguirre: suspendido el 14-11; se jugará el 29-11 a las 9:00 en Torrespaña
        "csv": {"fecha": "2026-11-14", "suspendido": True},
        "poner": {"fecha": "2026-11-29", "hora": "09:00", "instalacion": "Fútbol sala Torrespaña", "suspendido": False},
    },
}


def leer_csv(ruta):
    raw = ruta.read_bytes()
    try:
        texto = raw.decode("utf-8")
    except UnicodeDecodeError:
        texto = raw.decode("cp1252", errors="replace")
    return list(csv.DictReader(texto.splitlines(), delimiter=";"))


def cabecera(ruta):
    with ruta.open("r", encoding="latin1") as f:
        return f.readline().strip().split(";")


def mas_reciente(tipo, marca):
    candidatos = [p for p in SOURCE.glob("*.csv") if marca in cabecera(p)]
    if not candidatos:
        sys.exit(f"No hay ningún CSV de {tipo} en {SOURCE}")
    return max(candidatos, key=lambda p: p.stat().st_mtime)


def es_club(nombre):
    return nombre.strip().lower().startswith(CLUB.lower())


def num(v, tipo=int):
    try:
        return tipo(float(v))
    except (TypeError, ValueError):
        return 0


def cargar_anterior():
    """Lee partidos y clasificación del datos-liga.js previo (si existe) para poder comparar."""
    if not SALIDA.exists():
        return None, None
    txt = SALIDA.read_text(encoding="utf-8")
    try:
        def bloque(nombre):
            ini = txt.index(f"window.{nombre} = ") + len(f"window.{nombre} = ")
            return json.JSONDecoder().raw_decode(txt[ini:])[0]
        return bloque("PARTIDOS"), bloque("CLASIFICACION")
    except (ValueError, json.JSONDecodeError):
        return None, None


def mostrar_cambios(ant_p, ant_c, partidos, clasif):
    print("\n== Cambios respecto a la versión anterior ==")
    if ant_p is None:
        print("(primera generación, no hay versión anterior)")
        return
    hay = False
    antes = {p["jornada"]: p for p in ant_p}
    for p in partidos:
        a = antes.get(p["jornada"])
        rival = p["visitante"] if p["local"] == CLUB else p["local"]
        et = f"J{p['jornada']} vs {rival}"
        if a is None:
            print(f"+ {et}: partido nuevo"); hay = True; continue
        if p["finalizado"] and not a.get("finalizado"):
            print(f"* {et}: RESULTADO {p['local']} {p['golesLocal']}-{p['golesVisitante']} {p['visitante']}"); hay = True
        if p["suspendido"] != bool(a.get("suspendido")):
            print(f"! {et}: " + ("SUSPENDIDO" if p["suspendido"] else "ya no figura como suspendido (reprogramado)")); hay = True
        for campo, nom in (("fecha", "fecha"), ("hora", "hora"), ("instalacion", "instalación"),
                           ("camisetaLocal", "camiseta local"), ("camisetaVisitante", "camiseta visitante"),
                           ("local", "local"), ("visitante", "visitante")):
            if a.get(campo) != p[campo]:
                print(f"~ {et}: {nom}: {a.get(campo) or '—'} -> {p[campo] or '—'}"); hay = True
    for j in antes.keys() - {p["jornada"] for p in partidos}:
        print(f"- J{j}: partido eliminado"); hay = True
    pos_ant = {e["equipo"]: e["pos"] for e in (ant_c or [])}
    for e in clasif:
        if e["equipo"] in pos_ant and pos_ant[e["equipo"]] != e["pos"]:
            print(f"# Clasificación: {e['equipo']} {pos_ant[e['equipo']]}º -> {e['pos']}º"); hay = True
    if not hay:
        print("Sin cambios.")


def main():
    f_partidos = mas_reciente("partidos", "Codigo_equipo1")
    f_clasif = mas_reciente("clasificación", "Puntos")
    print(f"Partidos:      {f_partidos.name}")
    print(f"Clasificación: {f_clasif.name}")

    filas = [
        r for r in leer_csv(f_partidos)
        if r["Nombre_deporte"].strip() == DEPORTE and r["Nombre_categoria"].strip() == CATEGORIA
    ]
    grupos = {r["Codigo_grupo"] for r in filas if es_club(r["Equipo_local"]) or es_club(r["Equipo_visitante"])}
    if len(grupos) != 1:
        sys.exit(f"Se esperaba 1 grupo de {CLUB} en {DEPORTE} {CATEGORIA}, encontrados: {grupos or 'ninguno'}")
    grupo = grupos.pop()
    del_grupo = [r for r in filas if r["Codigo_grupo"] == grupo]
    nombre_grupo = del_grupo[0]["Nombre_grupo"]

    # --- Partidos del club ---
    partidos = []
    for r in del_grupo:
        if not (es_club(r["Equipo_local"]) or es_club(r["Equipo_visitante"])):
            continue
        fin = r["Estado"].strip() == "F"
        partidos.append({
            "jornada": int(r["Jornada"]),
            "fecha": r["Fecha"].strip(),
            "hora": r["Hora"].strip() or None,
            "local": CLUB if es_club(r["Equipo_local"]) else r["Equipo_local"].strip(),
            "visitante": CLUB if es_club(r["Equipo_visitante"]) else r["Equipo_visitante"].strip(),
            "instalacion": r["Campo"].strip() or None,
            "camisetaLocal": r["Color_Camiseta_1"].strip() or None,
            "camisetaVisitante": r["Color_Camiseta_2"].strip() or None,
            "finalizado": fin,
            "suspendido": r["Estado"].strip() == "S",
            "golesLocal": num(r["Resultado1"]) if fin else None,
            "golesVisitante": num(r["Resultado2"]) if fin else None,
        })
    partidos.sort(key=lambda p: p["jornada"])
    for p in partidos:
        aj = AJUSTES.get(p["jornada"])
        if not aj:
            continue
        if all(p[k] == v for k, v in aj["csv"].items()):
            p.update(aj["poner"])
            print(f"Ajuste manual aplicado a la jornada {p['jornada']}: " + ", ".join(f"{k}={v}" for k, v in aj["poner"].items()))
        else:
            print(f"! AJUSTES[{p['jornada']}] obsoleto: el CSV ya no dice {aj['csv']}. Bórralo de scripts/generar_datos.py.")

    # --- Clasificación ---
    codigo_nombre = {}
    for r in del_grupo:
        codigo_nombre[r["Codigo_equipo1"]] = r["Equipo_local"].strip()
        codigo_nombre[r["Codigo_equipo2"]] = r["Equipo_visitante"].strip()

    clasif = []
    origen = "csv"
    for r in leer_csv(f_clasif):
        if r["Codigo_grupo"] == grupo:
            clasif.append({
                "equipo": r["Nombre_equipo"].strip(),
                "pos": num(r["Posicion"]), "pts": num(r["Puntos"]),
                "pj": num(r["Partidos_jugados"]), "g": num(r["Partidos_ganados"]),
                "e": num(r["Partidos_empatados"]), "p": num(r["Partidos_perdidos"]),
                "gf": num(r["Goles_favor"]), "gc": num(r["Goles_contra"]),
            })
    if not clasif:
        # El fichero de clasificación aún no incluye el grupo: se calcula con los partidos finalizados.
        origen = "calculada"
        t = {n: dict(equipo=n, pts=0, pj=0, g=0, e=0, p=0, gf=0, gc=0) for n in codigo_nombre.values()}
        for r in del_grupo:
            if r["Estado"].strip() != "F":
                continue
            a, b = t[r["Equipo_local"].strip()], t[r["Equipo_visitante"].strip()]
            ga, gb = num(r["Resultado1"]), num(r["Resultado2"])
            for x, gf, gc in ((a, ga, gb), (b, gb, ga)):
                x["pj"] += 1; x["gf"] += gf; x["gc"] += gc
            if ga > gb: a["g"] += 1; b["p"] += 1; a["pts"] += 3
            elif ga < gb: b["g"] += 1; a["p"] += 1; b["pts"] += 3
            else: a["e"] += 1; b["e"] += 1; a["pts"] += 1; b["pts"] += 1
        clasif = list(t.values())
        clasif.sort(key=lambda x: (-x["pts"], -(x["gf"] - x["gc"]), -x["gf"], x["equipo"].lower()))
        for i, x in enumerate(clasif, 1):
            x["pos"] = i
    clasif.sort(key=lambda x: x["pos"])

    datos = {
        "grupo": nombre_grupo,
        "actualizado": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ficheroPartidos": f_partidos.name,
        "ficheroClasificacion": f_clasif.name,
        "origenClasificacion": origen,
    }
    ant_p, ant_c = cargar_anterior()
    SALIDA.write_text(
        "// GENERADO por scripts/generar_datos.py a partir de source/*.csv. No editar a mano.\n"
        f"window.LIGA = {json.dumps(datos, ensure_ascii=False, indent=2)};\n"
        f"window.PARTIDOS = {json.dumps(partidos, ensure_ascii=False, indent=2)};\n"
        f"window.CLASIFICACION = {json.dumps(clasif, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    jugados = sum(p["finalizado"] for p in partidos)
    print(f"Grupo: {nombre_grupo}")
    print(f"{len(partidos)} partidos del club ({jugados} finalizados); clasificación {origen} ({len(clasif)} equipos)")
    print(f"Escrito {SALIDA.relative_to(RAIZ)}")
    mostrar_cambios(ant_p, ant_c, partidos, clasif)


if __name__ == "__main__":
    main()
