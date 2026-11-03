"""Cópia do banco numa pasta sincronizada com a nuvem (ex.: Google Drive) e trava que impede
dois computadores de servirem a agenda ao mesmo tempo.

O banco em uso fica sempre no disco do computador anfitrião: o Google Drive não trava
arquivos entre computadores e, se sincronizasse no meio de uma gravação, levaria um banco
corrompido para a nuvem. Na pasta da nuvem vão só cópias completas e consistentes, feitas
pelo próprio SQLite, e a trava "anfitriao.json", renovada a cada minuto.

Se o anfitrião quebrar, outro computador com o programa instalado assume: quando a trava
fica sem renovação por TRAVA_VENCIDA, ele restaura a última cópia da nuvem e passa a servir.
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

BANCO = "licitacoes.sqlite3"
BRASAO = "brasao.png"
TRAVA = "anfitriao.json"
SOBRE_A_COPIA = "copia.json"
COPIAS_DIARIAS = "copias-diarias"
DIAS_DE_COPIAS = 30
RENOVAR_TRAVA = 60           # segundos
TRAVA_VENCIDA = 10 * 60      # segundos sem renovação: o anfitrião é dado como desligado


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


def _gravar_json(caminho, dados):
    temporario = caminho + ".tmp"
    with open(temporario, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=1)
    os.replace(temporario, caminho)


def _copiar_banco(origem, destino):
    """Cópia consistente mesmo com usuários gravando (API de backup do SQLite)."""
    temporario = destino + ".tmp"
    if os.path.exists(temporario):
        os.remove(temporario)
    fonte = sqlite3.connect(origem, timeout=15)
    try:
        copia = sqlite3.connect(temporario)
        try:
            fonte.backup(copia)
        finally:
            copia.close()
    finally:
        fonte.close()
    os.replace(temporario, destino)


class CopiaNuvem:
    def __init__(self, pasta_nuvem, pasta_dados, minutos=5, computador=None):
        self.pasta = os.path.abspath(pasta_nuvem)
        self.dados = pasta_dados
        self.intervalo = max(1, int(minutos)) * 60
        self.computador = computador or socket.gethostname()
        self.instancia = uuid.uuid4().hex
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
        return os.path.join(self.dados, BANCO)

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

    # --- restauração -----------------------------------------------------------------

    def restaurar_se_preciso(self):
        """Traz a cópia da nuvem quando ela é mais nova que o banco deste computador:
        quando ele não tem banco ou quando a última cópia foi feita por outro anfitrião.
        O banco local anterior é guardado ao lado, com a data no nome. Devolve uma
        mensagem ou None."""
        copia = self._na_nuvem(BANCO)
        if not os.path.exists(copia):
            return None
        sobre = _ler_json(self._na_nuvem(SOBRE_A_COPIA)) or {}
        local_existe = os.path.exists(self.banco_local)
        if local_existe and sobre.get("computador", "").lower() == self.computador.lower():
            return None  # a última cópia saiu daqui: o banco local é o mais novo
        os.makedirs(self.dados, exist_ok=True)
        conn = sqlite3.connect(copia)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("a cópia da nuvem está danificada")
        finally:
            conn.close()
        if local_existe:
            carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
            os.replace(self.banco_local,
                       os.path.join(self.dados, f"licitacoes.anterior-{carimbo}.sqlite3"))
        _copiar_banco(copia, self.banco_local)
        brasao = self._na_nuvem(BRASAO)
        if os.path.exists(brasao):
            shutil.copyfile(brasao, os.path.join(self.dados, BRASAO))
        return (f"Banco restaurado da nuvem (cópia de {sobre.get('feita_em', '?')}, "
                f"feita pelo computador {sobre.get('computador', '?')}).")

    # --- cópia -----------------------------------------------------------------------

    def _assinatura_atual(self):
        return tuple((os.path.getmtime(c), os.path.getsize(c))
                     for c in (self.banco_local, os.path.join(self.dados, BRASAO))
                     if os.path.exists(c))

    def copiar(self, forcar=False):
        """Envia o banco (e o brasão) para a nuvem, se mudaram desde a última cópia."""
        if self.perdeu_a_vez:
            return False
        try:
            assinatura = self._assinatura_atual()
            if not forcar and assinatura == self._assinatura \
                    and os.path.exists(self._na_nuvem(BANCO)):
                return False
            os.makedirs(self.pasta, exist_ok=True)
            _copiar_banco(self.banco_local, self._na_nuvem(BANCO))
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
        destino = os.path.join(pasta, f"licitacoes-{date.today().isoformat()}.sqlite3")
        if not os.path.exists(destino):
            shutil.copyfile(self._na_nuvem(BANCO), destino)
        antigas = sorted(n for n in os.listdir(pasta)
                         if n.startswith("licitacoes-") and n.endswith(".sqlite3"))
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
