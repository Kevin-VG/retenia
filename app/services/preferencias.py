"""Preferencias del usuario (institución y responsable que aparecen en las fichas PDF)."""
import json
from pathlib import Path

from app import rutas

CLAVES = ("institucion", "area", "responsable")


def _ruta() -> Path:
    return rutas.carpeta_datos() / "preferencias.json"


def cargar() -> dict:
    try:
        datos = json.loads(_ruta().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        datos = {}
    return {c: str(datos.get(c, "")).strip() for c in CLAVES}


def guardar(preferencias: dict) -> None:
    datos = {c: str(preferencias.get(c, "")).strip() for c in CLAVES}
    _ruta().write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
