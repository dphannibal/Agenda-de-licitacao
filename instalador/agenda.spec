# Empacotamento do AgendaLicitacoes.exe (PyInstaller): Python, telas, estilos e fontes
# embutidos, para o computador hospedeiro não precisar ter o Python instalado.
# Uso (na raiz do projeto):  pyinstaller instalador/agenda.spec
import os

RAIZ = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(RAIZ, "servidor.py")],
    pathex=[RAIZ],
    datas=[
        (os.path.join(RAIZ, "licitacoes", "templates"), os.path.join("licitacoes", "templates")),
        (os.path.join(RAIZ, "licitacoes", "static"), os.path.join("licitacoes", "static")),
    ],
    hiddenimports=["licitacoes.admin", "licitacoes.agenda", "licitacoes.auth",
                   "licitacoes.config"],
    excludes=["tkinter", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AgendaLicitacoes",
    icon=os.path.join(SPECPATH, "icone.ico"),
    console=True,
)
coll = COLLECT(exe, a.binaries, a.datas, name="AgendaLicitacoes")
