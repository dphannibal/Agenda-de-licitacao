"""Administração de usuários e trilha de auditoria."""
import secrets
from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from . import cripto
from .auth import FORMATO_LOGIN, _senha_pessoal, permissao
from .db import get_db, registrar
from . import parametros as P
from .perfis import FASES_ABERTAS, PERFIS, PERMISSOES, TIPOS_AFASTAMENTO, VINCULOS, VINCULOS_EFETIVOS


def _descricoes_perfis():
    """Resumo do que cada perfil pode fazer, conforme as permissões configuradas."""
    return {perfil: "; ".join(PERMISSOES[p] for p in PERMISSOES if p in P.permissoes().get(
        perfil, set())) or "Nenhuma permissão" for perfil in PERFIS}

bp = Blueprint("admin", __name__, url_prefix="/admin")

ITENS_POR_PAGINA = 50


def _buscar_usuario(id_):
    usuario = get_db().execute("SELECT * FROM usuarios WHERE id = ?", (id_,)).fetchone()
    if usuario is None:
        abort(404)
    return usuario


def _senha_temporaria():
    return secrets.token_urlsafe(9)


@bp.route("/usuarios")
@permissao("usuarios")
def usuarios():
    lista = [cripto.com_login(u) for u in
             get_db().execute("SELECT * FROM usuarios ORDER BY ativo DESC, nome")]
    return render_template("admin/usuarios.html", usuarios=lista, descricoes=_descricoes_perfis())


@bp.route("/usuarios/novo", methods=["GET", "POST"])
@permissao("usuarios")
def novo_usuario():
    dados = {"perfil": "consulta"}
    if request.method == "POST":
        dados = {c: request.form.get(c, "").strip() for c in ("nome", "login", "email", "perfil")}
        conn = get_db()
        erros = []
        if not dados["nome"]:
            erros.append("Informe o nome.")
        if not FORMATO_LOGIN.match(dados["login"]):
            erros.append("Login deve ter de 3 a 40 caracteres: letras, números, ponto, hífen ou _.")
        elif conn.execute("SELECT 1 FROM usuarios WHERE login = ?",
                          (cripto.indice_login(dados["login"]),)).fetchone():
            erros.append("Já existe um usuário com esse login.")
        if dados["perfil"] not in PERFIS:
            erros.append("Selecione um perfil válido.")

        if erros:
            for e in erros:
                flash(e, "erro")
        else:
            senha = _senha_temporaria()
            conn.execute(
                "INSERT INTO usuarios (nome, login, login_cifrado, email, senha_hash, perfil,"
                " trocar_senha) VALUES (?, ?, ?, ?, ?, ?, 1)",
                (dados["nome"], cripto.indice_login(dados["login"]),
                 cripto.cifrar_login(dados["login"]), dados["email"] or None,
                 generate_password_hash(senha), dados["perfil"]),
            )
            registrar("Cadastro de usuário", referencia=dados["nome"],
                      detalhes=f"Perfil: {PERFIS[dados['perfil']]}")
            conn.commit()
            flash(f"Usuário criado. Senha temporária de “{dados['login']}”: {senha} — "
                  "anote e entregue ao usuário; ela será trocada no primeiro acesso.", "sucesso")
            return redirect(url_for("admin.usuarios"))

    return render_template("admin/usuario_form.html", dados=dados, descricoes=_descricoes_perfis(),
                           novo=True)


@bp.route("/usuarios/<int:id_>/editar", methods=["GET", "POST"])
@permissao("usuarios")
def editar_usuario(id_):
    usuario = _buscar_usuario(id_)
    dados = cripto.com_login(usuario)
    if request.method == "POST":
        dados.update({c: request.form.get(c, "").strip() for c in ("nome", "email", "perfil")})
        dados["ativo"] = 1 if request.form.get("ativo") else 0
        proprio = usuario["id"] == g.usuario["id"]

        erros = []
        if not dados["nome"]:
            erros.append("Informe o nome.")
        if dados["perfil"] not in PERFIS:
            erros.append("Selecione um perfil válido.")
        if proprio and (dados["perfil"] != "administrador" or not dados["ativo"]):
            erros.append("Você não pode remover o próprio acesso de administrador.")

        if erros:
            for e in erros:
                flash(e, "erro")
        else:
            mudancas = []
            if dados["perfil"] != usuario["perfil"]:
                mudancas.append(f"Perfil: {PERFIS[usuario['perfil']]} → {PERFIS[dados['perfil']]}")
            if dados["ativo"] != usuario["ativo"]:
                mudancas.append("Reativado" if dados["ativo"] else "Desativado")
            if dados["nome"] != usuario["nome"]:
                mudancas.append(f"Nome: {usuario['nome']} → {dados['nome']}")
            if (dados["email"] or None) != usuario["email"]:
                mudancas.append("E-mail alterado")

            conn = get_db()
            conn.execute(
                "UPDATE usuarios SET nome = ?, email = ?, perfil = ?, ativo = ? WHERE id = ?",
                (dados["nome"], dados["email"] or None, dados["perfil"], dados["ativo"], id_),
            )
            if mudancas:
                registrar("Alteração de usuário", referencia=usuario["nome"],
                          detalhes="; ".join(mudancas))
            conn.commit()
            flash("Usuário atualizado.", "sucesso")
            return redirect(url_for("admin.usuarios"))

    return render_template("admin/usuario_form.html", dados=dados, descricoes=_descricoes_perfis(),
                           novo=False)


@bp.route("/usuarios/<int:id_>/redefinir-senha", methods=["POST"])
@permissao("usuarios")
def redefinir_senha(id_):
    usuario = _buscar_usuario(id_)
    senha = _senha_temporaria()
    conn = get_db()
    conn.execute(
        "UPDATE usuarios SET senha_hash = ?, senha_anterior_hash = ?, trocar_senha = 1"
        " WHERE id = ?",
        (generate_password_hash(senha), _senha_pessoal(usuario), id_),
    )
    registrar("Redefinição de senha", referencia=usuario["nome"])
    conn.commit()
    flash(f"Nova senha temporária de “{cripto.decifrar_login(usuario['login_cifrado'])}”: "
          f"{senha}", "sucesso")
    return redirect(url_for("admin.usuarios"))


@bp.route("/servidores")
@permissao("servidores", "afastamentos")
def servidores():
    lista = get_db().execute(
        "SELECT s.*, (SELECT COUNT(*) FROM licitacoes l"
        "             WHERE s.id IN (l.agente_id, l.membro1_id, l.membro2_id, l.membro3_id))"
        "             AS escalas,"
        "       (SELECT a.tipo || ' até ' || strftime('%d/%m/%Y', a.fim) FROM afastamentos a"
        "         WHERE a.servidor_id = s.id"
        "           AND date('now', 'localtime') BETWEEN a.inicio AND a.fim) AS afastado,"
        "       (SELECT a.tipo || ' a partir de ' || strftime('%d/%m/%Y', a.inicio)"
        "          FROM afastamentos a WHERE a.servidor_id = s.id"
        "           AND a.inicio > date('now', 'localtime') ORDER BY a.inicio LIMIT 1)"
        "             AS proximo_afastamento"
        "  FROM servidores s ORDER BY s.ativo DESC, s.nome"
    ).fetchall()
    return render_template("admin/servidores.html", servidores=lista, vinculos=VINCULOS,
                           efetivos=VINCULOS_EFETIVOS)


@bp.route("/servidores/novo", methods=["GET", "POST"], defaults={"id_": None})
@bp.route("/servidores/<int:id_>/editar", methods=["GET", "POST"])
@permissao("servidores")
def servidor_form(id_):
    conn = get_db()
    atual = None
    if id_ is not None:
        atual = conn.execute("SELECT * FROM servidores WHERE id = ?", (id_,)).fetchone()
        if atual is None:
            abort(404)
    dados = dict(atual) if atual else {"vinculo": "efetivo", "ativo": 1}

    if request.method == "POST":
        dados = {c: request.form.get(c, "").strip() for c in ("nome", "matricula", "vinculo")}
        dados["ativo"] = 1 if (request.form.get("ativo") or atual is None) else 0
        erros = []
        if not dados["nome"]:
            erros.append("Informe o nome do servidor.")
        if dados["vinculo"] not in VINCULOS:
            erros.append("Selecione o vínculo do servidor.")
        if erros:
            for e in erros:
                flash(e, "erro")
        else:
            valores = (dados["nome"], dados["matricula"] or None, dados["vinculo"], dados["ativo"])
            if atual is None:
                conn.execute("INSERT INTO servidores (nome, matricula, vinculo, ativo)"
                             " VALUES (?, ?, ?, ?)", valores)
                registrar("Cadastro de servidor", referencia=dados["nome"],
                          detalhes=f"Vínculo: {VINCULOS[dados['vinculo']]}")
            else:
                conn.execute("UPDATE servidores SET nome = ?, matricula = ?, vinculo = ?,"
                             " ativo = ? WHERE id = ?", (*valores, id_))
                mudancas = []
                if dados["vinculo"] != atual["vinculo"]:
                    mudancas.append(f"Vínculo: {VINCULOS[atual['vinculo']]} → "
                                    f"{VINCULOS[dados['vinculo']]}")
                if dados["ativo"] != atual["ativo"]:
                    mudancas.append("Reativado" if dados["ativo"] else "Desativado")
                if dados["nome"] != atual["nome"]:
                    mudancas.append(f"Nome: {atual['nome']} → {dados['nome']}")
                registrar("Alteração de servidor", referencia=dados["nome"],
                          detalhes="; ".join(mudancas) or None)
            conn.commit()
            flash("Servidor salvo.", "sucesso")
            return redirect(url_for("admin.servidores"))

    return render_template("admin/servidor_form.html", dados=dados, novo=atual is None,
                           vinculos=VINCULOS)


def _licitacoes_afetadas(servidor_id, inicio, fim):
    """Licitações abertas com sessão futura no período em que o servidor estará afastado."""
    abertas = [c for c in P.chaves(*FASES_ABERTAS) if P.fase(c) != "suspensa"]
    marcadores = ",".join("?" * len(abertas))
    return get_db().execute(
        "SELECT id, numero_edital, numero_processo, modalidade, status, data_sessao"
        "  FROM licitacoes"
        " WHERE ? IN (agente_id, membro1_id, membro2_id, membro3_id)"
        f"  AND status IN ({marcadores})"
        "   AND substr(data_sessao, 1, 10) BETWEEN max(?, date('now', 'localtime')) AND ?"
        " ORDER BY data_sessao",
        (servidor_id, *abertas, inicio, fim),
    ).fetchall()


@bp.route("/servidores/<int:id_>/afastamentos", methods=["GET", "POST"])
@permissao("afastamentos")
def afastamentos(id_):
    """Férias, licenças e afastamentos: impedem a escala do servidor no período."""
    conn = get_db()
    servidor = conn.execute("SELECT * FROM servidores WHERE id = ?", (id_,)).fetchone()
    if servidor is None:
        abort(404)
    dados = {"tipo": "Férias"}

    if request.method == "POST":
        dados = {c: request.form.get(c, "").strip()
                 for c in ("tipo", "inicio", "fim", "observacao")}
        erros = []
        if dados["tipo"] not in TIPOS_AFASTAMENTO:
            erros.append("Selecione o tipo de afastamento.")
        try:
            inicio = date.fromisoformat(dados["inicio"])
            fim = date.fromisoformat(dados["fim"])
            if fim < inicio:
                erros.append("O fim do afastamento não pode ser anterior ao início.")
        except ValueError:
            erros.append("Informe as datas de início e fim.")

        if erros:
            for e in erros:
                flash(e, "erro")
        else:
            conn.execute(
                "INSERT INTO afastamentos (servidor_id, tipo, inicio, fim, observacao)"
                " VALUES (?, ?, ?, ?, ?)",
                (id_, dados["tipo"], dados["inicio"], dados["fim"], dados["observacao"] or None),
            )
            periodo = f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"
            registrar("Cadastro de afastamento", referencia=servidor["nome"],
                      detalhes=f"{dados['tipo']}: {periodo}")
            conn.commit()
            flash(f"{dados['tipo']} de {servidor['nome']} registrado(a): {periodo}.", "sucesso")
            afetadas = _licitacoes_afetadas(id_, dados["inicio"], dados["fim"])
            if afetadas:
                lista = ", ".join(P.edital(l) for l in afetadas)
                flash(f"Atenção: {servidor['nome']} está escalado(a) em licitação com sessão "
                      f"nesse período: {lista}. Troque o membro (ou, se já estiver em "
                      "andamento, decida se o mantém) na edição da licitação.", "erro")
            return redirect(url_for("admin.afastamentos", id_=id_))

    lista = conn.execute(
        "SELECT * FROM afastamentos WHERE servidor_id = ? ORDER BY inicio DESC", (id_,)
    ).fetchall()
    return render_template("admin/afastamentos.html", servidor=servidor, afastamentos=lista,
                           dados=dados, tipos=TIPOS_AFASTAMENTO, hoje=date.today().isoformat())


@bp.route("/afastamentos/<int:id_>/excluir", methods=["POST"])
@permissao("afastamentos")
def excluir_afastamento(id_):
    conn = get_db()
    afastamento = conn.execute(
        "SELECT a.*, s.nome FROM afastamentos a JOIN servidores s ON s.id = a.servidor_id"
        " WHERE a.id = ?", (id_,)
    ).fetchone()
    if afastamento is None:
        abort(404)
    conn.execute("DELETE FROM afastamentos WHERE id = ?", (id_,))
    registrar("Exclusão de afastamento", referencia=afastamento["nome"],
              detalhes=f"{afastamento['tipo']}: {afastamento['inicio']} a {afastamento['fim']}")
    conn.commit()
    flash("Afastamento excluído.", "sucesso")
    return redirect(url_for("admin.afastamentos", id_=afastamento["servidor_id"]))


@bp.route("/auditoria")
@permissao("auditoria")
def auditoria():
    pagina = max(request.args.get("pagina", 1, type=int), 1)
    registros = get_db().execute(
        "SELECT h.*, u.nome AS usuario_nome, l.numero_processo"
        "  FROM historico h"
        "  LEFT JOIN usuarios u ON u.id = h.usuario_id"
        "  LEFT JOIN licitacoes l ON l.id = h.licitacao_id"
        " ORDER BY h.id DESC LIMIT ? OFFSET ?",
        (ITENS_POR_PAGINA + 1, (pagina - 1) * ITENS_POR_PAGINA),
    ).fetchall()
    tem_mais = len(registros) > ITENS_POR_PAGINA
    return render_template("admin/auditoria.html", registros=registros[:ITENS_POR_PAGINA],
                           pagina=pagina, tem_mais=tem_mais)
