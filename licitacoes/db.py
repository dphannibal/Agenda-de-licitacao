"""Acesso ao banco de dados SQLite."""
import re
import sqlite3

from flask import current_app, g

from . import cripto, perfis

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nome          TEXT    NOT NULL,
    login         TEXT    NOT NULL UNIQUE COLLATE NOCASE,  -- índice do login (cripto.py)
    login_cifrado TEXT,                   -- login cifrado, para as telas
    email         TEXT,
    senha_hash    TEXT    NOT NULL,
    senha_anterior_hash TEXT,             -- impede voltar à senha usada antes
    perfil        TEXT    NOT NULL,
    ativo         INTEGER NOT NULL DEFAULT 1,
    trocar_senha  INTEGER NOT NULL DEFAULT 1,
    preferencias  TEXT,                   -- JSON: colunas e ordenação das tabelas
    criado_em     TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS servidores (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nome       TEXT    NOT NULL,
    matricula  TEXT,
    vinculo    TEXT    NOT NULL,
    ativo      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS licitacoes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_processo   TEXT    NOT NULL,
    numero_edital     TEXT,
    modalidade        TEXT    NOT NULL,
    objeto            TEXT    NOT NULL,
    data_publicacao   TEXT,               -- data de publicação do edital
    data_sessao       TEXT,               -- sessão pública (não se aplica a credenciamento)
    vigencia_ate      TEXT,               -- credenciamento: vencimento da vigência anual
    local             TEXT,
    agente_id         INTEGER REFERENCES servidores(id) ON DELETE SET NULL,
    membro1_id        INTEGER REFERENCES servidores(id) ON DELETE SET NULL,
    membro2_id        INTEGER REFERENCES servidores(id) ON DELETE SET NULL,
    membro3_id        INTEGER REFERENCES servidores(id) ON DELETE SET NULL,  -- opcional, raro
    valor_estimado    REAL,
    status            TEXT    NOT NULL,
    suspensa_em       TEXT,               -- data e hora em que a sessão foi suspensa
    motivo_suspensao  TEXT,
    ocorrencia        TEXT,               -- última suspensão/remarcação (ver perfis.OCORRENCIAS)
    impedimentos_mantidos TEXT,           -- ids de afastamentos aceitos com a sessão em andamento
    prazo_hipotese    TEXT,               -- enquadramento do prazo mínimo (perfis.PRAZOS)
    retificado_em     TEXT,               -- republicação do edital retificado (reinicia o prazo)
    versao            INTEGER NOT NULL DEFAULT 0,  -- muda a cada alteração (edição simultânea)
    observacoes       TEXT,
    criado_por        INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em         TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    atualizado_em     TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_licitacoes_data ON licitacoes(data_sessao);
CREATE INDEX IF NOT EXISTS idx_licitacoes_vigencia ON licitacoes(vigencia_ate);

CREATE TABLE IF NOT EXISTS afastamentos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    servidor_id  INTEGER NOT NULL REFERENCES servidores(id) ON DELETE CASCADE,
    tipo         TEXT    NOT NULL,
    inicio       TEXT    NOT NULL,
    fim          TEXT    NOT NULL,
    observacao   TEXT
);

CREATE INDEX IF NOT EXISTS idx_afastamentos_periodo ON afastamentos(inicio, fim);

CREATE TABLE IF NOT EXISTS configuracoes (
    chave  TEXT PRIMARY KEY,
    valor  TEXT
);

CREATE TABLE IF NOT EXISTS modalidades (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    nome             TEXT    NOT NULL UNIQUE,
    sigla            TEXT    NOT NULL,
    cor              TEXT    NOT NULL,
    ordem            INTEGER NOT NULL DEFAULT 0,
    ativa            INTEGER NOT NULL DEFAULT 1,
    credenciamento   INTEGER NOT NULL DEFAULT 0,  -- aberta, sem sessão, vigência anual
    exige_equipe     INTEGER NOT NULL DEFAULT 1,
    rotulo_condutor  TEXT    NOT NULL DEFAULT 'Agente de contratação',
    prazo_padrao     TEXT    NOT NULL DEFAULT 'nao_se_aplica',  -- ver perfis.PRAZOS
    prazos_permitidos TEXT   NOT NULL DEFAULT 'nao_se_aplica'   -- critérios de julgamento cabíveis
);

CREATE TABLE IF NOT EXISTS situacoes (
    chave    TEXT    PRIMARY KEY,
    nome     TEXT    NOT NULL UNIQUE,
    cor      TEXT    NOT NULL,
    fase     TEXT    NOT NULL,
    ordem    INTEGER NOT NULL DEFAULT 0,
    ativa    INTEGER NOT NULL DEFAULT 1,
    sistema  INTEGER NOT NULL DEFAULT 0,
    whatsapp INTEGER NOT NULL DEFAULT 0   -- exportada na imagem do WhatsApp
);

CREATE TABLE IF NOT EXISTS permissoes (
    perfil     TEXT NOT NULL,
    permissao  TEXT NOT NULL,
    PRIMARY KEY (perfil, permissao)
);

CREATE TABLE IF NOT EXISTS feriados (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nome          TEXT    NOT NULL,
    tipo          TEXT    NOT NULL,       -- feriado | ponto_facultativo
    abrangencia   TEXT    NOT NULL,       -- nacional | estadual | municipal
    regra         TEXT    NOT NULL,       -- fixa | pascoa | data
    dia           INTEGER,
    mes           INTEGER,
    deslocamento  INTEGER,                -- dias em relação ao domingo de Páscoa
    data          TEXT,                   -- regra "data": ocorre só nesta data
    ativo         INTEGER NOT NULL DEFAULT 1,
    observacao    TEXT
);

CREATE TABLE IF NOT EXISTS feriado_transferencias (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    feriado_id  INTEGER NOT NULL REFERENCES feriados(id) ON DELETE CASCADE,
    ano         INTEGER NOT NULL,
    nova_data   TEXT    NOT NULL,
    ato         TEXT,                     -- ex.: Decreto municipal nº 123/2026
    UNIQUE (feriado_id, ano)
);

CREATE TABLE IF NOT EXISTS recursos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    licitacao_id        INTEGER NOT NULL REFERENCES licitacoes(id) ON DELETE CASCADE,
    intimado_em         TEXT    NOT NULL,   -- intimação ou lavratura da ata
    notificado_em       TEXT,               -- notificação das empresas sobre o recurso
    recorrentes         TEXT,               -- não usado (mantido por compatibilidade)
    razoes_ate          TEXT    NOT NULL,
    contrarrazoes_ate   TEXT    NOT NULL,
    reconsideracao_ate  TEXT    NOT NULL,
    decisao_ate         TEXT    NOT NULL,   -- estimado: depende do recebimento dos autos
    status_anterior     TEXT,
    decidido_em         TEXT,
    resultado           TEXT,
    observacao          TEXT
);

CREATE TABLE IF NOT EXISTS historico (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    licitacao_id  INTEGER REFERENCES licitacoes(id) ON DELETE SET NULL,
    usuario_id    INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    acao          TEXT    NOT NULL,
    referencia    TEXT,
    detalhes      TEXT,
    data          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_historico_licitacao ON historico(licitacao_id);
"""


# Com vários usuários ao mesmo tempo, quem grava espera a gravação do outro terminar
# (até 15 s) em vez de receber erro de banco ocupado.
ESPERA_BANCO_OCUPADO = 15


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=ESPERA_BANCO_OCUPADO)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# Colunas acrescentadas depois da primeira versão: bancos já em uso as recebem na partida.
COLUNAS_NOVAS = {
    "licitacoes": {
        "membro3_id": "INTEGER REFERENCES servidores(id) ON DELETE SET NULL",
        "ocorrencia": "TEXT",
        "impedimentos_mantidos": "TEXT",
        "prazo_hipotese": "TEXT",
        "retificado_em": "TEXT",
        "versao": "INTEGER NOT NULL DEFAULT 0",
    },
    "modalidades": {
        "prazo_padrao": "TEXT NOT NULL DEFAULT 'nao_se_aplica'",
        "prazos_permitidos": "TEXT NOT NULL DEFAULT 'nao_se_aplica'",
    },
    "situacoes": {
        "whatsapp": "INTEGER NOT NULL DEFAULT 0",
    },
    "recursos": {
        "notificado_em": "TEXT",
    },
    "usuarios": {
        "preferencias": "TEXT",
        "login_cifrado": "TEXT",
        "senha_anterior_hash": "TEXT",
    },
}


def _semear_parametros(conn):
    """Valores iniciais de modalidades, situações, permissões e nome do órgão."""
    if not conn.execute("SELECT 1 FROM modalidades LIMIT 1").fetchone():
        for ordem, (nome, sigla, cor, cred, equipe, condutor, prazo, permitidos) in enumerate(
                perfis.MODALIDADES_PADRAO):
            conn.execute(
                "INSERT INTO modalidades (nome, sigla, cor, ordem, credenciamento, exige_equipe,"
                " rotulo_condutor, prazo_padrao, prazos_permitidos)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (nome, sigla, cor, ordem, cred, equipe, condutor, prazo, permitidos),
            )
    if not conn.execute("SELECT 1 FROM situacoes LIMIT 1").fetchone():
        for ordem, (chave, nome, cor, fase, sistema) in enumerate(perfis.SITUACOES_PADRAO):
            conn.execute(
                "INSERT INTO situacoes (chave, nome, cor, fase, ordem, sistema, whatsapp)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (chave, nome, cor, fase, ordem, sistema,
                 int(fase in perfis.FASES_DIVULGAVEIS)),
            )
    if not conn.execute("SELECT 1 FROM permissoes LIMIT 1").fetchone():
        for perfil, permissoes in perfis.PERMISSOES_PADRAO.items():
            for permissao in permissoes:
                conn.execute("INSERT INTO permissoes VALUES (?, ?)", (perfil, permissao))
    if not conn.execute("SELECT 1 FROM feriados LIMIT 1").fetchone():
        conn.executemany(
            "INSERT INTO feriados (nome, tipo, abrangencia, regra, dia, mes, deslocamento,"
            " observacao) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", perfis.FERIADOS_PADRAO)
    conn.execute(
        "INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES ('nome_orgao', ?)",
        (current_app.config.get("NOME_ORGAO", "Secretaria"),),
    )


def _migrar_para_parametros(conn):
    """Bancos da versão anterior: situação por nome, edital com sigla, perfil 'operador'."""
    nomes = {nome: chave for chave, nome, *_ in perfis.SITUACOES_PADRAO}
    for nome, chave in nomes.items():
        conn.execute("UPDATE licitacoes SET status = ? WHERE status = ?", (chave, nome))
    conn.execute("UPDATE usuarios SET perfil = 'pregoeiro' WHERE perfil = 'operador'")
    # O edital passa a ser só o número; a sigla vem da modalidade nas visualizações.
    for id_, numero in conn.execute(
            "SELECT id, numero_edital FROM licitacoes WHERE numero_edital IS NOT NULL").fetchall():
        limpo = re.sub(r"^[A-Za-zÀ-ú]+\s*", "", numero).strip()
        if limpo != numero:
            conn.execute("UPDATE licitacoes SET numero_edital = ? WHERE id = ?", (limpo, id_))


def _migrar_para_prazos(conn):
    """Prazo padrão das modalidades já cadastradas e nova permissão de feriados."""
    for nome, *_, prazo, _permitidos in perfis.MODALIDADES_PADRAO:
        conn.execute("UPDATE modalidades SET prazo_padrao = ? WHERE nome = ?"
                     " AND prazo_padrao = 'nao_se_aplica'", (prazo, nome))
    conn.execute("INSERT OR IGNORE INTO permissoes VALUES ('gestor', 'feriados')")


def _migrar_para_recursos(conn):
    """Critério de julgamento por modalidade, situação "Em recurso", filtro do WhatsApp e
    ajustes nos feriados (terça de Carnaval e Dia do Servidor como feriado; emancipação de
    Três Rios em 14/12)."""
    for nome, *_, prazo, permitidos in perfis.MODALIDADES_PADRAO:
        conn.execute("UPDATE modalidades SET prazos_permitidos = ? WHERE nome = ?"
                     " AND prazos_permitidos = 'nao_se_aplica'", (permitidos, nome))
    conn.execute("UPDATE modalidades SET prazos_permitidos = prazo_padrao"
                 " WHERE prazos_permitidos = 'nao_se_aplica'")
    if not conn.execute("SELECT 1 FROM situacoes WHERE chave = 'recurso'").fetchone():
        ordem = conn.execute("SELECT ordem FROM situacoes WHERE chave = 'andamento'").fetchone()
        conn.execute("INSERT INTO situacoes (chave, nome, cor, fase, ordem, sistema)"
                     " VALUES ('recurso', 'Em recurso', '#c2410c', 'andamento', ?, 1)",
                     ((ordem[0] if ordem else 0),))
    marcadores = ",".join("?" * len(perfis.FASES_DIVULGAVEIS))
    conn.execute(f"UPDATE situacoes SET whatsapp = 1 WHERE fase IN ({marcadores})",
                 perfis.FASES_DIVULGAVEIS)
    conn.execute("INSERT OR IGNORE INTO permissoes SELECT perfil, 'recursos' FROM permissoes"
                 " WHERE permissao = 'suspender'")
    conn.execute("UPDATE feriados SET tipo = 'feriado', observacao = 'Considerado feriado na"
                 " secretaria' WHERE nome IN ('Carnaval (terça-feira)', 'Dia do Servidor Público')"
                 " AND tipo = 'ponto_facultativo'")
    conn.execute("UPDATE feriados SET dia = 14, observacao = 'Feriado municipal de Três Rios;"
                 " normalmente transferido — registre a transferência a cada ano'"
                 " WHERE nome = 'Emancipação de Três Rios' AND dia = 26 AND mes = 12")


ACOES_DE_USUARIO = ("Login", "Troca de senha", "Cadastro de usuário", "Alteração de usuário",
                    "Redefinição de senha", "Configuração inicial: administrador criado")


def _migrar_para_logins_cifrados(conn):
    """Logins deixam de ficar abertos no banco: cifrados, mais o índice para a busca."""
    for id_, login, nome in conn.execute(
            "SELECT id, login, nome FROM usuarios WHERE login_cifrado IS NULL").fetchall():
        conn.execute("UPDATE usuarios SET login = ?, login_cifrado = ? WHERE id = ?",
                     (cripto.indice_login(login), cripto.cifrar_login(login), id_))
        # A trilha de auditoria passa a identificar o usuário pelo nome.
        conn.execute("UPDATE historico SET referencia = ? WHERE referencia = ? AND acao IN"
                     f" ({','.join('?' * len(ACOES_DE_USUARIO))})",
                     (nome, login, *ACOES_DE_USUARIO))


# Migrações de dados, aplicadas uma única vez (controle por PRAGMA user_version).
MIGRACOES = [_migrar_para_parametros, _migrar_para_prazos, _migrar_para_recursos,
             _migrar_para_logins_cifrados]


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    for tabela, colunas in COLUNAS_NOVAS.items():
        existentes = {c["name"] for c in conn.execute(f"PRAGMA table_info({tabela})")}
        for nome, tipo in colunas.items():
            if nome not in existentes:
                conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}")
    # Cada alteração da licitação incrementa "versao": é assim que a edição percebe que
    # outro usuário salvou a mesma licitação enquanto ela estava aberta.
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS licitacoes_versao AFTER UPDATE ON licitacoes
        FOR EACH ROW WHEN NEW.versao = OLD.versao
        BEGIN
            UPDATE licitacoes SET versao = OLD.versao + 1 WHERE id = NEW.id;
        END""")
    _semear_parametros(conn)
    versao = conn.execute("PRAGMA user_version").fetchone()[0]
    for numero, migracao in enumerate(MIGRACOES, start=1):
        if versao < numero:
            migracao(conn)
            conn.execute(f"PRAGMA user_version = {numero}")
    conn.commit()


def registrar(acao, referencia=None, detalhes=None, licitacao_id=None):
    """Grava uma entrada na trilha de auditoria (sem commit)."""
    usuario = g.get("usuario")
    get_db().execute(
        "INSERT INTO historico (licitacao_id, usuario_id, acao, referencia, detalhes)"
        " VALUES (?, ?, ?, ?, ?)",
        (licitacao_id, usuario["id"] if usuario else None, acao, referencia, detalhes),
    )
