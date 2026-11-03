import io
import json
import os
import re
from datetime import date, timedelta

import pytest
from werkzeug.security import generate_password_hash

from licitacoes import create_app, cripto
from licitacoes.db import get_db
from licitacoes.feriados import pascoa
from licitacoes.perfis import FERIADOS_PADRAO

SENHA = "senha-segura-1"


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "PASTA_DADOS": str(tmp_path),
                      "DATABASE": str(tmp_path / "teste.sqlite3"), "SECRET_KEY": "teste"})
    with app.app_context():
        conn = get_db()
        for perfil in ("administrador", "gestor", "pregoeiro", "consulta"):
            conn.execute(
                "INSERT INTO usuarios (nome, login, login_cifrado, senha_hash, perfil,"
                " trocar_senha) VALUES (?, ?, ?, ?, ?, 0)",
                (perfil.title(), cripto.indice_login(perfil), cripto.cifrar_login(perfil),
                 generate_password_hash(SENHA), perfil),
            )
        for nome, vinculo in (("Ana Efetiva", "efetivo"), ("Beto Efetivo", "efetivo"),
                              ("Caio Comissionado", "comissionado"),
                              ("Dora Temporária", "temporario"), ("Eva Efetiva", "efetivo")):
            conn.execute("INSERT INTO servidores (nome, vinculo) VALUES (?, ?)", (nome, vinculo))
        conn.commit()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client, url):
    html = client.get(url).get_data(as_text=True)
    return re.search(r'name="_csrf" value="([^"]+)"', html).group(1)


def entrar(client, login, senha=SENHA):
    token = csrf(client, "/login")
    return client.post("/login", data={"login": login, "senha": senha, "_csrf": token})


def post(client, url, dados, pagina=None):
    dados = dict(dados, _csrf=csrf(client, pagina or "/"))
    return client.post(url, data=dados)


def dia_util(dia):
    """Primeiro dia sem fim de semana nem feriado/ponto facultativo padrão a partir de ``dia``."""
    def nao_util(d):
        if d.weekday() >= 5:
            return True
        for _, _, _, regra, dia_, mes, desloc, _ in FERIADOS_PADRAO:
            if regra == "fixa" and (d.month, d.day) == (mes, dia_):
                return True
            if regra == "pascoa" and d == pascoa(d.year) + timedelta(days=desloc):
                return True
        return False
    while nao_util(dia):
        dia += timedelta(days=1)
    return dia


# Sessão sempre no futuro e em dia útil, para os testes não dependerem da data em que rodam.
SESSAO = dia_util(date.today() + timedelta(days=15))
SESSAO_ISO = f"{SESSAO.isoformat()}T09:30"
SESSAO_BR = f"{SESSAO:%d/%m/%Y} 09:30"

LICITACAO = {
    "numero_processo": "2026.000123",
    "numero_edital": "010/2026",
    "modalidade": "Pregão Eletrônico",
    "objeto": "Aquisição de material de expediente",
    "data_sessao": SESSAO_ISO,
    "local": "Compras.gov.br",
    "valor_estimado": "150.000,50",
    "status": "publicado",
    "data_publicacao": (date.today() - timedelta(days=10)).isoformat(),
    # Servidores 1, 2 e 5 são efetivos; 3 e 4 não.
    "agente_id": "1",
    "membro1_id": "2",
    "membro2_id": "3",
}


def criar_licitacao(client):
    resp = post(client, "/licitacoes/nova", LICITACAO, "/licitacoes/nova")
    assert resp.status_code == 302
    return int(resp.headers["Location"].rsplit("/", 1)[1])


def test_exige_login(client):
    resp = client.get("/")
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]


def test_login_invalido(client):
    resp = entrar(client, "gestor", "errada")
    assert "Usuário ou senha inválidos" in resp.get_data(as_text=True)


def test_post_sem_csrf_e_rejeitado(client):
    resp = client.post("/login", data={"login": "gestor", "senha": SENHA})
    assert resp.status_code == 400


def test_pregoeiro_cria_e_edita_mas_nao_exclui(client):
    entrar(client, "pregoeiro")
    id_ = criar_licitacao(client)

    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "R$ 150.000,50" in pagina
    assert "Excluir" not in pagina

    dados = dict(LICITACAO, status="homologada")
    resp = post(client, f"/licitacoes/{id_}/editar", dados, f"/licitacoes/{id_}/editar")
    assert resp.status_code == 302
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "Situação: Edital publicado → Homologada" in pagina

    resp = post(client, f"/licitacoes/{id_}/excluir", {})
    assert resp.status_code == 403


def test_consulta_so_visualiza(client):
    entrar(client, "gestor")
    id_ = criar_licitacao(client)
    client.post("/logout", data={"_csrf": csrf(client, "/")})

    entrar(client, "consulta")
    assert client.get("/calendario?ano=2026&mes=11").status_code == 200
    assert "PE 010/2026" in client.get("/calendario?ano=2026&mes=11").get_data(as_text=True)
    assert client.get(f"/licitacoes/{id_}").status_code == 200
    assert client.get("/licitacoes/nova").status_code == 403
    assert client.get(f"/licitacoes/{id_}/editar").status_code == 403
    assert client.get("/admin/usuarios").status_code == 403
    assert client.get("/admin/auditoria").status_code == 403


def test_gestor_exclui_e_ve_auditoria(client):
    entrar(client, "gestor")
    id_ = criar_licitacao(client)
    resp = post(client, f"/licitacoes/{id_}/excluir", {})
    assert resp.status_code == 302
    assert client.get(f"/licitacoes/{id_}").status_code == 404

    auditoria = client.get("/admin/auditoria").get_data(as_text=True)
    assert "Exclusão de licitação" in auditoria
    assert client.get("/admin/usuarios").status_code == 403


def test_validacao_de_campos(client):
    entrar(client, "pregoeiro")
    dados = dict(LICITACAO, modalidade="Inventada", valor_estimado="abc", objeto="")
    resp = post(client, "/licitacoes/nova", dados, "/licitacoes/nova")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "modalidade válida" in html and "Valor estimado inválido" in html


def test_filtros_e_exportacao_ics(client):
    entrar(client, "pregoeiro")
    criar_licitacao(client)
    post(client, "/licitacoes/nova",
         dict(LICITACAO, numero_processo="2026.999", modalidade="Leilão",
              numero_edital="001/2026"),
         "/licitacoes/nova")

    html = client.get("/licitacoes?modalidade=Leilão").get_data(as_text=True)
    assert "2026.999" in html and "2026.000123" not in html

    ics = client.get("/licitacoes.ics").get_data(as_text=True)
    assert ics.count("BEGIN:VEVENT") == 2
    assert f"DTSTART:{SESSAO:%Y%m%d}T093000" in ics


def test_admin_gerencia_usuarios(client, app):
    entrar(client, "administrador")
    resp = post(client, "/admin/usuarios/novo",
                {"nome": "Maria Silva", "login": "maria.silva", "perfil": "pregoeiro"},
                "/admin/usuarios/novo")
    html = client.get(resp.headers["Location"]).get_data(as_text=True)
    senha = re.search(r"Senha temporária de “maria.silva”: (\S+)", html).group(1)

    # Admin não pode rebaixar a si mesmo.
    with app.app_context():
        admin_id = get_db().execute("SELECT id FROM usuarios WHERE perfil='administrador'").fetchone()[0]
    resp = post(client, f"/admin/usuarios/{admin_id}/editar",
                {"nome": "Adm", "perfil": "consulta", "ativo": "1"}, "/admin/usuarios")
    assert "próprio acesso de administrador" in resp.get_data(as_text=True)

    # Novo usuário é obrigado a trocar a senha temporária.
    novo = app.test_client()
    entrar(novo, "maria.silva", senha)
    resp = novo.get("/licitacoes")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/senha")
    post(novo, "/senha", {"senha_atual": senha, "nova_senha": "nova-senha-123",
                          "confirmacao": "nova-senha-123"}, "/senha")
    assert novo.get("/licitacoes").status_code == 200


def test_usuario_desativado_perde_acesso(client, app):
    outro = app.test_client()
    entrar(outro, "consulta")
    assert outro.get("/").status_code == 200

    entrar(client, "administrador")
    with app.app_context():
        uid = get_db().execute("SELECT id FROM usuarios WHERE perfil='consulta'").fetchone()[0]
    post(client, f"/admin/usuarios/{uid}/editar",
         {"nome": "Consulta", "perfil": "consulta"}, "/admin/usuarios")

    assert outro.get("/").status_code == 302
    assert "desativado" in entrar(outro, "consulta").get_data(as_text=True)


def test_configuracao_inicial_cria_o_administrador(tmp_path):
    app = create_app({"TESTING": True, "PASTA_DADOS": str(tmp_path)})
    # De outro computador da rede: só o aviso, sem formulário.
    remoto = app.test_client()
    remoto.environ_base["REMOTE_ADDR"] = "192.168.0.20"
    assert remoto.get("/login").headers["Location"] == "/configuracao-inicial"
    resp = remoto.get("/configuracao-inicial")
    assert resp.status_code == 403 and "computador servidor" in resp.get_data(as_text=True)

    # No próprio servidor: cria o administrador e já entra.
    client = app.test_client()
    url = "/configuracao-inicial"
    assert client.get("/").headers["Location"] == url
    resp = post(client, url, {"nome": "Douglas", "login": "douglas", "senha": "curta",
                              "confirmacao": "curta"}, url)
    assert "ao menos 8" in resp.get_data(as_text=True)
    resp = post(client, url, {"nome": "Douglas", "login": "douglas", "senha": SENHA,
                              "confirmacao": SENHA}, url)
    assert resp.headers["Location"] == "/"
    assert client.get("/").status_code == 200

    # Com administrador no banco, a tela deixa de existir e o login volta ao normal.
    assert client.get(url).status_code == 404
    assert remoto.get("/login").status_code == 200
    assert entrar(app.test_client(), "douglas").headers["Location"] == "/"

    # Banco restaurado (ou atualização): já tem administrador, nada é pedido.
    outra = create_app({"TESTING": True, "PASTA_DADOS": str(tmp_path)})
    assert outra.test_client().get("/login").status_code == 200


def test_equipe_com_minoria_efetiva_e_rejeitada(client):
    entrar(client, "pregoeiro")
    dados = dict(LICITACAO, membro1_id="3", membro2_id="4")
    html = post(client, "/licitacoes/nova", dados, "/licitacoes/nova").get_data(as_text=True)
    assert "maioria de servidores efetivos" in html
    assert "Caio Comissionado, Dora Temporária não são efetivos" in html

    dados = dict(LICITACAO, membro1_id="1")
    html = post(client, "/licitacoes/nova", dados, "/licitacoes/nova").get_data(as_text=True)
    assert "mais de uma função" in html


def test_equipe_completa_exigida_fora_do_planejamento(client):
    entrar(client, "pregoeiro")
    dados = dict(LICITACAO, membro2_id="")
    html = post(client, "/licitacoes/nova", dados, "/licitacoes/nova").get_data(as_text=True)
    assert "Informe a equipe" in html

    dados = dict(LICITACAO, membro2_id="", status="planejamento", data_sessao="")
    assert post(client, "/licitacoes/nova", dados, "/licitacoes/nova").status_code == 302


def test_credenciamento_aberto_e_renovado_anualmente(client):
    entrar(client, "gestor")
    dados = dict(LICITACAO, modalidade="Credenciamento", numero_edital="001/2026",
                 data_publicacao="2026-03-10", status="publicado")
    html = post(client, "/licitacoes/nova", dados, "/licitacoes/nova").get_data(as_text=True)
    assert "Credenciamento só pode estar em andamento" in html

    dados["status"] = "andamento"
    id_ = int(post(client, "/licitacoes/nova", dados, "/licitacoes/nova")
              .headers["Location"].rsplit("/", 1)[1])
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "10/03/2027" in pagina  # vigência padrão: 1 ano após a publicação
    assert "Suspender / remarcar" not in pagina

    post(client, f"/licitacoes/{id_}/renovar", {})
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "10/03/2028" in pagina and "Renovação do credenciamento" in pagina
    assert "Credenciamentos abertos" in client.get("/").get_data(as_text=True)
    assert "Credenciamento aberto" in client.get("/licitacoes/whatsapp").get_data(as_text=True)


def gestor_registra_ferias(client, servidor_id, inicio, fim):
    url = f"/admin/servidores/{servidor_id}/afastamentos"
    return post(client, url, {"tipo": "Férias", "inicio": inicio.isoformat(),
                              "fim": fim.isoformat()}, url)


def abrir_sessao(client, id_):
    resp = post(client, f"/licitacoes/{id_}/editar", dict(LICITACAO, status="andamento"),
                f"/licitacoes/{id_}/editar")
    assert resp.status_code == 302


def test_numero_do_edital_obrigatorio_apos_planejamento(client):
    entrar(client, "pregoeiro")
    html = post(client, "/licitacoes/nova", dict(LICITACAO, numero_edital=""),
                "/licitacoes/nova").get_data(as_text=True)
    assert "Informe o número do edital" in html


def test_painel_destaca_edital_cor_da_modalidade_e_equipe(client):
    entrar(client, "pregoeiro")
    criar_licitacao(client)
    html = client.get("/").get_data(as_text=True)
    assert '<a class="edital"' in html and "PE 010/2026" in html
    assert "--destaque: #1e7b3c" in html  # pregão eletrônico em verde
    assert "Pregoeiro(a):</span> Ana Efetiva" in html
    assert "Membros:</span> Beto Efetivo, Caio Comissionado" in html


def test_terceiro_membro_opcional(client):
    entrar(client, "pregoeiro")
    id_ = criar_licitacao(client)
    assert "Membro da equipe (3)" not in client.get(f"/licitacoes/{id_}").get_data(as_text=True)

    # Com 4 integrantes, 2 efetivos e 2 não efetivos é empate: não é maioria.
    editar = f"/licitacoes/{id_}/editar"
    html = post(client, editar, dict(LICITACAO, membro3_id="4"), editar).get_data(as_text=True)
    assert "Ao menos 3 dos 4 integrantes" in html

    resp = post(client, editar, dict(LICITACAO, membro3_id="5"), editar)
    assert resp.status_code == 302
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "Membro da equipe (3)" in pagina and "Eva Efetiva" in pagina
    assert "Beto Efetivo, Caio Comissionado, Eva Efetiva" in client.get("/").get_data(
        as_text=True)


def test_suspensao_e_remarcacao_antes_da_sessao(client):
    entrar(client, "pregoeiro")
    id_ = criar_licitacao(client)

    # Suspensão não é feita pelo formulário comum.
    html = post(client, f"/licitacoes/{id_}/editar", dict(LICITACAO, status="suspensa"),
                f"/licitacoes/{id_}/editar").get_data(as_text=True)
    assert "Suspender / remarcar" in html

    url = f"/licitacoes/{id_}/suspender"
    tela = client.get(url).get_data(as_text=True)
    assert "Suspensa antes da abertura" in tela and "análise documental" not in tela
    # Antes da abertura não cabe suspensão para análise documental.
    html = post(client, url, {"tipo": "suspensa_analise", "suspensa_em": "2026-10-20T14:35"}, url)
    assert "Escolha o que aconteceu" in html.get_data(as_text=True)

    post(client, url, {"tipo": "suspensa_antes", "suspensa_em": "2026-10-20T14:35",
                       "motivo": "Impugnação do edital"}, url)
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "Suspensa — sessão não aberta" in pagina and "20/10/2026 14:35" in pagina
    assert "Suspensas" in client.get("/").get_data(as_text=True)

    html = post(client, url, {"tipo": "remarcada_antes", "nova_data": "2020-01-01T10:00"}, url)
    assert "deve ser futura" in html.get_data(as_text=True)
    post(client, url, {"tipo": "remarcada_retificacao", "nova_data": "2030-02-15T10:00",
                       "data_retificacao": "2026-10-21"}, url)
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "Remarcada — edital retificado" in pagina and "15/02/2030 10:00" in pagina
    assert "De 20/10/2026" not in pagina
    assert f"De {SESSAO_BR} para 15/02/2030 10:00. Edital retificado em 21/10/2026" in pagina


def test_suspensao_para_analise_e_continuacao_com_sessao_em_andamento(client):
    entrar(client, "pregoeiro")
    id_ = criar_licitacao(client)
    abrir_sessao(client, id_)

    url = f"/licitacoes/{id_}/suspender"
    tela = client.get(url).get_data(as_text=True)
    assert "Suspensa para análise documental" in tela and "Suspensa antes" not in tela

    post(client, url, {"tipo": "suspensa_analise", "suspensa_em": "2026-10-21T11:00",
                       "motivo": "Análise da habilitação"}, url)
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "Em andamento — suspensa p/ análise documental" in pagina
    painel = client.get("/").get_data(as_text=True)
    assert "Em andamento — suspensa p/ análise documental" in painel

    post(client, url, {"tipo": "continuacao", "nova_data": "2030-03-01T14:00"}, url)
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "Em andamento — continuação" in pagina and "01/03/2030 14:00" in pagina
    assert "Remarcada pelo pregoeiro (continuação)" in pagina


def test_consulta_nao_suspende(client):
    entrar(client, "gestor")
    id_ = criar_licitacao(client)
    client.post("/logout", data={"_csrf": csrf(client, "/")})
    entrar(client, "consulta")
    assert client.get(f"/licitacoes/{id_}/suspender").status_code == 403


def test_membro_de_ferias_antes_da_sessao_deve_ser_trocado(client):
    entrar(client, "gestor")
    gestor_registra_ferias(client, 2, SESSAO - timedelta(days=2), SESSAO + timedelta(days=5))
    html = post(client, "/licitacoes/nova", LICITACAO, "/licitacoes/nova").get_data(as_text=True)
    assert "Membro impedido na data da sessão" in html and "Beto Efetivo" in html
    assert "manter_impedidos" not in html  # antes da sessão não há opção de manter
    assert post(client, "/licitacoes/nova", dict(LICITACAO, membro1_id="5"),
                "/licitacoes/nova").status_code == 302


def test_membro_impedido_com_sessao_em_andamento_pode_ser_mantido(client):
    entrar(client, "gestor")
    id_ = criar_licitacao(client)
    abrir_sessao(client, id_)

    resp = gestor_registra_ferias(client, 2, SESSAO, SESSAO + timedelta(days=3))
    html = client.get(resp.headers["Location"]).get_data(as_text=True)
    assert "Atenção: Beto Efetivo está escalado(a)" in html and "PE 010/2026" in html
    # O aviso fica na licitação (e na edição), não no painel inicial.
    assert "Membro de equipe impedido" not in client.get("/").get_data(as_text=True)
    assert "Membro impedido na data da sessão" in client.get(f"/licitacoes/{id_}").get_data(
        as_text=True)

    editar = f"/licitacoes/{id_}/editar"
    dados = dict(LICITACAO, status="andamento")
    html = post(client, editar, dados, editar).get_data(as_text=True)
    assert "troque o membro ou marque" in html and 'name="manter_impedidos"' in html

    assert post(client, editar, dict(dados, manter_impedidos="1"), editar).status_code == 302
    assert "Membro impedido na data da sessão" not in client.get(f"/licitacoes/{id_}").get_data(
        as_text=True)
    assert "Mantido membro impedido" in client.get(f"/licitacoes/{id_}").get_data(as_text=True)


def test_whatsapp_gera_imagem_de_celular(client):
    from PIL import Image

    entrar(client, "pregoeiro")
    id_ = criar_licitacao(client)
    post(client, "/licitacoes/nova", dict(LICITACAO, numero_processo="2026.HOMOLOG",
                                          status="homologada"), "/licitacoes/nova")
    post(client, "/licitacoes/nova", dict(LICITACAO, numero_processo="2026.PLANEJ",
                                          status="planejamento"), "/licitacoes/nova")
    html = client.get("/licitacoes/whatsapp").get_data(as_text=True)
    assert "/licitacoes/whatsapp/1.png" in html and "/licitacoes/whatsapp/2.png" not in html
    assert "PE 010/2026" in html and f"Sessão: {SESSAO:%d/%m/%Y} às 09:30" in html
    assert "Pregoeiro(a): Ana Efetiva" in html and "Membros: Beto Efetivo, Caio Comissionado" in html
    assert "2026.HOMOLOG" not in html and "2026.PLANEJ" not in html

    resp = client.get("/licitacoes/whatsapp/1.png")
    assert resp.mimetype == "image/png"
    assert Image.open(io.BytesIO(resp.data)).size == (1080, 1920)
    assert client.get(f"/licitacoes/{id_}/whatsapp.png").mimetype == "image/png"

    for n in range(8):
        post(client, "/licitacoes/nova", dict(LICITACAO, numero_edital=f"{n:03d}/2026"),
             "/licitacoes/nova")
    html = client.get("/licitacoes/whatsapp").get_data(as_text=True)
    assert "/licitacoes/whatsapp/2.png" in html
    assert client.get("/licitacoes/whatsapp/2.png").status_code == 200


def test_painel_mostra_sessoes_alem_de_30_dias(client):
    entrar(client, "pregoeiro")
    longe = dia_util(date.today() + timedelta(days=200)).isoformat() + "T09:00"
    post(client, "/licitacoes/nova", dict(LICITACAO, numero_edital="999/2027",
                                          data_sessao=longe), "/licitacoes/nova")
    assert "PE 999/2027" in client.get("/").get_data(as_text=True)


def sair(client):
    client.post("/logout", data={"_csrf": csrf(client, "/")})


def test_edital_digitado_sem_sigla(client, app):
    entrar(client, "pregoeiro")
    # Se a sigla for digitada por engano, ela é retirada; a tela mostra sigla + número.
    id_ = int(post(client, "/licitacoes/nova", dict(LICITACAO, numero_edital="pe 010/2026"),
                   "/licitacoes/nova").headers["Location"].rsplit("/", 1)[1])
    with app.app_context():
        assert get_db().execute("SELECT numero_edital FROM licitacoes WHERE id = ?",
                                (id_,)).fetchone()[0] == "010/2026"
    assert "PE 010/2026" in client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    html = post(client, "/licitacoes/nova", dict(LICITACAO, numero_edital="ABC 1/2026"),
                "/licitacoes/nova").get_data(as_text=True)
    assert "sem a sigla" in html
    # A busca aceita sigla + número.
    assert "PE 010/2026" in client.get("/licitacoes?q=PE+010").get_data(as_text=True)
    assert "PE 010/2026" not in client.get("/licitacoes?q=PP+010").get_data(as_text=True)


def test_administrador_altera_permissoes_dos_perfis(client):
    entrar(client, "gestor")
    assert client.get("/admin/perfis").status_code == 403
    sair(client)

    entrar(client, "administrador")
    tela = client.get("/admin/perfis").get_data(as_text=True)
    assert "Pregoeiro / Agente de Contratação" in tela
    # Gestor perde "excluir"; pregoeiro ganha "afastamentos".
    gestor = ["ver", "criar", "editar", "suspender", "servidores", "afastamentos", "auditoria",
              "parametros"]
    post(client, "/admin/perfis", {"perm_gestor": gestor,
                                   "perm_pregoeiro": ["ver", "criar", "editar", "suspender",
                                                      "afastamentos"],
                                   "perm_consulta": ["ver"]}, "/admin/perfis")
    assert "Alteração de permissões" in client.get("/admin/auditoria").get_data(as_text=True)
    sair(client)

    entrar(client, "gestor")
    id_ = criar_licitacao(client)
    assert post(client, f"/licitacoes/{id_}/excluir", {}).status_code == 403
    sair(client)
    entrar(client, "pregoeiro")
    assert client.get("/admin/servidores/2/afastamentos").status_code == 200


def test_gestor_altera_parametros(client):
    entrar(client, "pregoeiro")
    id_ = criar_licitacao(client)
    assert client.get("/admin/parametros").status_code == 403
    sair(client)

    entrar(client, "gestor")
    assert client.get("/admin/parametros").status_code == 200
    post(client, "/admin/parametros/geral", {"nome_orgao": "Secretaria de Saúde"},
         "/admin/parametros")
    assert "Secretaria de Saúde" in client.get("/").get_data(as_text=True)

    # Modalidade: nova sigla, novo nome e nova cor valem para as licitações existentes.
    post(client, "/admin/modalidades/1/editar",
         {"nome": "Pregão Eletrônico SRP", "sigla": "pes", "cor": "#123456", "ordem": "0",
          "ativa": "1", "exige_equipe": "1", "rotulo_condutor": "Pregoeiro(a)",
          "prazo_padrao": "bens_menor_preco",
          "prazos_permitidos": ["bens_menor_preco", "servicos_comuns"]},
         "/admin/modalidades/1/editar")
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "PES 010/2026" in pagina and "Pregão Eletrônico SRP" in pagina
    assert "--destaque: #123456" in client.get("/").get_data(as_text=True)

    # Situação do sistema: renomeia, mas não exclui.
    post(client, "/admin/situacoes/publicado/editar",
         {"nome": "Aviso publicado", "cor": "#0000aa", "ordem": "1"},
         "/admin/situacoes/publicado/editar")
    assert "Aviso publicado" in client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    post(client, "/admin/situacoes/publicado/excluir", {})
    assert "Aviso publicado" in client.get("/admin/parametros").get_data(as_text=True)

    # Nova situação de encerramento, que depois pode ser excluída por não estar em uso.
    post(client, "/admin/situacoes/nova", {"nome": "Cancelada", "cor": "#990000",
                                           "fase": "encerrada", "ordem": "20", "ativa": "1"},
         "/admin/situacoes/nova")
    assert "Cancelada" in client.get("/licitacoes/nova").get_data(as_text=True)
    post(client, "/admin/situacoes/cancelada/excluir", {})
    assert "Cancelada" not in client.get("/admin/parametros").get_data(as_text=True)


def test_painel_licitacoes_em_andamento(client):
    entrar(client, "pregoeiro")
    publicada = criar_licitacao(client)
    aberta = criar_licitacao(client)
    abrir_sessao(client, aberta)
    url = f"/licitacoes/{aberta}/suspender"
    post(client, url, {"tipo": "suspensa_analise", "suspensa_em": "2026-10-21T11:00"}, url)
    antes = criar_licitacao(client)
    url = f"/licitacoes/{antes}/suspender"
    post(client, url, {"tipo": "suspensa_antes", "suspensa_em": "2026-10-21T11:00"}, url)

    html = client.get("/").get_data(as_text=True)
    em_andamento = html.split("Licitações em andamento")[1].split("Suspensas antes")[0]
    assert "suspensa p/ análise documental" in em_andamento
    assert "Edital publicado" in em_andamento
    assert "sessão não aberta" not in em_andamento
    assert "sessão não aberta" in html.split("Suspensas antes")[1]
    assert publicada


def test_ordenacao_e_colunas_do_painel(client):
    entrar(client, "pregoeiro")
    for numero in ("002/2026", "010/2025", "001/2026"):
        post(client, "/licitacoes/nova", dict(LICITACAO, numero_edital=numero),
             "/licitacoes/nova")

    html = client.get("/?ordem=edital&dir=desc").get_data(as_text=True)
    assert html.index("PE 002/2026") < html.index("PE 001/2026") < html.index("PE 010/2025")
    # A escolha fica guardada para as próximas visitas.
    html = client.get("/").get_data(as_text=True)
    assert html.index("PE 002/2026") < html.index("PE 001/2026")

    post(client, "/preferencias/tabela",
         {"coluna": ["situacao", "edital", "objeto", "data"],
          "visivel": ["situacao", "edital", "data"], "ordem": "edital", "direcao": "asc",
          "voltar": "/"}, "/")
    html = client.get("/").get_data(as_text=True)
    tabela = html.split("Licitações em andamento")[1]
    assert tabela.index(">Situação") < tabela.index(">Edital") < tabela.index(">Data e hora")
    assert ">Objeto" not in tabela.split("</thead>")[0]
    assert html.index("PE 010/2025") < html.index("PE 001/2026") < html.index("PE 002/2026")


def test_feriado_e_fim_de_semana_impedem_a_sessao(client):
    entrar(client, "pregoeiro")
    for data_sessao, esperado in (("2026-12-25T09:00", "Natal"),
                                  ("2026-11-21T09:00", "sábado"),
                                  ("2027-01-20T09:00", "São Sebastião, padroeiro de Três Rios"),
                                  ("2027-04-23T09:00", "São Jorge")):
        html = post(client, "/licitacoes/nova", dict(LICITACAO, data_sessao=data_sessao),
                    "/licitacoes/nova").get_data(as_text=True)
        assert esperado in html, data_sessao

    # Ponto facultativo (Corpus Christi 2027): só com confirmação de expediente.
    dados = dict(LICITACAO, data_sessao="2027-05-27T09:00")
    html = post(client, "/licitacoes/nova", dados, "/licitacoes/nova").get_data(as_text=True)
    assert "Corpus Christi" in html and 'name="confirmar_ponto_facultativo"' in html
    resp = post(client, "/licitacoes/nova", dict(dados, confirmar_ponto_facultativo="1"),
                "/licitacoes/nova")
    assert resp.status_code == 302


def test_transferencia_de_feriado_municipal(client):
    entrar(client, "pregoeiro")
    assert client.get("/admin/feriados").status_code == 403
    sair(client)
    entrar(client, "gestor")
    id_ = criar_licitacao(client)
    with client.application.app_context():
        feriado = get_db().execute("SELECT id FROM feriados WHERE nome LIKE 'São Sebastião%'"
                                   ).fetchone()[0]
    # Decreto antecipa o padroeiro de 20/01/2027 (quarta) para 18/01/2027 (segunda).
    url = f"/admin/feriados/{feriado}/transferir?ano=2027"
    post(client, url, {"ano": "2027", "nova_data": "2027-01-18",
                       "ato": "Decreto municipal nº 1/2027"}, url)
    assert "transferido de 20/01" in client.get("/admin/feriados?ano=2027").get_data(
        as_text=True)

    editar = f"/licitacoes/{id_}/editar"
    html = post(client, editar, dict(LICITACAO, data_sessao="2027-01-18T09:00"),
                editar).get_data(as_text=True)
    assert "transferido de 20/01" in html
    assert post(client, editar, dict(LICITACAO, data_sessao="2027-01-20T09:00"),
                editar).status_code == 302
    assert "Transferência de feriado" in client.get("/admin/auditoria").get_data(as_text=True)


def test_ponto_facultativo_cadastrado_avisa_sessoes_marcadas(client):
    entrar(client, "gestor")
    criar_licitacao(client)
    resp = post(client, "/admin/feriados/novo",
                {"nome": "Ponto facultativo decretado", "tipo": "ponto_facultativo",
                 "abrangencia": "municipal", "regra": "data", "data": SESSAO.isoformat()},
                "/admin/feriados/novo")
    html = client.get(resp.headers["Location"]).get_data(as_text=True)
    assert "há sessão marcada" in html and "PE 010/2026" in html
    assert "Ponto facultativo decretado" in client.get(
        f"/calendario?ano={SESSAO.year}&mes={SESSAO.month}").get_data(as_text=True)


def test_prazo_minimo_legal_de_nova_licitacao(client):
    entrar(client, "pregoeiro")
    # Pregão de bens por menor preço: 8 dias úteis. Divulgado na segunda 01/03/2027, o prazo
    # corre de 02/03 a 11/03, e a sessão pode ser marcada para o próprio dia 11/03.
    base = dict(LICITACAO, data_publicacao="2027-03-01")
    html = post(client, "/licitacoes/nova", dict(base, data_sessao="2027-03-10T09:00"),
                "/licitacoes/nova").get_data(as_text=True)
    assert "Prazo mínimo legal não respeitado" in html and "a partir de 11/03/2027" in html
    resp = post(client, "/licitacoes/nova", dict(base, data_sessao="2027-03-11T09:00"),
                "/licitacoes/nova")
    assert resp.status_code == 302
    pagina = client.get(resp.headers["Location"]).get_data(as_text=True)
    assert "8 dias úteis" in pagina and "a partir de 11/03/2027" in pagina

    # Pregão de serviços comuns: 10 dias úteis (até 15/03).
    html = post(client, "/licitacoes/nova",
                dict(base, data_sessao="2027-03-12T09:00", prazo_hipotese="servicos_comuns"),
                "/licitacoes/nova").get_data(as_text=True)
    assert "exige 10 dias úteis" in html and "a partir de 15/03/2027" in html
    html = post(client, "/licitacoes/nova", dict(base, data_publicacao=""),
                "/licitacoes/nova").get_data(as_text=True)
    assert "Informe a data de publicação do edital" in html


def test_objeto_e_criterio_conforme_a_modalidade(client):
    entrar(client, "pregoeiro")
    base = dict(LICITACAO, data_publicacao="2027-03-01", data_sessao="2027-04-30T09:00")
    # Técnica e preço não cabe em pregão, mas cabe em concorrência (35 dias úteis).
    html = post(client, "/licitacoes/nova", dict(base, prazo_hipotese="tecnica"),
                "/licitacoes/nova").get_data(as_text=True)
    assert "não cabe na modalidade Pregão Eletrônico" in html
    concorrencia = dict(base, modalidade="Concorrência Eletrônica", prazo_hipotese="tecnica")
    html = post(client, "/licitacoes/nova", dict(concorrencia, data_sessao="2027-04-16T09:00"),
                "/licitacoes/nova").get_data(as_text=True)
    assert "exige 35 dias úteis" in html
    assert post(client, "/licitacoes/nova", concorrencia, "/licitacoes/nova").status_code == 302


def test_dispensa_conta_o_dia_do_aviso(client):
    entrar(client, "pregoeiro")
    # Aviso publicado na segunda 01/03/2027: conta 01, 02 e 03/03 — sessão a partir de 03/03.
    base = dict(LICITACAO, modalidade="Dispensa Eletrônica", data_publicacao="2027-03-01",
                prazo_hipotese="")
    html = post(client, "/licitacoes/nova", dict(base, data_sessao="2027-03-02T09:00"),
                "/licitacoes/nova").get_data(as_text=True)
    assert "a partir de 03/03/2027" in html
    assert post(client, "/licitacoes/nova", dict(base, data_sessao="2027-03-03T09:00"),
                "/licitacoes/nova").status_code == 302


RECURSO = {"intimado_em": "2027-11-19", "razoes_ate": "2027-11-24",
           "contrarrazoes_ate": "2027-11-29", "reconsideracao_ate": "2027-12-02",
           "decisao_ate": "2027-12-17"}


def test_recurso_e_prazos_no_painel(client):
    entrar(client, "pregoeiro")
    id_ = criar_licitacao(client)
    # Só cabe recurso com a sessão aberta.
    assert client.get(f"/licitacoes/{id_}/recurso").status_code == 400
    abrir_sessao(client, id_)
    url = f"/licitacoes/{id_}/recurso"
    # A tela já vem com a sugestão dos prazos legais, que o pregoeiro pode alterar.
    assert 'name="razoes_ate"' in client.get(url).get_data(as_text=True)

    # Datas fora de ordem ou em dia sem expediente são recusadas.
    html = post(client, url, dict(RECURSO, contrarrazoes_ate="2027-11-23"), url).get_data(
        as_text=True)
    assert "Contrarrazões até não pode ser antes" in html
    html = post(client, url, dict(RECURSO, decisao_ate="2027-12-14"), url).get_data(as_text=True)
    assert "não é dia útil" in html and "Emancipação de Três Rios" in html

    post(client, url, RECURSO, url)
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    for data in ("24/11/2027", "29/11/2027", "02/12/2027", "17/12/2027"):
        assert data in pagina
    painel = client.get("/").get_data(as_text=True)
    assert "Em recurso — prazos" in painel and "24/11/2027" in painel

    # Licitação presencial: o pregoeiro notifica as empresas e ajusta as contrarrazões.
    prazos = f"/licitacoes/{id_}/recurso/prazos"
    post(client, prazos, dict(RECURSO, notificado_em="2027-11-25", contrarrazoes_ate="2027-11-30",
                              reconsideracao_ate="2027-12-03"), prazos)
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "25/11/2027" in pagina and "30/11/2027" in pagina
    assert "Prazos do recurso alterados" in pagina

    # Enquanto o recurso corre, a situação só muda pela decisão.
    html = post(client, f"/licitacoes/{id_}/editar", dict(LICITACAO, status="homologada"),
                f"/licitacoes/{id_}/editar").get_data(as_text=True)
    assert "registre a decisão do recurso" in html
    decisao = f"/licitacoes/{id_}/recurso/decisao"
    post(client, decisao, {"decidido_em": "2027-12-10", "resultado": "Não provido",
                           "status": "homologada"}, decisao)
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "Não provido em 10/12/2027" in pagina and "Homologada" in pagina
    assert "Em recurso — prazos" not in client.get("/").get_data(as_text=True)


def test_sugestao_de_prazos_do_recurso(app):
    from licitacoes.agenda import prazos_recurso
    with app.test_request_context():
        # Contrarrazões contam do fim das razões ou, se houver, da notificação das empresas.
        assert prazos_recurso(date(2027, 11, 19)) == {
            "razoes_ate": "2027-11-24", "contrarrazoes_ate": "2027-11-29",
            "reconsideracao_ate": "2027-12-02", "decisao_ate": "2027-12-17"}
        assert prazos_recurso(date(2027, 11, 19), date(2027, 11, 25))["contrarrazoes_ate"] \
            == "2027-11-30"


def test_painel_mostra_so_os_quadros_necessarios(client):
    entrar(client, "pregoeiro")
    html = client.get("/").get_data(as_text=True)
    assert "Nenhuma licitação cadastrada" in html
    for quadro in ("Licitações em andamento", "Em recurso", "Suspensas antes",
                   "Credenciamentos abertos", "Colunas e ordenação", "Sessões de hoje"):
        assert quadro not in html
    criar_licitacao(client)
    html = client.get("/").get_data(as_text=True)
    assert "Licitações em andamento" in html and "Colunas e ordenação" in html
    for quadro in ("Em recurso", "Suspensas antes", "Credenciamentos abertos"):
        assert quadro not in html


def test_brasao_no_cabecalho_e_na_imagem(client):
    from PIL import Image

    entrar(client, "gestor")
    criar_licitacao(client)
    assert client.get("/brasao.png").status_code == 404

    grande = io.BytesIO()
    Image.new("RGBA", (1200, 1600), (200, 30, 30, 255)).save(grande, "PNG")
    grande.seek(0)
    post(client, "/admin/parametros/brasao", {"brasao": (grande, "brasao.png")},
         "/admin/parametros")
    resp = client.get("/brasao.png")
    assert resp.status_code == 200
    # Guardado reduzido proporcionalmente (3:4).
    assert Image.open(io.BytesIO(resp.data)).size == (450, 600)
    assert 'class="brasao"' in client.get("/").get_data(as_text=True)

    imagem = Image.open(io.BytesIO(client.get("/licitacoes/whatsapp/1.png").data)).convert("RGB")
    # O brasão vermelho aparece à esquerda do cabeçalho azul.
    assert imagem.getpixel((70, 100)) == (200, 30, 30)

    html = post(client, "/admin/parametros/brasao",
                {"brasao": (io.BytesIO(b"isto nao e imagem"), "brasao.png")},
                "/admin/parametros")
    assert "não é uma imagem válida" in client.get(html.headers["Location"]).get_data(
        as_text=True)
    post(client, "/admin/parametros/brasao/remover", {}, "/admin/parametros")
    assert client.get("/brasao.png").status_code == 404


def test_filtro_de_situacoes_no_whatsapp(client):
    entrar(client, "gestor")
    criar_licitacao(client)
    assert "PE 010/2026" in client.get("/licitacoes/whatsapp").get_data(as_text=True)
    marcadas = ["andamento", "recurso"]  # sem "Edital publicado"
    post(client, "/admin/situacoes/whatsapp", {"whatsapp": marcadas}, "/admin/parametros")
    assert "PE 010/2026" not in client.get("/licitacoes/whatsapp").get_data(as_text=True)
    post(client, "/admin/situacoes/whatsapp", {"whatsapp": marcadas + ["publicado"]},
         "/admin/parametros")
    assert "PE 010/2026" in client.get("/licitacoes/whatsapp").get_data(as_text=True)


def test_feriados_ajustados(client):
    entrar(client, "pregoeiro")
    for data_sessao, esperado in (("2027-12-14T09:00", "Emancipação de Três Rios"),
                                  ("2027-02-09T09:00", "Carnaval (terça-feira)"),
                                  ("2027-10-28T09:00", "Dia do Servidor")):
        html = post(client, "/licitacoes/nova", dict(LICITACAO, data_sessao=data_sessao),
                    "/licitacoes/nova").get_data(as_text=True)
        assert esperado in html and 'name="confirmar_ponto_facultativo"' not in html


def test_remarcacao_por_retificacao_reabre_o_prazo(client):
    entrar(client, "pregoeiro")
    id_ = criar_licitacao(client)
    url = f"/licitacoes/{id_}/suspender"
    base = {"tipo": "remarcada_retificacao", "data_retificacao": "2030-04-01"}
    # Retificado em 01/04/2030 (segunda): 8 dias úteis vão até 11/04, data mínima da sessão.
    html = post(client, url, dict(base, nova_data="2030-04-10T10:00"), url).get_data(as_text=True)
    assert "a partir de 11/04/2030" in html
    html = post(client, url, {"tipo": "remarcada_retificacao", "nova_data": "2030-04-10T10:00"},
                url).get_data(as_text=True)
    assert "divulgação do edital retificado" in html
    html = post(client, url, dict(base, nova_data="2030-04-19T10:00"), url).get_data(as_text=True)
    assert "Paixão de Cristo" in html

    # Se a alteração não afeta as propostas, o prazo não reabre.
    post(client, url, {"tipo": "remarcada_retificacao", "nova_data": "2030-04-10T10:00",
                       "sem_novo_prazo": "1"}, url)
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "10/04/2030 10:00" in pagina and "Sem reabertura de prazo" in pagina

    post(client, url, dict(base, nova_data="2030-04-11T10:00"), url)
    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "11/04/2030 10:00" in pagina and "contado da retificação em 01/04/2030" in pagina


def test_imagem_encaixa_mais_licitacoes(client):
    entrar(client, "pregoeiro")
    for n in range(6):
        post(client, "/licitacoes/nova", dict(LICITACAO, numero_edital=f"{n:03d}/2026"),
             "/licitacoes/nova")
    html = client.get("/licitacoes/whatsapp").get_data(as_text=True)
    assert "/licitacoes/whatsapp/1.png" in html and "/licitacoes/whatsapp/2.png" not in html


def test_banco_antigo_e_convertido(tmp_path):
    import sqlite3
    caminho = tmp_path / "antigo.sqlite3"
    conn = sqlite3.connect(caminho)
    conn.execute("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, nome TEXT, login TEXT,"
                 " email TEXT, senha_hash TEXT, perfil TEXT, ativo INTEGER, trocar_senha INTEGER,"
                 " criado_em TEXT)")
    conn.execute("INSERT INTO usuarios (nome, login, senha_hash, perfil, ativo, trocar_senha)"
                 " VALUES ('Op', 'op', 'x', 'operador', 1, 0)")
    # Tabela como era na versão anterior, sem as colunas novas.
    conn.execute("CREATE TABLE licitacoes (id INTEGER PRIMARY KEY, numero_processo TEXT,"
                 " numero_edital TEXT, modalidade TEXT, objeto TEXT, data_publicacao TEXT,"
                 " data_sessao TEXT, vigencia_ate TEXT, local TEXT, agente_id INTEGER,"
                 " membro1_id INTEGER, membro2_id INTEGER, valor_estimado REAL, status TEXT,"
                 " suspensa_em TEXT, motivo_suspensao TEXT, observacoes TEXT, criado_por INTEGER,"
                 " criado_em TEXT, atualizado_em TEXT)")
    conn.execute("INSERT INTO licitacoes (numero_processo, numero_edital, modalidade, objeto,"
                 " status) VALUES ('1', 'PE 012/2026', 'Pregão Eletrônico', 'x', 'Em andamento')")
    conn.commit()
    conn.close()
    create_app({"TESTING": True, "DATABASE": str(caminho)})
    conn = sqlite3.connect(caminho)
    colunas = {c[1] for c in conn.execute("PRAGMA table_info(licitacoes)")}
    assert {"membro3_id", "ocorrencia", "impedimentos_mantidos"} <= colunas
    assert conn.execute("SELECT numero_edital, status FROM licitacoes").fetchone() == (
        "012/2026", "andamento")
    assert conn.execute("SELECT perfil FROM usuarios").fetchone()[0] == "pregoeiro"


def test_banco_da_versao_anterior_recebe_recursos_e_ajustes(tmp_path):
    import sqlite3
    caminho = tmp_path / "v2.sqlite3"
    create_app({"TESTING": True, "DATABASE": str(caminho)})
    # Simula o banco como era antes desta versão.
    conn = sqlite3.connect(caminho)
    conn.executescript("""
        DELETE FROM situacoes WHERE chave = 'recurso';
        UPDATE situacoes SET whatsapp = 0;
        UPDATE modalidades SET prazos_permitidos = 'nao_se_aplica';
        UPDATE feriados SET dia = 26 WHERE nome = 'Emancipação de Três Rios';
        UPDATE feriados SET tipo = 'ponto_facultativo'
         WHERE nome IN ('Carnaval (terça-feira)', 'Dia do Servidor Público');
        DELETE FROM permissoes WHERE permissao = 'recursos';
        PRAGMA user_version = 2;
    """)
    conn.commit()
    conn.close()

    create_app({"TESTING": True, "DATABASE": str(caminho)})
    conn = sqlite3.connect(caminho)
    assert conn.execute("SELECT fase FROM situacoes WHERE chave = 'recurso'").fetchone() == (
        "andamento",)
    assert conn.execute("SELECT whatsapp FROM situacoes WHERE chave = 'publicado'"
                        ).fetchone() == (1,)
    assert conn.execute("SELECT prazos_permitidos FROM modalidades WHERE sigla = 'PE'"
                        ).fetchone() == ("bens_menor_preco,servicos_comuns",)
    assert conn.execute("SELECT dia FROM feriados WHERE nome = 'Emancipação de Três Rios'"
                        ).fetchone() == (14,)
    assert {t for (t,) in conn.execute(
        "SELECT tipo FROM feriados WHERE nome IN ('Carnaval (terça-feira)',"
        " 'Dia do Servidor Público')")} == {"feriado"}
    assert conn.execute("SELECT 1 FROM permissoes WHERE perfil = 'pregoeiro'"
                        " AND permissao = 'recursos'").fetchone()


def test_edicao_simultanea_nao_sobrescreve(app, client):
    entrar(client, "pregoeiro")
    id_ = criar_licitacao(client)
    outro = app.test_client()
    entrar(outro, "gestor")

    editar = f"/licitacoes/{id_}/editar"
    # Os dois abrem a edição ao mesmo tempo (mesma versão da licitação).
    token_1, token_2 = csrf(client, editar), csrf(outro, editar)
    versao = re.search(r'name="versao" value="(\d+)"', client.get(editar).get_data(
        as_text=True)).group(1)

    resp = client.post(editar, data=dict(LICITACAO, objeto="Alterado pelo pregoeiro",
                                         versao=versao, _csrf=token_1))
    assert resp.status_code == 302
    html = outro.post(editar, data=dict(LICITACAO, objeto="Alterado pelo gestor",
                                        versao=versao, _csrf=token_2)).get_data(as_text=True)
    assert "foi alterada por Pregoeiro" in html and "não foram salvas" in html
    assert "Alterado pelo pregoeiro" in html  # o formulário volta com os dados atuais

    pagina = client.get(f"/licitacoes/{id_}").get_data(as_text=True)
    assert "Alterado pelo pregoeiro" in pagina and "Alterado pelo gestor" not in pagina
    # Com a versão atual, a nova edição é aceita.
    nova = re.search(r'name="versao" value="(\d+)"', html).group(1)
    resp = outro.post(editar, data=dict(LICITACAO, objeto="Alterado pelo gestor",
                                        versao=nova, _csrf=token_2))
    assert resp.status_code == 302


def test_varios_usuarios_cadastrando_ao_mesmo_tempo(app):
    import threading

    clientes = []
    for _ in range(8):
        c = app.test_client()
        entrar(c, "pregoeiro")
        clientes.append((c, csrf(c, "/licitacoes/nova")))
    resultados = []

    def cadastrar(cliente, token, n):
        for i in range(5):
            resp = cliente.post("/licitacoes/nova", data=dict(
                LICITACAO, numero_processo=f"T{n}-{i}", numero_edital=f"{n}{i:02d}/2026",
                _csrf=token))
            resultados.append(resp.status_code)

    tarefas = [threading.Thread(target=cadastrar, args=(c, t, n))
               for n, (c, t) in enumerate(clientes)]
    for t in tarefas:
        t.start()
    for t in tarefas:
        t.join()

    assert resultados.count(302) == 40
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM licitacoes").fetchone()[0] == 40
        assert get_db().execute("SELECT COUNT(*) FROM historico WHERE acao ="
                                " 'Cadastro de licitação'").fetchone()[0] == 40


def test_pasta_de_dados_fora_do_programa(tmp_path):
    dados = tmp_path / "dados"
    app = create_app({"TESTING": True, "PASTA_DADOS": str(dados)})
    assert app.config["DATABASE"] == str(dados / "licitacoes.sqlite3")
    assert (dados / "licitacoes.sqlite3").exists() and (dados / "secret_key").exists()
    assert app.config["PASTA_ARQUIVOS"] == str(dados)


def test_atalho_para_os_usuarios(tmp_path):
    import servidor

    caminho = servidor.criar_atalho(str(tmp_path), "http://SERVIDOR:8080/")
    with open(caminho, "rb") as arquivo:
        assert arquivo.read() == b"[InternetShortcut]\r\nURL=http://SERVIDOR:8080/\r\n"
    assert all(not ip.startswith("127.") for ip in servidor.enderecos_ipv4())


def _anfitriao(tmp_path, nome, nuvem):
    from licitacoes.nuvem import CopiaNuvem

    return CopiaNuvem(str(nuvem), str(tmp_path / nome), computador=nome)


def _contar(pasta, tabela):
    import sqlite3

    conn = sqlite3.connect(os.path.join(pasta, "licitacoes.sqlite3"))
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
    finally:
        conn.close()


def _novo_usuario(app, login, perfil="administrador", nome="Maria Silva"):
    with app.app_context():
        get_db().execute(
            "INSERT INTO usuarios (nome, login, login_cifrado, senha_hash, perfil, trocar_senha)"
            " VALUES (?, ?, ?, ?, ?, 0)",
            (nome, cripto.indice_login(login), cripto.cifrar_login(login),
             generate_password_hash(SENHA), perfil))
        get_db().commit()


RECUPERACAO = "Cofre#Agenda-77"


def test_copia_na_nuvem_criptografada_e_restauracao_em_outro_computador(tmp_path):
    from licitacoes import nuvem as modulo

    nuvem = tmp_path / "Meu Drive" / "AgendaLicitacoes"
    a = _anfitriao(tmp_path, "PC-A", nuvem)
    a.assumir()
    app = create_app({"TESTING": True, "PASTA_DADOS": a.dados, "NUVEM": a})
    _novo_usuario(app, "maria.silva")
    (tmp_path / "PC-A" / "brasao.png").write_bytes(b"png")
    # Sem senha de recuperação, nada vai para a nuvem.
    assert a.verificar_chave() == modulo.SEM_SENHA and not a.copiar(forcar=True)
    assert not (nuvem / "licitacoes.cifrado").exists()

    a.definir_senha_recuperacao(RECUPERACAO)
    assert a.ultima_copia and not a.copiar()  # nada mudou: não copia de novo
    copia = (nuvem / "licitacoes.cifrado").read_bytes()
    assert b"SQLite format" not in copia and b"maria.silva" not in copia
    assert b"maria.silva" not in (tmp_path / "PC-A" / "licitacoes.sqlite3").read_bytes()
    assert (nuvem / "chave.json").exists() and (nuvem / "brasao.png").exists()
    assert len(list((nuvem / "copias-diarias").iterdir())) == 1

    # O PC-A parou de responder: o PC-B só assume depois que a trava vence.
    b = _anfitriao(tmp_path, "PC-B", nuvem)
    with pytest.raises(modulo.OutroAnfitriao):
        b.assumir()
    trava = json.loads((nuvem / "anfitriao.json").read_text(encoding="utf-8"))
    trava["renovada"] -= modulo.TRAVA_VENCIDA + 1
    (nuvem / "anfitriao.json").write_text(json.dumps(trava), encoding="utf-8")
    b.assumir()
    assert b.verificar_chave() == modulo.AGUARDANDO
    app_b = create_app({"TESTING": True, "PASTA_DADOS": b.dados, "NUVEM": b})
    assert b.verificar_chave() == modulo.AGUARDANDO  # chave nova do PC-B não é a da nuvem
    assert not b.copiar(forcar=True)

    # A senha de recuperação só é aceita no próprio computador.
    remoto = app_b.test_client()
    remoto.environ_base["REMOTE_ADDR"] = "192.168.0.20"
    assert remoto.get("/login").headers["Location"] == "/recuperacao"
    assert remoto.get("/recuperacao").status_code == 403
    client = app_b.test_client()
    assert client.get("/").headers["Location"] == "/recuperacao"
    resp = post(client, "/recuperacao", {"senha": "Errada#2026x"}, "/recuperacao")
    assert "Senha de recuperação incorreta" in resp.get_data(as_text=True)
    resp = post(client, "/recuperacao", {"senha": RECUPERACAO}, "/recuperacao")
    assert resp.headers["Location"] == "/login"
    assert "PC-A" in client.get("/login").get_data(as_text=True)
    assert entrar(client, "maria.silva").headers["Location"] == "/"
    assert (tmp_path / "PC-B" / "brasao.png").read_bytes() == b"png"
    assert b.copiar(forcar=True)

    # O PC-A volta: percebe que perdeu a vez e não sobrescreve a cópia do PC-B.
    a._renovar_trava()
    assert a.perdeu_a_vez and not a.copiar(forcar=True)
    assert json.loads((nuvem / "copia.json").read_text(encoding="utf-8"))["computador"] == "PC-B"

    # Mais tarde o PC-B é desligado e o PC-A reassume: traz o banco do PC-B e guarda o seu.
    b.encerrar()
    assert not (nuvem / "anfitriao.json").exists()
    a2 = _anfitriao(tmp_path, "PC-A", nuvem)
    a2.assumir()
    assert a2.verificar_chave() == modulo.PRONTA
    assert a2.restaurar_se_preciso()
    assert any(p.name.startswith("licitacoes.anterior-") for p in (tmp_path / "PC-A").iterdir())
    a2.copiar()
    # Reiniciado, o mesmo computador retoma a vez e mantém o próprio banco.
    a3 = _anfitriao(tmp_path, "PC-A", nuvem)
    a3.assumir()
    a3.verificar_chave()
    assert a3.restaurar_se_preciso() is None


def test_copias_diarias_guardam_trinta_dias(tmp_path):
    nuvem = tmp_path / "nuvem"
    a = _anfitriao(tmp_path, "PC-A", nuvem)
    create_app({"TESTING": True, "PASTA_DADOS": a.dados})
    diarias = nuvem / "copias-diarias"
    diarias.mkdir(parents=True)
    for dia in range(1, 36):
        (diarias / f"licitacoes-2026-01-{dia:02d}.cifrado").write_bytes(b"")
    a.definir_senha_recuperacao(RECUPERACAO)
    nomes = sorted(p.name for p in diarias.iterdir())
    assert len(nomes) == 30 and "licitacoes-2026-01-01.cifrado" not in nomes

    # Restaurar um dia anterior: a cópia diária volta a ser o banco deste computador.
    hoje = [p for p in diarias.iterdir() if p.stat().st_size][0]
    _novo_usuario(create_app({"TESTING": True, "PASTA_DADOS": a.dados}), "depois.da.copia")
    assert _contar(a.dados, "usuarios") == 1
    a.restaurar_arquivo(str(hoje))
    assert _contar(a.dados, "usuarios") == 0  # o usuário foi criado depois da cópia


def test_configuracao_inicial_pede_a_senha_de_recuperacao(tmp_path):
    from licitacoes import nuvem as modulo

    a = _anfitriao(tmp_path, "PC-A", tmp_path / "nuvem")
    app = create_app({"TESTING": True, "PASTA_DADOS": a.dados, "NUVEM": a})
    client = app.test_client()
    url = "/configuracao-inicial"
    assert "Senha de recuperação" in client.get(url).get_data(as_text=True)
    dados = {"nome": "Douglas", "login": "douglas", "senha": SENHA, "confirmacao": SENHA,
             "recuperacao": SENHA, "recuperacao_confirmacao": SENHA}
    assert "diferente da senha do administrador" in post(client, url, dados, url).get_data(
        as_text=True)
    dados.update(recuperacao=RECUPERACAO, recuperacao_confirmacao=RECUPERACAO)
    assert post(client, url, dados, url).headers["Location"] == "/"
    assert a.estado == modulo.PRONTA and (tmp_path / "nuvem" / "licitacoes.cifrado").exists()

    # Troca da senha de recuperação: só o administrador, confirmando a própria senha.
    pagina = "/admin/parametros"
    post(client, "/admin/parametros/recuperacao",
            {"senha_atual": "errada", "recuperacao": "Outra#Chave-88",
             "recuperacao_confirmacao": "Outra#Chave-88"}, pagina)
    assert "não confere" in client.get(pagina).get_data(as_text=True)
    post(client, "/admin/parametros/recuperacao",
         {"senha_atual": SENHA, "recuperacao": "Outra#Chave-88",
          "recuperacao_confirmacao": "Outra#Chave-88"}, pagina)
    embrulho = json.loads((tmp_path / "nuvem" / "chave.json").read_text(encoding="utf-8"))
    assert cripto.desembrulhar(embrulho, "Outra#Chave-88") == app.config["CHAVE_DADOS"]
    with pytest.raises(ValueError):
        cripto.desembrulhar(embrulho, RECUPERACAO)


def test_situacao_da_copia_nas_configuracoes(app, client):
    entrar(client, "administrador")
    assert "Não configurada" in client.get("/admin/parametros").get_data(as_text=True)

    class Copia:
        pasta, intervalo, ultima_copia = r"G:\Meu Drive\Agenda", 300, "03/11/2026 10:15"
        ultimo_erro, estado = None, "pronta"

    app.config["NUVEM"] = Copia()
    html = client.get("/admin/parametros").get_data(as_text=True)
    assert "03/11/2026 10:15" in html and "a cada 5 minuto(s)" in html
    Copia.estado = "sem_senha"
    assert "falta definir a senha de recuperação" in client.get(
        "/admin/parametros").get_data(as_text=True)


def test_logins_ficam_cifrados_no_banco(app, client, tmp_path):
    assert entrar(client, "Administrador").headers["Location"] == "/"  # maiúsculas não importam
    html = client.get("/admin/usuarios").get_data(as_text=True)
    assert ">pregoeiro<" in html
    with app.app_context():
        logins = [r[0] for r in get_db().execute("SELECT login FROM usuarios")]
    assert "pregoeiro" not in logins and all(len(l) == 64 for l in logins)


def test_migracao_cifra_logins_antigos(tmp_path):
    import sqlite3

    app = create_app({"TESTING": True, "PASTA_DADOS": str(tmp_path)})
    _novo_usuario(app, "provisorio")
    conn = sqlite3.connect(str(tmp_path / "licitacoes.sqlite3"))
    conn.execute("UPDATE usuarios SET login = 'joao.antigo', login_cifrado = NULL")
    conn.execute("INSERT INTO historico (acao, referencia) VALUES ('Login', 'joao.antigo')")
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    conn.close()
    app = create_app({"TESTING": True, "PASTA_DADOS": str(tmp_path)})
    assert entrar(app.test_client(), "joao.antigo").headers["Location"] == "/"
    with app.app_context():
        assert get_db().execute("SELECT referencia FROM historico WHERE acao = 'Login'"
                                " ORDER BY id LIMIT 1").fetchone()[0] == "Maria Silva"
    assert b"joao.antigo" not in (tmp_path / "licitacoes.sqlite3").read_bytes()


@pytest.mark.parametrize("senha, motivo", [
    ("Curta1!", "ao menos 8"),
    ("somenteletras", "letras e também"),
    ("12345678", "letras e também"),
    ("senha123", "fácil"),
    ("S3nh@2026", "fácil"),
    ("Prefeitura2026!", "fácil"),
    ("qwerty12", "fácil"),
    ("abcdefgh1", "fácil"),
    ("aaaa1111", "fácil"),
    ("Pregoeiro#99", "fácil"),
    ("Maria.2026x", "nome"),
    ("x-maria.silva-9", "login"),
])
def test_senhas_faceis_sao_recusadas(senha, motivo):
    from licitacoes.senhas import problema

    assert motivo in problema(senha, login="maria.silva", nome="Maria Silva")
    assert problema("Kq8#mZ2!rio", login="maria.silva", nome="Maria Silva") is None


def test_troca_de_senha_nao_aceita_facil_nem_a_anterior(app, client):
    entrar(client, "gestor")
    dados = {"senha_atual": SENHA, "nova_senha": "12345678a", "confirmacao": "12345678a"}
    assert "fácil" in post(client, "/senha", dados, "/senha").get_data(as_text=True)
    dados.update(nova_senha=SENHA, confirmacao=SENHA)
    assert "já foi usada" in post(client, "/senha", dados, "/senha").get_data(as_text=True)
    dados.update(nova_senha="Rio#Paraiba-41", confirmacao="Rio#Paraiba-41")
    assert post(client, "/senha", dados, "/senha").headers["Location"] == "/"

    # O administrador redefine (senha temporária): voltar às duas últimas pessoais é recusado.
    admin = app.test_client()
    entrar(admin, "administrador")
    with app.app_context():
        uid = get_db().execute("SELECT id FROM usuarios WHERE perfil='gestor'").fetchone()[0]
    post(admin, f"/admin/usuarios/{uid}/redefinir-senha", {}, "/admin/usuarios")
    temporaria = re.search(r"Nova senha temporária de “gestor”: ([A-Za-z0-9_-]+)",
                           admin.get("/admin/usuarios").get_data(as_text=True)).group(1)
    novo = app.test_client()
    entrar(novo, "gestor", temporaria)
    dados = {"senha_atual": temporaria, "nova_senha": "Rio#Paraiba-41",
             "confirmacao": "Rio#Paraiba-41"}
    assert "já foi usada" in post(novo, "/senha", dados, "/senha").get_data(as_text=True)
    dados.update(nova_senha="Serra#Mar-2027", confirmacao="Serra#Mar-2027")
    assert post(novo, "/senha", dados, "/senha").headers["Location"] == "/"
