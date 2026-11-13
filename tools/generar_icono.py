"""Genera app/resources/icon.png (512 px) e icon.ico (16–256 px) dibujados con Qt.

    python tools/generar_icono.py
"""
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath

RECURSOS = Path(__file__).resolve().parents[1] / "app" / "resources"
TAMANOS_ICO = (16, 24, 32, 48, 64, 128, 256)


def dibujar(lado: int) -> QImage:
    img = QImage(lado, lado, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    s = lado / 256

    # Fondo: cuadrado redondeado con degradado azul → marino
    fondo = QPainterPath()
    fondo.addRoundedRect(QRectF(8 * s, 8 * s, 240 * s, 240 * s), 52 * s, 52 * s)
    grad = QLinearGradient(0, 0, lado, lado)
    grad.setColorAt(0, QColor("#2563eb"))
    grad.setColorAt(1, QColor("#0c1938"))
    p.fillPath(fondo, grad)

    # Letra R
    fuente = QFont("Segoe UI", 1, QFont.Weight.Black)
    fuente.setPixelSize(int(170 * s))
    p.setFont(fuente)
    p.setPen(QColor("#ffffff"))
    p.drawText(QRectF(18 * s, 20 * s, 160 * s, 216 * s), Qt.AlignmentFlag.AlignCenter, "R")

    # Semáforo vertical
    capsula = QPainterPath()
    capsula.addRoundedRect(QRectF(176 * s, 52 * s, 52 * s, 152 * s), 26 * s, 26 * s)
    p.fillPath(capsula, QColor(255, 255, 255, 40))
    for i, color in enumerate(("#ef4444", "#f59e0b", "#22c55e")):
        p.setBrush(QColor(color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(186 * s, (62 + i * 46) * s, 32 * s, 32 * s))
    p.end()
    return img


def png_bytes(img: QImage) -> bytes:
    datos = QByteArray()
    buf = QBuffer(datos)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(datos)


def escribir_ico(ruta: Path, imagenes: list[tuple[int, bytes]]) -> None:
    """ICO con entradas PNG (formato admitido desde Windows Vista)."""
    cabecera = struct.pack("<HHH", 0, 1, len(imagenes))
    desplazamiento = 6 + 16 * len(imagenes)
    entradas, cuerpos = b"", b""
    for lado, datos in imagenes:
        dim = 0 if lado >= 256 else lado
        entradas += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(datos), desplazamiento)
        desplazamiento += len(datos)
        cuerpos += datos
    ruta.write_bytes(cabecera + entradas + cuerpos)


def main() -> None:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841 - necesario para fuentes
    RECURSOS.mkdir(parents=True, exist_ok=True)
    dibujar(512).save(str(RECURSOS / "icon.png"))
    escribir_ico(RECURSOS / "icon.ico", [(t, png_bytes(dibujar(t))) for t in TAMANOS_ICO])
    print(f"Generados {RECURSOS / 'icon.png'} y {RECURSOS / 'icon.ico'}")


if __name__ == "__main__":
    main()
