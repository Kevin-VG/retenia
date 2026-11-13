"""Historial local de evaluaciones (SQLite en la carpeta de datos del usuario)."""
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app import __version__, rutas

ESQUEMA = """
CREATE TABLE IF NOT EXISTS evaluaciones (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha         TEXT    NOT NULL,              -- ISO 8601, hora local
    estudiante_id TEXT    NOT NULL DEFAULT '',
    nombre        TEXT    NOT NULL DEFAULT '',
    origen        TEXT    NOT NULL CHECK (origen IN ('individual', 'lote')),
    probabilidad  REAL    NOT NULL,
    semaforo      TEXT    NOT NULL CHECK (semaforo IN ('Rojo', 'Amarillo', 'Verde')),
    umbral        REAL    NOT NULL,
    perfil_json   TEXT    NOT NULL,              -- 36 variables usadas por el modelo
    entradas_json TEXT    NOT NULL,              -- variables ingresadas por el usuario
    notas         TEXT    NOT NULL DEFAULT '',
    app_version   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eval_estudiante ON evaluaciones (estudiante_id);
CREATE INDEX IF NOT EXISTS idx_eval_fecha ON evaluaciones (fecha);
"""


@dataclass
class Registro:
    id: int
    fecha: str
    estudiante_id: str
    nombre: str
    origen: str
    probabilidad: float
    semaforo: str
    umbral: float
    perfil: dict
    entradas: dict
    notas: str
    app_version: str


class Historial:
    def __init__(self, ruta: Path | None = None):
        self.ruta = Path(ruta) if ruta else rutas.carpeta_datos() / "historial.db"
        with closing(self._conectar()) as con, con:
            con.executescript(ESQUEMA)

    def _conectar(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.ruta)
        con.row_factory = sqlite3.Row
        return con

    @staticmethod
    def _fila(estudiante_id, nombre, origen, probabilidad, semaforo, umbral, perfil, entradas, notas):
        return (
            datetime.now().isoformat(timespec="seconds"),
            str(estudiante_id or "").strip(),
            str(nombre or "").strip(),
            origen,
            float(probabilidad),
            semaforo,
            float(umbral),
            json.dumps({k: float(v) for k, v in perfil.items()}),
            json.dumps({k: float(v) for k, v in entradas.items()}),
            notas or "",
            __version__,
        )

    _INSERT = """INSERT INTO evaluaciones (fecha, estudiante_id, nombre, origen, probabilidad,
                 semaforo, umbral, perfil_json, entradas_json, notas, app_version)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

    def guardar(self, *, estudiante_id, nombre, origen, probabilidad, semaforo, umbral,
                perfil, entradas, notas="") -> int:
        with closing(self._conectar()) as con, con:
            cur = con.execute(self._INSERT, self._fila(
                estudiante_id, nombre, origen, probabilidad, semaforo, umbral, perfil, entradas, notas
            ))
            return int(cur.lastrowid)

    def guardar_lote(self, filas: list[dict]) -> int:
        """Guarda muchas evaluaciones en una transacción. Cada dict usa las claves de `guardar`."""
        valores = [
            self._fila(f.get("estudiante_id"), f.get("nombre", ""), "lote", f["probabilidad"],
                       f["semaforo"], f["umbral"], f["perfil"], f["perfil"], f.get("notas", ""))
            for f in filas
        ]
        with closing(self._conectar()) as con, con:
            con.executemany(self._INSERT, valores)
        return len(valores)

    def buscar(self, texto: str = "", semaforo: str | None = None, origen: str | None = None,
               desde: str | None = None, limite: int = 5000) -> list[Registro]:
        """Filtra por texto (ID, nombre, notas), nivel, origen y fecha mínima (ISO, p. ej. «2026-11-01»)."""
        sql = "SELECT * FROM evaluaciones WHERE 1=1"
        params: list = []
        if desde:
            sql += " AND fecha >= ?"
            params.append(desde)
        if texto.strip():
            sql += " AND (estudiante_id LIKE ? OR nombre LIKE ? OR notas LIKE ?)"
            patron = f"%{texto.strip()}%"
            params += [patron, patron, patron]
        if semaforo:
            sql += " AND semaforo = ?"
            params.append(semaforo)
        if origen:
            sql += " AND origen = ?"
            params.append(origen)
        sql += " ORDER BY fecha DESC, probabilidad DESC, id DESC LIMIT ?"
        params.append(limite)
        with closing(self._conectar()) as con:
            return [self._registro(r) for r in con.execute(sql, params)]

    def fecha_archivo_guardado(self, nombre_archivo: str) -> str | None:
        """Fecha del último guardado de un archivo de evaluación (None si nunca se guardó)."""
        with closing(self._conectar()) as con:
            fila = con.execute(
                "SELECT MAX(fecha) FROM evaluaciones WHERE origen = 'lote' AND (notas = ? OR notas LIKE ?)",
                (f"Archivo: {nombre_archivo}", f"Archivo: {nombre_archivo} · %"),
            ).fetchone()
        return fila[0] if fila and fila[0] else None

    def obtener(self, registro_id: int) -> Registro | None:
        with closing(self._conectar()) as con:
            fila = con.execute("SELECT * FROM evaluaciones WHERE id = ?", (registro_id,)).fetchone()
        return self._registro(fila) if fila else None

    def actualizar_notas(self, registro_id: int, notas: str) -> None:
        with closing(self._conectar()) as con, con:
            con.execute("UPDATE evaluaciones SET notas = ? WHERE id = ?", (notas, registro_id))

    def eliminar(self, ids: list[int]) -> int:
        if not ids:
            return 0
        marcas = ",".join("?" * len(ids))
        with closing(self._conectar()) as con, con:
            return con.execute(f"DELETE FROM evaluaciones WHERE id IN ({marcas})", ids).rowcount

    def contar(self) -> int:
        with closing(self._conectar()) as con:
            return int(con.execute("SELECT COUNT(*) FROM evaluaciones").fetchone()[0])

    @staticmethod
    def _registro(r: sqlite3.Row) -> Registro:
        return Registro(
            id=r["id"], fecha=r["fecha"], estudiante_id=r["estudiante_id"], nombre=r["nombre"],
            origen=r["origen"], probabilidad=r["probabilidad"], semaforo=r["semaforo"],
            umbral=r["umbral"], perfil=json.loads(r["perfil_json"]),
            entradas=json.loads(r["entradas_json"]), notas=r["notas"], app_version=r["app_version"],
        )
