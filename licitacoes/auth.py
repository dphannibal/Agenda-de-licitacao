"""Autenticação, sessão e controle de acesso por perfil."""
import functools

from flask import (
    Blueprint, abort, current_app, flash, g, redirect, render_template, request, session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db, registrar
from .parametros import tem_permissao

bp = Blueprint("auth", __name__)

TAMANHO_MINIMO_SENHA = 8
# A configuração inicial só pode ser feita no próprio computador servidor: assim ninguém
# da rede se adianta e vira administrador de uma instalação nova.
ENDERECOS_LOCAIS = {"127.0.0.1", "::1"}


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
    # Instalação nova, sem administrador: tudo leva à configuração inicial.
    if request.endpoint not in ("static", "auth.configuracao_inicial") \
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
            "SELECT * FROM usuarios WHERE login = ?", (login_informado,)
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
            registrar("Login", referencia=usuario["login"])
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
        if not nome or not login_escolhido:
            erros.append("Informe o nome e o usuário.")
        if len(senha) < TAMANHO_MINIMO_SENHA:
            erros.append(f"A senha deve ter ao menos {TAMANHO_MINIMO_SENHA} caracteres.")
        elif senha != request.form.get("confirmacao", ""):
            erros.append("A confirmação não confere com a senha.")
        elif get_db().execute("SELECT 1 FROM usuarios WHERE login = ?",
                              (login_escolhido,)).fetchone():
            erros.append("Já existe um usuário com esse login; escolha outro.")
        for erro in erros:
            flash(erro, "erro")
        if not erros:
            conn = get_db()
            cursor = conn.execute(
                "INSERT INTO usuarios (nome, login, senha_hash, perfil, trocar_senha)"
                " VALUES (?, ?, ?, 'administrador', 0)",
                (nome, login_escolhido, generate_password_hash(senha)),
            )
            registrar("Configuração inicial: administrador criado", referencia=login_escolhido)
            conn.commit()
            current_app.config["_TEM_ADMINISTRADOR"] = True
            session.clear()
            session.permanent = True
            session["usuario_id"] = cursor.lastrowid
            flash("Administrador criado. Agora cadastre os servidores e os demais usuários.",
                  "sucesso")
            return redirect(url_for("agenda.painel"))

    return render_template("auth/configuracao_inicial.html", remoto=False)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/senha", methods=["GET", "POST"])
@login_obrigatorio
def trocar_senha():
    if request.method == "POST":
        atual = request.form.get("senha_atual", "")
        nova = request.form.get("nova_senha", "")
        confirmacao = request.form.get("confirmacao", "")

        if not check_password_hash(g.usuario["senha_hash"], atual):
            flash("A senha atual não confere.", "erro")
        elif len(nova) < TAMANHO_MINIMO_SENHA:
            flash(f"A nova senha deve ter ao menos {TAMANHO_MINIMO_SENHA} caracteres.", "erro")
        elif nova != confirmacao:
            flash("A confirmação não confere com a nova senha.", "erro")
        elif nova == atual:
            flash("A nova senha deve ser diferente da atual.", "erro")
        else:
            conn = get_db()
            conn.execute(
                "UPDATE usuarios SET senha_hash = ?, trocar_senha = 0 WHERE id = ?",
                (generate_password_hash(nova), g.usuario["id"]),
            )
            registrar("Troca de senha", referencia=g.usuario["login"])
            conn.commit()
            flash("Senha alterada com sucesso.", "sucesso")
            return redirect(url_for("agenda.painel"))

    return render_template("auth/senha.html")
