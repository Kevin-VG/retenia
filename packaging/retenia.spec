# PyInstaller: genera dist/RetenIA/ (modo carpeta, sin consola).
#
#     pyinstaller packaging/retenia.spec --noconfirm --clean
#
# Se usa modo carpeta (onedir) en vez de un solo .exe: arranca más rápido y
# provoca menos falsos positivos en antivirus.
import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

RAIZ = Path(SPECPATH).parent
VERSION = re.search(r'__version__ = "([^"]+)"', (RAIZ / "app" / "__init__.py").read_text()).group(1)

# El pipeline se des-serializa con pickle: sus clases no aparecen en imports estáticos
ocultos = (
    collect_submodules("sklearn.ensemble")
    + collect_submodules("sklearn.compose")
    + collect_submodules("sklearn.preprocessing")
    + collect_submodules("sklearn.pipeline")
    + collect_submodules("sklearn.tree")
    + ["sklearn.utils._typedefs", "sklearn.neighbors._partition_nodes"]
)

# Información de versión visible en Propiedades → Detalles del .exe
partes = tuple(int(p) for p in VERSION.split(".")) + (0,)
info_version = RAIZ / "build" / "version_info.txt"
info_version.parent.mkdir(exist_ok=True)
info_version.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={partes}, prodvers={partes}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040A04B0', [
      StringStruct('CompanyName', 'Kevin Ventura'),
      StringStruct('FileDescription', 'RetenIA - Alerta temprana de desercion universitaria'),
      StringStruct('FileVersion', '{VERSION}'),
      StringStruct('InternalName', 'RetenIA'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('OriginalFilename', 'RetenIA.exe'),
      StringStruct('ProductName', 'RetenIA'),
      StringStruct('ProductVersion', '{VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [0x040A, 1200])])
  ]
)
""", encoding="utf-8")

a = Analysis(
    [str(RAIZ / "app" / "main.py")],
    pathex=[str(RAIZ)],
    datas=[(str(RAIZ / "app" / "resources"), "app/resources")],
    hiddenimports=ocultos,
    excludes=[
        "tkinter", "matplotlib", "IPython", "jupyter", "notebook", "pytest",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQuick",
        "PySide6.QtQml", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts",
        "PySide6.QtDataVisualization", "PySide6.QtBluetooth", "PySide6.QtNetwork",
    ],
    noarchive=False,
)

# Quitar piezas de Qt que una app de widgets no usa (~40 MB menos)
def _innecesario(destino: str) -> bool:
    nombre = Path(destino).name.lower()
    if nombre == "opengl32sw.dll":  # OpenGL por software
        return True
    if nombre.startswith(("qt6quick", "qt6qml", "qt6pdf", "qt6virtualkeyboard")):
        return True
    partes_ruta = Path(destino).parts
    # Traducciones de Qt: solo español
    return "translations" in partes_ruta and nombre.endswith(".qm") and "_es" not in nombre


a.binaries = [b for b in a.binaries if not _innecesario(b[0])]
a.datas = [d for d in a.datas if not _innecesario(d[0])]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RetenIA",
    icon=str(RAIZ / "app" / "resources" / "icon.ico"),
    version=str(info_version),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="RetenIA", upx=False)
