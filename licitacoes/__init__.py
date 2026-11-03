"""Agenda de Licitações — aplicação web para intranet."""
__version__ = "1.1.0"
import os
import secrets
from datetime import datetime

import click
from flask import Flask, Response, abort, g, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from . import brasao, cripto, db, parametros, senhas
from .perfis import PERFIS


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    # Banco, chave das sessões e brasão ficam na pasta de dados. Numa instalação em pasta
    # compartilhada, ela deve ficar FORA do compartilhamento (variável AGENDA_DADOS ou
    # opção --dados do servidor), para os usuários da rede não copiarem nem alterarem o banco.
    dados = (config or {}).get("PASTA_DADOS") or os.environ.get("AGENDA_DADOS") \
        or app.instance_path
    os.makedirs(dados, exist_ok=True)

    app.config.update(
        PASTA_DADOS=dados,
        DATABASE=os.path.join(dados, "licitacoes.sqlite3"),
        SECRET_KEY=os.environ.get("SECRET_KEY") or _chave_secreta(dados),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=8 * 60 * 60,  # uma jornada de trabalho
        NOME_ORGAO=os.environ.get("NOME_ORGAO", "Secretaria"),
        PASTA_ARQUIVOS=dados,                  # brasão e outros arquivos enviados
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,     # limite de envio de arquivos
    )
    if config:
        app.config.update(config)
    if not app.config.get("CHAVE_DADOS"):
        app.config["CHAVE_DADOS"] = cripto.carregar_chave(app.config["PASTA_DADOS"])

    app.teardown_appcontext(db.close_db)
    app.before_request(_validar_csrf)
    _registrar_filtros(app)
    _registrar_erros(app)
    _registrar_comandos(app)

    from . import admin, agenda, auth, config as configuracoes

    app.register_blueprint(auth.bp)
    app.register_blueprint(agenda.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(configuracoes.bp)

    @app.route("/agenda-licitacoes.json")
    def identificacao():
        """Usado pelo programa dos usuários para confirmar que o endereço é o da agenda."""
        return {"sistema": "agenda-licitacoes", "versao": __version__}

    @app.route("/brasao.png")
    def imagem_brasao():
        if not brasao.existe():
            abort(404)
        return Response(brasao.conteudo(), mimetype="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})

    with app.app_context():
        db.init_db()

    return app


def _chave_secreta(pasta):
    """Gera (uma única vez) e reaproveita a chave de assinatura das sessões."""
    caminho = os.path.join(pasta, "secret_key")
    if not os.path.exists(caminho):
        with open(caminho, "w") as f:
            f.write(secrets.token_hex(32))
    with open(caminho) as f:
        return f.read().strip()


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def _validar_csrf():
    if request.method == "POST":
        token = request.form.get("_csrf", "")
        if not token or not secrets.compare_digest(token, session.get("_csrf", "")):
            abort(400, "Formulário expirado. Recarregue a página e tente novamente.")


def _registrar_filtros(app):
    @app.template_filter("data")
    def formatar_data(valor, com_hora=True):
        if not valor:
            return ""
        dt = datetime.fromisoformat(valor)
        return dt.strftime("%d/%m/%Y %H:%M" if com_hora else "%d/%m/%Y")

    @app.template_filter("moeda")
    def formatar_moeda(valor):
        if valor is None:
            return "—"
        texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {texto}"

    @app.context_processor
    def globais():
        usuario = g.get("usuario")
        return {
            "csrf_token": csrf_token,
            "pode": lambda p: bool(usuario) and parametros.tem_permissao(usuario["perfil"], p),
            "PERFIS": PERFIS,
            "nome_orgao": parametros.nome_orgao(),
            "edital": parametros.edital,
            "cor_modalidade": parametros.cores_modalidade,
            "cores_situacao": parametros.cores_situacao,
            "nome_situacao": lambda chave: parametros.situacao(chave)["nome"],
            "situacoes_ativas": lambda: parametros.situacoes(somente_ativas=True),
            "fase_de": parametros.fase,
            "brasao_url": (url_for("imagem_brasao", v=brasao.versao())
                           if brasao.existe() else None),
            "modalidade_de": parametros.modalidade,
        }


def _registrar_erros(app):
    mensagens = {
        400: ("Requisição inválida", None),
        403: ("Acesso negado", "Seu perfil não tem permissão para esta operação."),
        404: ("Página não encontrada", "O endereço ou registro solicitado não existe."),
    }

    def tratar(erro):
        titulo, mensagem = mensagens[erro.code]
        return render_template("erro.html", codigo=erro.code, titulo=titulo,
                               mensagem=mensagem or erro.description), erro.code

    for codigo in mensagens:
        app.register_error_handler(codigo, tratar)


def _registrar_comandos(app):
    @app.cli.command("criar-admin")
    @click.option("--login", default="admin", show_default=True)
    @click.password_option(help="Senha do administrador.")
    def criar_admin(login, password):
        """Cria (ou redefine a senha de) um usuário administrador."""
        conn = db.get_db()
        existente = conn.execute("SELECT * FROM usuarios WHERE login = ?",
                                 (cripto.indice_login(login),)).fetchone()
        anteriores = (existente["senha_hash"], existente["senha_anterior_hash"]) \
            if existente else ()
        motivo = senhas.problema(password, login=login, anteriores=anteriores)
        if motivo:
            raise click.ClickException(motivo)
        senha_hash = generate_password_hash(password)
        if existente:
            conn.execute(
                "UPDATE usuarios SET senha_hash = ?, senha_anterior_hash = ?,"
                " perfil = 'administrador', ativo = 1, trocar_senha = 0 WHERE id = ?",
                (senha_hash, existente["senha_hash"], existente["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO usuarios (nome, login, login_cifrado, senha_hash, perfil,"
                " trocar_senha) VALUES (?, ?, ?, ?, 'administrador', 0)",
                ("Administrador", cripto.indice_login(login), cripto.cifrar_login(login),
                 senha_hash),
            )
        conn.commit()
        click.echo(f"Administrador '{login}' pronto para uso.")

