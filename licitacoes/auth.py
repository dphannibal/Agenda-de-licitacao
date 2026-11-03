"""Autenticação, sessão e controle de acesso por perfil."""
import functools
import re

from flask import (
    Blueprint, abort, current_app, flash, g, redirect, render_template, request, session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from . import cripto, db, nuvem, senhas
from .db import get_db, registrar
from . import parametros
from .parametros import tem_permissao

bp = Blueprint("auth", __name__)

# A configuração inicial só pode ser feita no próprio computador servidor: assim ninguém
# da rede se adianta e vira administrador de uma instalação nova.
ENDERECOS_LOCAIS = {"127.0.0.1", "::1"}
# Atendidas mesmo antes da configuração inicial ou da recuperação.
SEMPRE_LIVRES = ("static", "identificacao")
FORMATO_LOGIN = re.compile(r"^[a-zA-Z0-9._-]{3,40}$")


def _nuvem():
    return current_app.config.get("NUVEM")


def aguardando_recuperacao():
    return bool(_nuvem()) and _nuvem().estado == nuvem.AGUARDANDO


def falta_senha_recuperacao():
    return bool(_nuvem()) and _nuvem().estado == nuvem.SEM_SENHA


def problema_na_senha_recuperacao(senha, confirmacao, outras=()):
    motivo = senhas.problema(senha)
    if motivo:
        return "Senha de recuperação: " + motivo[0].lower() + motivo[1:]
    if senha != confirmacao:
        return "A confirmação não confere com a senha de recuperação."
    if senha in outras:
        return "A senha de recuperação deve ser diferente da senha do administrador."
    return None


def existe_administrador():
    """Há algum administrador ativo? Uma vez que sim, fica guardado: o sistema impede
    que o último administrador perca o acesso."""
    if not current_app.config.get("_TEM_ADMINISTRADOR"):
        achou = get_db().execute(
            "SELECT 1 FROM usuarios WHERE perfil = 'administrador' AND ativo = 1 LIMIT 1"
        ).fetchone()
        current_app.config["_TEM_ADMINISTRADOR"] = bool(achou)
    return current_app.config["_TEM_ADMINISTRADOR"]


@bp.before_app_request
def carregar_usuario():
    # Computador assumindo a agenda: antes de tudo, a senha de recuperação das cópias.
    if aguardando_recuperacao():
        if request.endpoint not in SEMPRE_LIVRES + ("auth.recuperacao",):
            return redirect(url_for("auth.recuperacao"))
    # Instalação nova, sem administrador: tudo leva à configuração inicial.
    elif request.endpoint not in SEMPRE_LIVRES + ("auth.configuracao_inicial",) \
            and not existe_administrador():
        return redirect(url_for("auth.configuracao_inicial"))

    usuario_id = session.get("usuario_id")
    g.usuario = None
    if usuario_id is not None:
        g.usuario = get_db().execute(
            "SELECT * FROM usuarios WHERE id = ? AND ativo = 1", (usuario_id,)
        ).fetchone()
        if g.usuario is None:
            session.clear()

    # Quem está com senha temporária precisa trocá-la antes de qualquer coisa.
    livres = {"auth.trocar_senha", "auth.logout", "static"}
    if g.usuario and g.usuario["trocar_senha"] and request.endpoint not in livres:
        return redirect(url_for("auth.trocar_senha"))


def login_obrigatorio(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if g.usuario is None:
            return redirect(url_for("auth.login", proximo=request.full_path))
        return view(*args, **kwargs)

    return wrapper


def permissao(*nomes):
    """Exige ao menos uma das permissões informadas."""
    def decorador(view):
        @functools.wraps(view)
        @login_obrigatorio
        def wrapper(*args, **kwargs):
            if not any(tem_permissao(g.usuario["perfil"], n) for n in nomes):
                abort(403)
            return view(*args, **kwargs)

        return wrapper

    return decorador


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.usuario:
        return redirect(url_for("agenda.painel"))

    if request.method == "POST":
        login_informado = request.form.get("login", "").strip()
        senha = request.form.get("senha", "")
        usuario = get_db().execute(
            "SELECT * FROM usuarios WHERE login = ?", (cripto.indice_login(login_informado),)
        ).fetchone()

        if usuario is None or not check_password_hash(usuario["senha_hash"], senha):
            flash("Usuário ou senha inválidos.", "erro")
        elif not usuario["ativo"]:
            flash("Usuário desativado. Procure o administrador do sistema.", "erro")
        else:
            session.clear()
            session.permanent = True
            session["usuario_id"] = usuario["id"]
            g.usuario = usuario
            registrar("Login", referencia=usuario["nome"])
            get_db().commit()
            proximo = request.args.get("proximo", "")
            # Só redireciona para caminhos internos, nunca para outro site.
            if proximo.startswith("/") and not proximo.startswith("//"):
                return redirect(proximo)
            return redirect(url_for("agenda.painel"))

    return render_template("auth/login.html")


@bp.route("/configuracao-inicial", methods=["GET", "POST"])
def configuracao_inicial():
    if existe_administrador():
        abort(404)
    if request.remote_addr not in ENDERECOS_LOCAIS:
        return render_template("auth/configuracao_inicial.html", remoto=True), 403

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        login_escolhido = request.form.get("login", "").strip()
        senha = request.form.get("senha", "")
        erros = []
        motivo = senhas.problema(senha, login=login_escolhido, nome=nome)
        if not nome or not FORMATO_LOGIN.match(login_escolhido):
            erros.append("Informe o nome e um login de 3 a 40 caracteres: letras, números, "
                         "ponto, hífen ou _.")
        elif motivo:
            erros.append(motivo)
        elif senha != request.form.get("confirmacao", ""):
            erros.append("A confirmação não confere com a senha.")
        elif get_db().execute("SELECT 1 FROM usuarios WHERE login = ?",
                              (cripto.indice_login(login_escolhido),)).fetchone():
            erros.append("Já existe um usuário com esse login; escolha outro.")
        senha_recuperacao = request.form.get("recuperacao", "")
        if not erros and falta_senha_recuperacao():
            motivo = problema_na_senha_recuperacao(
                senha_recuperacao, request.form.get("recuperacao_confirmacao", ""), (senha,))
            if motivo:
                erros.append(motivo)
        for erro in erros:
            flash(erro, "erro")
        if not erros:
            conn = get_db()
            cursor = conn.execute(
                "INSERT INTO usuarios (nome, login, login_cifrado, senha_hash, perfil,"
                " trocar_senha) VALUES (?, ?, ?, ?, 'administrador', 0)",
                (nome, cripto.indice_login(login_escolhido), cripto.cifrar_login(login_escolhido),
                 generate_password_hash(senha)),
            )
            registrar("Configuração inicial: administrador criado", referencia=nome)
            conn.commit()
            current_app.config["_TEM_ADMINISTRADOR"] = True
            if falta_senha_recuperacao():
                _nuvem().definir_senha_recuperacao(senha_recuperacao)
            session.clear()
            session.permanent = True
            session["usuario_id"] = cursor.lastrowid
            flash("Administrador criado. Agora cadastre os servidores e os demais usuários.",
                  "sucesso")
            return redirect(url_for("agenda.painel"))

    return render_template("auth/configuracao_inicial.html", remoto=False,
                           pedir_recuperacao=falta_senha_recuperacao())


@bp.route("/recuperacao", methods=["GET", "POST"])
def recuperacao():
    """Outro computador assumindo a agenda: a senha de recuperação abre as cópias da nuvem."""
    if not aguardando_recuperacao():
        abort(404)
    if request.remote_addr not in ENDERECOS_LOCAIS:
        return render_template("auth/recuperacao.html", remoto=True), 403
    if request.method == "POST":
        db.close_db()  # o banco deste computador vai ser substituído pela cópia
        try:
            mensagem = _nuvem().recuperar(request.form.get("senha", ""))
        except ValueError as erro:
            flash(str(erro), "erro")
        else:
            current_app.config["CHAVE_DADOS"] = cripto.carregar_chave(
                current_app.config["PASTA_DADOS"])
            current_app.config["_TEM_ADMINISTRADOR"] = False
            db.init_db()
            parametros.invalidar()
            session.clear()
            flash(mensagem or "Chave recuperada.", "sucesso")
            return redirect(url_for("auth.login"))
    return render_template("auth/recuperacao.html", remoto=False)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


def _senha_pessoal(usuario):
    """Hash da última senha escolhida pelo próprio usuário (a temporária não conta)."""
    return usuario["senha_anterior_hash"] if usuario["trocar_senha"] else usuario["senha_hash"]


@bp.route("/senha", methods=["GET", "POST"])
@login_obrigatorio
def trocar_senha():
    if request.method == "POST":
        atual = request.form.get("senha_atual", "")
        nova = request.form.get("nova_senha", "")
        confirmacao = request.form.get("confirmacao", "")

        usuario = g.usuario
        motivo = senhas.problema(
            nova, login=cripto.decifrar_login(usuario["login_cifrado"]), nome=usuario["nome"],
            anteriores=(usuario["senha_hash"], usuario["senha_anterior_hash"]))
        if not check_password_hash(usuario["senha_hash"], atual):
            flash("A senha atual não confere.", "erro")
        elif motivo:
            flash(motivo, "erro")
        elif nova != confirmacao:
            flash("A confirmação não confere com a nova senha.", "erro")
        else:
            conn = get_db()
            conn.execute(
                "UPDATE usuarios SET senha_hash = ?, senha_anterior_hash = ?, trocar_senha = 0"
                " WHERE id = ?",
                (generate_password_hash(nova), _senha_pessoal(usuario), usuario["id"]),
            )
            registrar("Troca de senha", referencia=usuario["nome"])
            conn.commit()
            flash("Senha alterada com sucesso.", "sucesso")
            return redirect(url_for("agenda.painel"))

    return render_template("auth/senha.html")
