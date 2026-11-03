"""Configurações: permissões dos perfis (só administrador) e parâmetros do sistema
(nome do órgão, modalidades, siglas, cores e situações)."""
import functools
import re
import unicodedata
from datetime import date

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template, request,
                   url_for)
from werkzeug.security import check_password_hash

from . import brasao
from . import feriados as F
from . import parametros as P
from .auth import login_obrigatorio, permissao, problema_na_senha_recuperacao
from .db import get_db, registrar
from .perfis import FASES, FASES_DA_ACAO, FASES_ABERTAS, PERFIL_TOTAL, PERFIS, PERMISSOES, PRAZOS

bp = Blueprint("config", __name__, url_prefix="/admin")

FORMATO_COR = re.compile(r"^#[0-9a-fA-F]{6}$")
FORMATO_SIGLA = re.compile(r"^[A-Za-zÀ-ú]{1,6}$")
# Situações criadas pelo usuário não podem ocupar as fases das ações de suspender/remarcar.
FASES_LIVRES = [f for f in FASES if f not in FASES_DA_ACAO]


def somente_administrador(view):
    @functools.wraps(view)
    @login_obrigatorio
    def wrapper(*args, **kwargs):
        if g.usuario["perfil"] != PERFIL_TOTAL:
            abort(403)
        return view(*args, **kwargs)

    return wrapper


def _erros(lista):
    for e in lista:
        flash(e, "erro")
    return bool(lista)


@bp.route("/perfis", methods=["GET", "POST"])
@somente_administrador
def perfis():
    """Matriz de permissões por perfil. O administrador mantém sempre todas."""
    editaveis = [p for p in PERFIS if p != PERFIL_TOTAL]
    if request.method == "POST":
        conn = get_db()
        antes = P.permissoes()
        mudancas = []
        for perfil in editaveis:
            novas = {p for p in request.form.getlist(f"perm_{perfil}") if p in PERMISSOES}
            atuais = antes.get(perfil, set())
            if novas != atuais:
                conn.execute("DELETE FROM permissoes WHERE perfil = ?", (perfil,))
                conn.executemany("INSERT INTO permissoes VALUES (?, ?)",
                                 [(perfil, p) for p in sorted(novas)])
                ganhou = ", ".join(PERMISSOES[p] for p in PERMISSOES if p in novas - atuais)
                perdeu = ", ".join(PERMISSOES[p] for p in PERMISSOES if p in atuais - novas)
                partes = [f"+ {ganhou}" if ganhou else "", f"− {perdeu}" if perdeu else ""]
                mudancas.append(f"{PERFIS[perfil]}: " + "; ".join(x for x in partes if x))
        if mudancas:
            registrar("Alteração de permissões", referencia="Perfis",
                      detalhes=" | ".join(mudancas))
            conn.commit()
            P.invalidar()
            flash("Permissões atualizadas.", "sucesso")
        else:
            flash("Nenhuma alteração foi feita.", "info")
        return redirect(url_for("config.perfis"))

    return render_template("config/perfis.html", editaveis=editaveis,
                           permissoes=PERMISSOES, atuais=P.permissoes())


@bp.route("/parametros")
@permissao("parametros")
def parametros():
    conn = get_db()
    uso_modalidade = dict(conn.execute(
        "SELECT modalidade, COUNT(*) FROM licitacoes GROUP BY modalidade").fetchall())
    uso_situacao = dict(conn.execute(
        "SELECT status, COUNT(*) FROM licitacoes GROUP BY status").fetchall())
    return render_template(
        "config/parametros.html", modalidades=P.modalidades(), situacoes=P.situacoes(),
        uso_modalidade=uso_modalidade, uso_situacao=uso_situacao, fases=FASES, prazos=PRAZOS,
        nuvem=current_app.config.get("NUVEM"),
    )


@bp.route("/parametros/geral", methods=["POST"])
@permissao("parametros")
def salvar_geral():
    nome = request.form.get("nome_orgao", "").strip()
    if _erros([] if nome else ["Informe o nome do órgão."]):
        return redirect(url_for("config.parametros"))
    antigo = P.nome_orgao()
    if nome != antigo:
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO configuracoes VALUES ('nome_orgao', ?)", (nome,))
        registrar("Alteração de parâmetro", referencia="Nome do órgão",
                  detalhes=f"{antigo} → {nome}")
        conn.commit()
        P.invalidar()
    flash("Nome do órgão salvo.", "sucesso")
    return redirect(url_for("config.parametros"))


@bp.route("/parametros/recuperacao", methods=["POST"])
@somente_administrador
def senha_recuperacao():
    """Define ou troca a senha de recuperação das cópias na nuvem."""
    nuvem = current_app.config.get("NUVEM")
    if nuvem is None:
        abort(404)
    senha = request.form.get("recuperacao", "")
    erros = []
    if not check_password_hash(g.usuario["senha_hash"], request.form.get("senha_atual", "")):
        erros.append("A sua senha não confere.")
    else:
        motivo = problema_na_senha_recuperacao(
            senha, request.form.get("recuperacao_confirmacao", ""))
        if motivo:
            erros.append(motivo)
        elif check_password_hash(g.usuario["senha_hash"], senha):
            erros.append("A senha de recuperação deve ser diferente da senha do administrador.")
    if not _erros(erros):
        nuvem.definir_senha_recuperacao(senha)
        registrar("Alteração de parâmetro", referencia="Senha de recuperação das cópias")
        get_db().commit()
        flash("Senha de recuperação salva. Anote-a num lugar seguro, fora do computador.",
              "sucesso")
    return redirect(url_for("config.parametros"))


@bp.route("/parametros/brasao", methods=["POST"])
@permissao("parametros")
def salvar_brasao():
    arquivo = request.files.get("brasao")
    if not arquivo or not arquivo.filename:
        flash("Escolha a imagem do brasão.", "erro")
        return redirect(url_for("config.parametros"))
    try:
        brasao.salvar(arquivo.stream)
    except ValueError as erro:
        flash(str(erro), "erro")
        return redirect(url_for("config.parametros"))
    registrar("Alteração de parâmetro", referencia="Brasão do município",
              detalhes=f"Imagem enviada: {arquivo.filename}")
    get_db().commit()
    flash("Brasão atualizado.", "sucesso")
    return redirect(url_for("config.parametros"))


@bp.route("/parametros/brasao/remover", methods=["POST"])
@permissao("parametros")
def remover_brasao():
    brasao.remover()
    registrar("Alteração de parâmetro", referencia="Brasão do município", detalhes="Removido")
    get_db().commit()
    flash("Brasão removido.", "sucesso")
    return redirect(url_for("config.parametros"))


# --- Modalidades -------------------------------------------------------------------------

@bp.route("/modalidades/nova", methods=["GET", "POST"], defaults={"id_": None})
@bp.route("/modalidades/<int:id_>/editar", methods=["GET", "POST"])
@permissao("parametros")
def modalidade(id_):
    conn = get_db()
    atual = None
    if id_ is not None:
        atual = conn.execute("SELECT * FROM modalidades WHERE id = ?", (id_,)).fetchone()
        if atual is None:
            abort(404)
    proxima = (conn.execute("SELECT MAX(ordem) FROM modalidades").fetchone()[0] or 0) + 1
    dados = dict(atual) if atual else {
        "cor": "#1d4f91", "ordem": proxima, "ativa": 1, "credenciamento": 0,
        "exige_equipe": 1, "rotulo_condutor": "Agente de contratação",
        "prazo_padrao": "nao_se_aplica", "prazos_permitidos": "nao_se_aplica",
    }
    em_uso = atual and conn.execute(
        "SELECT COUNT(*) FROM licitacoes WHERE modalidade = ?", (atual["nome"],)).fetchone()[0]

    if request.method == "POST":
        f = request.form
        dados = {
            "nome": f.get("nome", "").strip(), "sigla": f.get("sigla", "").strip().upper(),
            "cor": f.get("cor", "").strip(), "ordem": f.get("ordem", "0").strip(),
            "ativa": 1 if f.get("ativa") else 0,
            "credenciamento": 1 if f.get("credenciamento") else 0,
            "exige_equipe": 1 if f.get("exige_equipe") else 0,
            "rotulo_condutor": f.get("rotulo_condutor", "").strip() or "Agente de contratação",
            "prazo_padrao": f.get("prazo_padrao", ""),
            "prazos_permitidos": ",".join(p for p in PRAZOS
                                          if p in f.getlist("prazos_permitidos")),
        }
        erros = []
        if not dados["nome"]:
            erros.append("Informe o nome da modalidade.")
        elif conn.execute("SELECT 1 FROM modalidades WHERE nome = ? AND id != ?",
                          (dados["nome"], id_ or 0)).fetchone():
            erros.append("Já existe uma modalidade com esse nome.")
        if not FORMATO_SIGLA.match(dados["sigla"]):
            erros.append("A sigla deve ter de 1 a 6 letras (ex.: PE).")
        if not FORMATO_COR.match(dados["cor"]):
            erros.append("Escolha uma cor válida.")
        if not dados["ordem"].lstrip("-").isdigit():
            erros.append("A ordem deve ser um número.")
        if not dados["prazos_permitidos"]:
            erros.append("Marque ao menos um critério de julgamento cabível.")
        elif dados["prazo_padrao"] not in dados["prazos_permitidos"].split(","):
            erros.append("O critério de julgamento padrão precisa estar entre os cabíveis.")
        if em_uso and dados["credenciamento"] != atual["credenciamento"]:
            erros.append("Não é possível mudar o tipo (credenciamento ou com sessão) de uma "
                         "modalidade já usada em licitações.")

        if not _erros(erros):
            valores = (dados["nome"], dados["sigla"], dados["cor"], int(dados["ordem"]),
                       dados["ativa"], dados["credenciamento"], dados["exige_equipe"],
                       dados["rotulo_condutor"], dados["prazo_padrao"],
                       dados["prazos_permitidos"])
            colunas = ("nome = ?, sigla = ?, cor = ?, ordem = ?, ativa = ?, credenciamento = ?,"
                       " exige_equipe = ?, rotulo_condutor = ?, prazo_padrao = ?,"
                       " prazos_permitidos = ?")
            if atual is None:
                conn.execute("INSERT INTO modalidades (nome, sigla, cor, ordem, ativa,"
                             " credenciamento, exige_equipe, rotulo_condutor, prazo_padrao,"
                             " prazos_permitidos) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", valores)
                registrar("Cadastro de modalidade", referencia=dados["nome"],
                          detalhes=f"Sigla {dados['sigla']}")
            else:
                conn.execute(f"UPDATE modalidades SET {colunas} WHERE id = ?", (*valores, id_))
                if dados["nome"] != atual["nome"]:
                    # As licitações guardam o nome da modalidade.
                    conn.execute("UPDATE licitacoes SET modalidade = ? WHERE modalidade = ?",
                                 (dados["nome"], atual["nome"]))
                mudancas = [f"{rotulo}: {atual[c]} → {dados[c]}" for c, rotulo in (
                    ("nome", "Nome"), ("sigla", "Sigla"), ("cor", "Cor"), ("ativa", "Ativa"),
                    ("exige_equipe", "Exige equipe"), ("rotulo_condutor", "Condutor"),
                    ("prazo_padrao", "Critério padrão"),
                    ("prazos_permitidos", "Critérios cabíveis"))
                    if str(atual[c]) != str(dados[c])]
                registrar("Alteração de modalidade", referencia=dados["nome"],
                          detalhes="; ".join(mudancas) or None)
            conn.commit()
            P.invalidar()
            flash("Modalidade salva.", "sucesso")
            return redirect(url_for("config.parametros"))

    return render_template("config/modalidade.html", dados=dados, novo=atual is None,
                           em_uso=em_uso, prazos=PRAZOS)


@bp.route("/modalidades/<int:id_>/excluir", methods=["POST"])
@permissao("parametros")
def excluir_modalidade(id_):
    conn = get_db()
    atual = conn.execute("SELECT * FROM modalidades WHERE id = ?", (id_,)).fetchone()
    if atual is None:
        abort(404)
    if conn.execute("SELECT 1 FROM licitacoes WHERE modalidade = ?", (atual["nome"],)).fetchone():
        flash("Modalidade em uso: desative-a em vez de excluir.", "erro")
    else:
        conn.execute("DELETE FROM modalidades WHERE id = ?", (id_,))
        registrar("Exclusão de modalidade", referencia=atual["nome"])
        conn.commit()
        P.invalidar()
        flash("Modalidade excluída.", "sucesso")
    return redirect(url_for("config.parametros"))


# --- Situações ---------------------------------------------------------------------------

def _chave_para(nome):
    base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "_", base.lower()).strip("_") or "situacao"
    chave, n = base, 2
    while get_db().execute("SELECT 1 FROM situacoes WHERE chave = ?", (chave,)).fetchone():
        chave, n = f"{base}_{n}", n + 1
    return chave


@bp.route("/situacoes/nova", methods=["GET", "POST"], defaults={"chave": None})
@bp.route("/situacoes/<chave>/editar", methods=["GET", "POST"])
@permissao("parametros")
def situacao(chave):
    conn = get_db()
    atual = None
    if chave is not None:
        atual = conn.execute("SELECT * FROM situacoes WHERE chave = ?", (chave,)).fetchone()
        if atual is None:
            abort(404)
    proxima = (conn.execute("SELECT MAX(ordem) FROM situacoes").fetchone()[0] or 0) + 1
    dados = dict(atual) if atual else {"cor": "#475467", "fase": "encerrada", "ordem": proxima,
                                       "ativa": 1, "sistema": 0, "whatsapp": 0}

    if request.method == "POST":
        f = request.form
        sistema = bool(atual and atual["sistema"])
        dados = {
            "nome": f.get("nome", "").strip(), "cor": f.get("cor", "").strip(),
            "ordem": f.get("ordem", "0").strip(),
            # As do sistema não mudam de fase nem podem ser desativadas.
            "fase": atual["fase"] if sistema else f.get("fase", ""),
            "ativa": 1 if sistema or f.get("ativa") else 0,
            "sistema": int(sistema),
            "whatsapp": 1 if f.get("whatsapp") else 0,
        }
        erros = []
        if not dados["nome"]:
            erros.append("Informe o nome da situação.")
        elif conn.execute("SELECT 1 FROM situacoes WHERE nome = ? AND chave != ?",
                          (dados["nome"], chave or "")).fetchone():
            erros.append("Já existe uma situação com esse nome.")
        if not FORMATO_COR.match(dados["cor"]):
            erros.append("Escolha uma cor válida.")
        if not sistema and dados["fase"] not in FASES_LIVRES:
            erros.append("Escolha a fase da situação.")
        if not dados["ordem"].lstrip("-").isdigit():
            erros.append("A ordem deve ser um número.")

        if not _erros(erros):
            if atual is None:
                conn.execute(
                    "INSERT INTO situacoes (chave, nome, cor, fase, ordem, ativa, whatsapp)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (_chave_para(dados["nome"]), dados["nome"], dados["cor"], dados["fase"],
                     int(dados["ordem"]), dados["ativa"], dados["whatsapp"]),
                )
                registrar("Cadastro de situação", referencia=dados["nome"],
                          detalhes=f"Fase: {FASES[dados['fase']]}")
            else:
                conn.execute(
                    "UPDATE situacoes SET nome = ?, cor = ?, fase = ?, ordem = ?, ativa = ?,"
                    " whatsapp = ? WHERE chave = ?",
                    (dados["nome"], dados["cor"], dados["fase"], int(dados["ordem"]),
                     dados["ativa"], dados["whatsapp"], chave),
                )
                mudancas = [f"{rotulo}: {atual[c]} → {dados[c]}" for c, rotulo in (
                    ("nome", "Nome"), ("cor", "Cor"), ("fase", "Fase"), ("ativa", "Ativa"),
                    ("whatsapp", "No WhatsApp"))
                    if str(atual[c]) != str(dados[c])]
                registrar("Alteração de situação", referencia=dados["nome"],
                          detalhes="; ".join(mudancas) or None)
            conn.commit()
            P.invalidar()
            flash("Situação salva.", "sucesso")
            return redirect(url_for("config.parametros"))

    return render_template("config/situacao.html", dados=dados, novo=atual is None,
                           fases={f: FASES[f] for f in FASES_LIVRES}, todas_fases=FASES)


@bp.route("/situacoes/whatsapp", methods=["POST"])
@permissao("parametros")
def filtro_whatsapp():
    """Quais situações entram na imagem/texto do WhatsApp."""
    marcadas = set(request.form.getlist("whatsapp"))
    conn = get_db()
    antes = {s["chave"] for s in P.situacoes() if s["whatsapp"]}
    for s in P.situacoes():
        conn.execute("UPDATE situacoes SET whatsapp = ? WHERE chave = ?",
                     (int(s["chave"] in marcadas), s["chave"]))
    if antes != marcadas:
        nomes = ", ".join(s["nome"] for s in P.situacoes() if s["chave"] in marcadas)
        registrar("Alteração de parâmetro", referencia="Situações no WhatsApp",
                  detalhes=nomes or "Nenhuma")
    conn.commit()
    P.invalidar()
    flash("Filtro do WhatsApp salvo.", "sucesso")
    return redirect(url_for("config.parametros") + "#whatsapp")


@bp.route("/situacoes/<chave>/excluir", methods=["POST"])
@permissao("parametros")
def excluir_situacao(chave):
    conn = get_db()
    atual = conn.execute("SELECT * FROM situacoes WHERE chave = ?", (chave,)).fetchone()
    if atual is None:
        abort(404)
    if atual["sistema"]:
        flash("Situação usada pelo sistema: pode ser renomeada, mas não excluída.", "erro")
    elif conn.execute("SELECT 1 FROM licitacoes WHERE status = ?", (chave,)).fetchone():
        flash("Situação em uso: desative-a em vez de excluir.", "erro")
    else:
        conn.execute("DELETE FROM situacoes WHERE chave = ?", (chave,))
        registrar("Exclusão de situação", referencia=atual["nome"])
        conn.commit()
        P.invalidar()
        flash("Situação excluída.", "sucesso")
    return redirect(url_for("config.parametros"))


# --- Feriados e pontos facultativos ------------------------------------------------------

def _sessoes_no_dia(dia):
    """Licitações abertas com sessão marcada no dia (para avisar após cadastrar feriado)."""
    chaves = P.chaves(*FASES_ABERTAS)
    linhas = get_db().execute(
        "SELECT * FROM licitacoes WHERE substr(data_sessao, 1, 10) = ?"
        f" AND status IN ({','.join('?' * len(chaves))})", (dia.isoformat(), *chaves)
    ).fetchall()
    return [P.edital(l) for l in linhas]


def _avisar_sessoes(ano, feriado_id):
    """Depois de criar, alterar ou transferir: aponta sessões que caíram no novo dia."""
    for dia, lista in F.ocorrencias(ano).items():
        if any(o["id"] == feriado_id for o in lista):
            afetadas = _sessoes_no_dia(dia)
            if afetadas:
                flash(f"Atenção: há sessão marcada em {dia:%d/%m/%Y}: {', '.join(afetadas)}. "
                      "Remarque-a para um dia útil.", "erro")


@bp.route("/feriados")
@permissao("feriados")
def feriados():
    ano = request.args.get("ano", date.today().year, type=int)
    conn = get_db()
    lista = []
    for f in conn.execute("SELECT * FROM feriados ORDER BY abrangencia, nome"):
        transf = conn.execute("SELECT * FROM feriado_transferencias WHERE feriado_id = ?"
                              " AND ano = ?", (f["id"], ano)).fetchone()
        original = F.data_original(f, ano)
        efetiva = date.fromisoformat(transf["nova_data"]) if transf else original
        lista.append({"f": f, "original": original, "efetiva": efetiva, "transf": transf})
    lista.sort(key=lambda x: (x["efetiva"] is None, x["efetiva"] or date.max))
    return render_template("config/feriados.html", lista=lista, ano=ano, tipos=F.TIPOS,
                           abrangencias=F.ABRANGENCIAS, dias_semana=F.NOMES_DIA)


@bp.route("/feriados/novo", methods=["GET", "POST"], defaults={"id_": None})
@bp.route("/feriados/<int:id_>/editar", methods=["GET", "POST"])
@permissao("feriados")
def feriado(id_):
    conn = get_db()
    atual = None
    if id_ is not None:
        atual = conn.execute("SELECT * FROM feriados WHERE id = ?", (id_,)).fetchone()
        if atual is None:
            abort(404)
    dados = dict(atual) if atual else {"tipo": "ponto_facultativo", "abrangencia": "municipal",
                                       "regra": "data", "ativo": 1}

    if request.method == "POST":
        f = request.form
        dados = {c: f.get(c, "").strip() for c in ("nome", "tipo", "abrangencia", "regra",
                                                    "data", "observacao")}
        dados["ativo"] = 1 if f.get("ativo") or atual is None else 0
        dados["dia"] = dados["mes"] = dados["deslocamento"] = None
        erros = []
        if not dados["nome"]:
            erros.append("Informe o nome.")
        if dados["tipo"] not in F.TIPOS or dados["abrangencia"] not in F.ABRANGENCIAS:
            erros.append("Escolha o tipo e a abrangência.")
        try:
            if dados["regra"] == "fixa":
                dia_mes = date.fromisoformat(f"2024-{f.get('mes', '').zfill(2)}-"
                                             f"{f.get('dia', '').zfill(2)}")
                dados["dia"], dados["mes"], dados["data"] = dia_mes.day, dia_mes.month, None
            elif dados["regra"] == "pascoa":
                dados["deslocamento"], dados["data"] = int(f.get("deslocamento", "")), None
            elif dados["regra"] == "data":
                dados["data"] = date.fromisoformat(dados["data"]).isoformat()
            else:
                erros.append("Escolha quando ocorre.")
        except ValueError:
            erros.append("Data inválida.")

        if not _erros(erros):
            valores = tuple(dados[c] for c in ("nome", "tipo", "abrangencia", "regra", "dia",
                                               "mes", "deslocamento", "data", "ativo"))
            valores += (dados["observacao"] or None,)
            if atual is None:
                cur = conn.execute(
                    "INSERT INTO feriados (nome, tipo, abrangencia, regra, dia, mes,"
                    " deslocamento, data, ativo, observacao) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    valores)
                id_ = cur.lastrowid
                registrar(f"Cadastro de {F.TIPOS[dados['tipo']].lower()}",
                          referencia=dados["nome"])
            else:
                conn.execute(
                    "UPDATE feriados SET nome = ?, tipo = ?, abrangencia = ?, regra = ?, dia = ?,"
                    " mes = ?, deslocamento = ?, data = ?, ativo = ?, observacao = ? WHERE id = ?",
                    (*valores, id_))
                registrar("Alteração de feriado", referencia=dados["nome"])
            conn.commit()
            F.invalidar()
            flash("Salvo.", "sucesso")
            ano = int(dados["data"][:4]) if dados["regra"] == "data" else date.today().year
            for a in (ano, ano + 1):
                _avisar_sessoes(a, id_)
            return redirect(url_for("config.feriados", ano=ano))

    return render_template("config/feriado.html", dados=dados, novo=atual is None,
                           tipos=F.TIPOS, abrangencias=F.ABRANGENCIAS, regras=F.REGRAS)


@bp.route("/feriados/<int:id_>/excluir", methods=["POST"])
@permissao("feriados")
def excluir_feriado(id_):
    conn = get_db()
    atual = conn.execute("SELECT * FROM feriados WHERE id = ?", (id_,)).fetchone()
    if atual is None:
        abort(404)
    conn.execute("DELETE FROM feriados WHERE id = ?", (id_,))
    registrar("Exclusão de feriado", referencia=atual["nome"])
    conn.commit()
    F.invalidar()
    flash(f"{atual['nome']} excluído.", "sucesso")
    return redirect(url_for("config.feriados", ano=request.form.get("ano") or None))


@bp.route("/feriados/<int:id_>/transferir", methods=["GET", "POST"])
@permissao("feriados")
def transferir_feriado(id_):
    """Transfere a data do feriado num ano (ex.: decreto municipal que antecipa o feriado)."""
    conn = get_db()
    atual = conn.execute("SELECT * FROM feriados WHERE id = ?", (id_,)).fetchone()
    if atual is None:
        abort(404)
    ano = request.values.get("ano", date.today().year, type=int)
    original = F.data_original(atual, ano)
    transf = conn.execute("SELECT * FROM feriado_transferencias WHERE feriado_id = ? AND ano = ?",
                          (id_, ano)).fetchone()
    dados = dict(transf) if transf else {"ano": ano}

    if request.method == "POST":
        if request.form.get("remover"):
            conn.execute("DELETE FROM feriado_transferencias WHERE feriado_id = ? AND ano = ?",
                         (id_, ano))
            registrar("Transferência de feriado desfeita", referencia=atual["nome"],
                      detalhes=f"Ano {ano}")
            conn.commit()
            F.invalidar()
            flash("Transferência desfeita: vale a data original.", "sucesso")
            return redirect(url_for("config.feriados", ano=ano))
        dados = {"ano": ano, "nova_data": request.form.get("nova_data", ""),
                 "ato": request.form.get("ato", "").strip()}
        erros = []
        if original is None:
            erros.append(f"Este item não ocorre em {ano}.")
        try:
            nova = date.fromisoformat(dados["nova_data"])
            if original and nova == original:
                erros.append("A nova data é igual à original.")
        except ValueError:
            erros.append("Informe a nova data.")
        if not _erros(erros):
            conn.execute("INSERT OR REPLACE INTO feriado_transferencias (feriado_id, ano,"
                         " nova_data, ato) VALUES (?, ?, ?, ?)",
                         (id_, ano, nova.isoformat(), dados["ato"] or None))
            registrar("Transferência de feriado", referencia=atual["nome"],
                      detalhes=f"{original:%d/%m/%Y} → {nova:%d/%m/%Y}"
                               + (f" ({dados['ato']})" if dados["ato"] else ""))
            conn.commit()
            F.invalidar()
            flash(f"{atual['nome']} transferido para {nova:%d/%m/%Y}.", "sucesso")
            _avisar_sessoes(ano, id_)
            return redirect(url_for("config.feriados", ano=ano))

    return render_template("config/transferir.html", feriado=atual, ano=ano, original=original,
                           dados=dados, existente=transf)
