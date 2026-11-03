"""Cópia do banco numa pasta sincronizada com a nuvem (ex.: Google Drive) e trava que impede
dois computadores de servirem a agenda ao mesmo tempo.

O banco em uso fica sempre no disco do computador anfitrião: o Google Drive não trava
arquivos entre computadores e, se sincronizasse no meio de uma gravação, levaria um banco
corrompido para a nuvem. Na pasta da nuvem vão só cópias completas e consistentes, feitas
pelo próprio SQLite e criptografadas com a chave dos dados (cripto.py), e a trava
"anfitriao.json", renovada a cada minuto.

A chave vai para a nuvem embrulhada com a senha de recuperação ("chave.json"). Enquanto o
administrador não define essa senha, nenhuma cópia é enviada.

Se o anfitrião quebrar, outro computador com o programa instalado assume: quando a trava
fica sem renovação por TRAVA_VENCIDA, ele pede a senha de recuperação (no próprio
computador), restaura a última cópia da nuvem e passa a servir.
"""
import json
import os
import shutil
import socket
import sqlite3
import threading
import time
import uuid
from datetime import date, datetime

from . import cripto

BANCO_LOCAL = "licitacoes.sqlite3"
BANCO = "licitacoes.cifrado"
BRASAO = "brasao.png"
TRAVA = "anfitriao.json"
CHAVE = "chave.json"
SOBRE_A_COPIA = "copia.json"
COPIAS_DIARIAS = "copias-diarias"
DIAS_DE_COPIAS = 30
RENOVAR_TRAVA = 60           # segundos
TRAVA_VENCIDA = 10 * 60      # segundos sem renovação: o anfitrião é dado como desligado
CABECALHO = b"AGENDA-LICITACOES-CIFRADO-1\n"

# Situações da chave (atributo "estado"):
SEM_SENHA = "sem_senha"                  # nuvem sem chave.json: falta a senha de recuperação
PRONTA = "pronta"                        # a chave deste computador é a da nuvem
AGUARDANDO = "aguardando_recuperacao"    # a nuvem tem outra chave: falta informar a senha


class OutroAnfitriao(Exception):
    """Outro computador está servindo a agenda com esta pasta da nuvem."""


def _agora():
    return datetime.now().strftime("%d/%m/%Y %H:%M")


def _ler_json(caminho):
    try:
        with open(caminho, encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except (OSError, ValueError):
        return None


def _gravar(caminho, conteudo):
    temporario = caminho + ".tmp"
    with open(temporario, "wb") as arquivo:
        arquivo.write(conteudo)
    os.replace(temporario, caminho)


def _gravar_json(caminho, dados):
    _gravar(caminho, json.dumps(dados, ensure_ascii=False, indent=1).encode("utf-8"))


def _ler_banco(caminho):
    """Conteúdo do banco, copiado de forma consistente mesmo com usuários gravando."""
    temporario = caminho + ".copia"
    if os.path.exists(temporario):
        os.remove(temporario)
    fonte = sqlite3.connect(caminho, timeout=15)
    try:
        copia = sqlite3.connect(temporario)
        try:
            fonte.backup(copia)
        finally:
            copia.close()
    finally:
        fonte.close()
    try:
        with open(temporario, "rb") as arquivo:
            return arquivo.read()
    finally:
        os.remove(temporario)


class CopiaNuvem:
    def __init__(self, pasta_nuvem, pasta_dados, minutos=5, computador=None):
        self.pasta = os.path.abspath(pasta_nuvem)
        self.dados = pasta_dados
        self.intervalo = max(1, int(minutos)) * 60
        self.computador = computador or socket.gethostname()
        self.instancia = uuid.uuid4().hex
        self.estado = SEM_SENHA
        self.ultima_copia = None     # "dd/mm/aaaa hh:mm" da última cópia enviada
        self.ultimo_erro = None      # "dd/mm/aaaa hh:mm — mensagem"
        self.perdeu_a_vez = False    # outro computador assumiu: não copia mais
        self.endereco = None         # endereço dos usuários, gravado na trava
        self._assinatura = None
        self._parar = threading.Event()
        self._fio = None
        self._trava_lock = threading.Lock()

    @property
    def banco_local(self):
        return os.path.join(self.dados, BANCO_LOCAL)

    def _na_nuvem(self, *partes):
        return os.path.join(self.pasta, *partes)

    def _erro(self, texto):
        self.ultimo_erro = f"{_agora()} — {texto}"
        print(f"Cópia na nuvem: {texto}")

    # --- trava -----------------------------------------------------------------------

    def anfitriao_ativo(self):
        """Dados da trava de OUTRO computador ainda em uso, ou None."""
        trava = _ler_json(self._na_nuvem(TRAVA))
        if not trava or trava.get("instancia") == self.instancia:
            return None
        if trava.get("computador", "").lower() == self.computador.lower():
            return None  # este mesmo computador, reiniciado: pode retomar
        if time.time() - float(trava.get("renovada", 0)) > TRAVA_VENCIDA:
            return None
        return trava

    def assumir(self):
        """Assume a vez de anfitrião ou levanta OutroAnfitriao."""
        os.makedirs(self.pasta, exist_ok=True)
        outro = self.anfitriao_ativo()
        if outro:
            raise OutroAnfitriao(
                f"A agenda já está sendo servida pelo computador {outro.get('computador')} "
                f"(endereço {outro.get('endereco', '?')}). Use esse endereço no navegador. "
                f"Se aquele computador foi desligado ou quebrou, este poderá assumir "
                f"{TRAVA_VENCIDA // 60} minutos depois.")
        self._renovar_trava()

    def _renovar_trava(self, endereco=None):
        with self._trava_lock:
            atual = _ler_json(self._na_nuvem(TRAVA)) or {}
            if atual.get("instancia") not in (None, self.instancia) and self.anfitriao_ativo():
                if not self.perdeu_a_vez:
                    self.perdeu_a_vez = True
                    self._erro(f"o computador {atual.get('computador')} assumiu a agenda; "
                               "este computador parou de enviar cópias. Encerre o programa "
                               "aqui para não haver dois anfitriões.")
                return
            if endereco:
                self.endereco = endereco
            _gravar_json(self._na_nuvem(TRAVA), {
                "computador": self.computador, "instancia": self.instancia,
                "endereco": self.endereco, "renovada": time.time(),
                "renovada_em": _agora(),
            })

    def liberar(self):
        with self._trava_lock:
            trava = _ler_json(self._na_nuvem(TRAVA))
            if trava and trava.get("instancia") == self.instancia:
                os.remove(self._na_nuvem(TRAVA))

    # --- chave e senha de recuperação ----------------------------------------------------

    def _chave_local(self):
        if not os.path.exists(os.path.join(self.dados, cripto.ARQUIVO_CHAVE)):
            return None
        return cripto.carregar_chave(self.dados)

    def verificar_chave(self):
        """Compara a chave deste computador com a da nuvem e atualiza o estado."""
        embrulho = _ler_json(self._na_nuvem(CHAVE))
        if embrulho is None:
            self.estado = SEM_SENHA
        else:
            local = self._chave_local()
            iguais = local is not None and cripto.impressao(local) == embrulho.get("impressao")
            self.estado = PRONTA if iguais else AGUARDANDO
        return self.estado

    def definir_senha_recuperacao(self, senha):
        """Guarda na nuvem a chave deste computador, protegida pela senha de recuperação.
        Também serve para trocar a senha (as cópias antigas continuam abríveis)."""
        if self.estado == AGUARDANDO:
            raise ValueError("Informe antes a senha de recuperação das cópias já existentes.")
        os.makedirs(self.pasta, exist_ok=True)
        _gravar_json(self._na_nuvem(CHAVE), cripto.embrulhar(cripto.carregar_chave(self.dados),
                                                             senha))
        self.estado = PRONTA
        self.copiar(forcar=True)

    def recuperar(self, senha):
        """Traz da nuvem a chave (com a senha de recuperação) e a última cópia do banco.
        ValueError se a senha estiver errada."""
        chave = cripto.desembrulhar(_ler_json(self._na_nuvem(CHAVE)), senha)
        cripto.gravar_chave(self.dados, chave)
        self.estado = PRONTA
        return self.restaurar_se_preciso(forcar=True)

    # --- restauração -----------------------------------------------------------------

    def restaurar_se_preciso(self, forcar=False):
        """Traz a cópia da nuvem quando ela é mais nova que o banco deste computador:
        quando ele não tem banco ou quando a última cópia foi feita por outro anfitrião.
        O banco local anterior é guardado ao lado, com a data no nome. Devolve uma
        mensagem ou None."""
        copia = self._na_nuvem(BANCO)
        if self.estado != PRONTA or not os.path.exists(copia):
            return None
        sobre = _ler_json(self._na_nuvem(SOBRE_A_COPIA)) or {}
        local_existe = os.path.exists(self.banco_local)
        if not forcar and local_existe \
                and sobre.get("computador", "").lower() == self.computador.lower():
            return None  # a última cópia saiu daqui: o banco local é o mais novo
        self.restaurar_arquivo(copia)
        brasao = self._na_nuvem(BRASAO)
        if os.path.exists(brasao):
            shutil.copyfile(brasao, os.path.join(self.dados, BRASAO))
        return (f"Banco restaurado da nuvem (cópia de {sobre.get('feita_em', '?')}, "
                f"feita pelo computador {sobre.get('computador', '?')}).")

    def restaurar_arquivo(self, copia):
        """Substitui o banco deste computador por uma cópia cifrada (a última ou uma das
        cópias diárias). O banco anterior é guardado ao lado, com a data no nome."""
        local_existe = os.path.exists(self.banco_local)
        with open(copia, "rb") as arquivo:
            conteudo = arquivo.read()
        if not conteudo.startswith(CABECALHO):
            raise ValueError("a cópia da nuvem não está no formato esperado")
        try:
            banco = cripto.decifrar_bytes(conteudo[len(CABECALHO):], cripto.carregar_chave(
                self.dados), b"copia")
        except ValueError as erro:
            raise ValueError("a cópia da nuvem está danificada") from erro
        os.makedirs(self.dados, exist_ok=True)
        novo = self.banco_local + ".restaurado"
        _gravar(novo, banco)
        conn = sqlite3.connect(novo)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("a cópia da nuvem está danificada")
        finally:
            conn.close()
        if local_existe:
            carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
            os.replace(self.banco_local,
                       os.path.join(self.dados, f"licitacoes.anterior-{carimbo}.sqlite3"))
        os.replace(novo, self.banco_local)

    # --- cópia -----------------------------------------------------------------------

    def _assinatura_atual(self):
        return tuple((os.path.getmtime(c), os.path.getsize(c))
                     for c in (self.banco_local, os.path.join(self.dados, BRASAO))
                     if os.path.exists(c))

    def copiar(self, forcar=False):
        """Envia o banco cifrado (e o brasão) para a nuvem, se mudaram desde a última cópia."""
        if self.perdeu_a_vez or self.estado != PRONTA:
            return False
        try:
            assinatura = self._assinatura_atual()
            if not forcar and assinatura == self._assinatura \
                    and os.path.exists(self._na_nuvem(BANCO)):
                return False
            os.makedirs(self.pasta, exist_ok=True)
            cifrado = CABECALHO + cripto.cifrar_bytes(
                _ler_banco(self.banco_local), cripto.carregar_chave(self.dados), b"copia")
            _gravar(self._na_nuvem(BANCO), cifrado)
            brasao = os.path.join(self.dados, BRASAO)
            if os.path.exists(brasao):
                shutil.copyfile(brasao, self._na_nuvem(BRASAO))
            elif os.path.exists(self._na_nuvem(BRASAO)):
                os.remove(self._na_nuvem(BRASAO))
            _gravar_json(self._na_nuvem(SOBRE_A_COPIA),
                         {"computador": self.computador, "feita_em": _agora()})
            self._copia_do_dia()
            self._assinatura = assinatura
            self.ultima_copia = _agora()
            self.ultimo_erro = None
            return True
        except (OSError, sqlite3.Error) as erro:
            self._erro(f"falha ao copiar para {self.pasta}: {erro}")
            return False

    def _copia_do_dia(self):
        """Uma cópia por dia, guardadas por DIAS_DE_COPIAS dias."""
        pasta = self._na_nuvem(COPIAS_DIARIAS)
        os.makedirs(pasta, exist_ok=True)
        destino = os.path.join(pasta, f"licitacoes-{date.today().isoformat()}.cifrado")
        if not os.path.exists(destino):
            shutil.copyfile(self._na_nuvem(BANCO), destino)
        antigas = sorted(n for n in os.listdir(pasta)
                         if n.startswith("licitacoes-") and n.endswith(".cifrado"))
        for nome in antigas[:-DIAS_DE_COPIAS]:
            os.remove(os.path.join(pasta, nome))

    # --- funcionamento contínuo --------------------------------------------------------

    def iniciar(self, endereco=None):
        self._renovar_trava(endereco)
        self.copiar(forcar=True)
        self._fio = threading.Thread(target=self._rodar, name="copia-nuvem", daemon=True)
        self._fio.start()

    def _rodar(self):
        proxima_copia = time.monotonic() + self.intervalo
        while not self._parar.wait(RENOVAR_TRAVA):
            try:
                self._renovar_trava()
            except OSError as erro:
                self._erro(f"falha ao renovar a trava em {self.pasta}: {erro}")
            if time.monotonic() >= proxima_copia:
                self.copiar()
                proxima_copia = time.monotonic() + self.intervalo

    def encerrar(self):
        self._parar.set()
        if self._fio:
            self._fio.join(timeout=5)
        self.copiar()
        try:
            self.liberar()
        except OSError:
            pass
