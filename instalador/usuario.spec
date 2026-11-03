# Empacotamento do AgendaUsuario.exe (PyInstaller): o programa dos usuários, que acha o
# servidor da agenda na rede e abre o sistema no navegador. Um único arquivo, sem janela.
# Uso (na raiz do projeto):  pyinstaller instalador/usuario.spec
import os

RAIZ = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(RAIZ, "cliente", "agenda_usuario.py")],
    excludes=["tkinter", "pytest", "flask", "PIL", "cryptography"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="AgendaUsuario",
    icon=os.path.join(SPECPATH, "icone.ico"),
    console=False,
)
