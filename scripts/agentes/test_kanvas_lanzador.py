import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from kanvas_lanzador import (  # noqa: E402
    GRUPOS_MANUALES, RAMA_BASE, SERIALES, cierres_pendientes, listas, prompt_para, propuesta_de_cierre, tarea_origen, tipo_tarea,
)


def t(id_, title, state="todo", group="X", deps=None):
    return {"id": id_, "title": title, "state": state, "group": group, "deps": deps or []}


def se_lanzan(tareas):
    """IDs que el lanzador arrancaría, aplicando listas() como main()."""
    return [x["id"] for x in listas(tareas)]


def test_tarea_con_dependencias_hechas_se_lanza():
    tareas = [t("A-01", "Algo", "done"), t("A-02", "Otra", deps=["A-01"])]
    assert se_lanzan(tareas) == ["A-02"]


def test_tarea_con_dependencias_sin_terminar_no_se_lanza():
    tareas = [t("A-01", "Algo", "doing"), t("A-02", "Otra", deps=["A-01"])]
    assert se_lanzan(tareas) == []


def test_tarea_en_doing_sin_agente_se_ignora():
    assert se_lanzan([t("X-01", "Trabajo", "doing")]) == []


def test_tipos_de_tarea():
    assert tipo_tarea(t("X-01", "Arreglar el calendario")) == "trabajo"
    assert tipo_tarea(t("X-02", "Commit: calendario")) == "commit"
    assert tipo_tarea(t("X-03", "  commit: en minúsculas")) == "commit"
    assert tipo_tarea(t("X-04", "Confirmar y commit: datos")) == "trabajo"  # solo «Commit:» es un tipo especial


def test_push_es_un_tipo_y_es_serial():
    assert tipo_tarea(t("X-06", "Push: subir a GitHub")) == "push"
    assert tipo_tarea(t("X-07", "  push: en minúsculas")) == "push"
    assert tipo_tarea(t("X-08", "Hacer push del cambio")) == "trabajo"  # solo el prefijo «Push:» es especial


def test_commit_y_push_son_seriales_y_trabajo_no():
    assert "commit" in SERIALES and "push" in SERIALES
    assert "trabajo" not in SERIALES


def test_prompt_de_push_sube_main_y_los_demas_no_hacen_push():
    push = prompt_para(t("AW-03", "Push: subir"), "push", "/b.json", "/repo")
    assert "git push origin main" in push
    assert "No hagas push." not in push
    trabajo = prompt_para(t("AW-01", "Cambiar texto"), "trabajo", "/b.json", "/wt")
    assert "No hagas push." in trabajo
    assert "git push origin" not in trabajo


def permisos(nombre):
    ruta = os.path.join(os.path.dirname(__file__), nombre)
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)["permissions"]


def test_agentes_de_trabajo_y_commit_no_pueden_hacer_push():
    p = permisos("agente.settings.json")
    assert "Bash(git push:*)" in p["deny"]
    assert "Bash(git -C * push*)" in p["deny"]  # git -C <ruta> push no debe colarse
    assert not any("push" in a for a in p["allow"])


def test_agente_push_solo_puede_subir_main_sin_forzar():
    p = permisos("agente_push.settings.json")
    pushes = [a for a in p["allow"] if "push" in a]
    assert pushes == ["Bash(git push origin main)"]
    for prohibido in ("Bash(git push --force:*)", "Bash(git push -f:*)", "Bash(git push * --force*)", "Bash(git -C:*)", "Edit", "Write"):
        assert prohibido in p["deny"]


def test_orden_numerico_de_ids():
    tareas = [t("X-10", "Trabajo"), t("X-02", "Commit: algo"), t("X-03", "Otro")]
    assert se_lanzan(tareas) == ["X-02", "X-03", "X-10"]


def test_tarea_origen_se_lee_de_la_descripcion():
    assert tarea_origen({"desc": "Cierre de AG-07: fusionar"}) == "AG-07"
    assert tarea_origen({"desc": "sin referencia"}) is None
    assert tarea_origen({}) is None


def test_datos_de_la_liga_es_grupo_manual():
    assert "DL" in GRUPOS_MANUALES
    assert "AW" not in GRUPOS_MANUALES


def test_cierres_pendientes_solo_trabajo_en_revision_sin_commit():
    tareas = [
        t("AW-01", "Ya tiene commit", "review", group="AW"),
        t("AW-02", "Commit: Ya tiene commit", group="AW", deps=["AW-01"]),
        t("AW-03", "Push: Ya tiene commit", group="AW", deps=["AW-02"]),
        t("AW-04", "Sin commit todavía", "review", group="AW"),
        t("AW-05", "Aún en curso", "doing", group="AW"),
        t("DL-01", "Datos de la liga", "review", group="DL"),
        t("AW-06", "Commit: huérfano", "review", group="AW", deps=["AW-09"]),
        t("AW-07", "Push: huérfano", "review", group="AW"),
    ]
    assert [x["id"] for x in cierres_pendientes(tareas)] == ["AW-04"]


def test_propuesta_de_cierre_encadena_trabajo_commit_y_push():
    lote = propuesta_de_cierre(t("AW-04", "Destacar nombre", "review", group="AW"))
    commit, push = lote["tasks"]
    assert commit["title"] == "Commit: Destacar nombre" and commit["deps"] == ["AW-04"] and commit["group"] == "AW"
    assert commit["desc"].startswith("Cierre de AW-04:")
    assert push["title"] == "Push: Destacar nombre" and push["deps"] == [commit["title"]]
    assert tipo_tarea(commit) == "commit" and tipo_tarea(push) == "push"
    # tras proponerlas, la tarea ya no necesita cierre
    tras = [t("AW-04", "Destacar nombre", "review", group="AW"), {**commit, "id": "AW-05", "state": "proposed"}]
    assert cierres_pendientes(tras) == []


def test_rama_base_es_main():
    assert RAMA_BASE == "main"
