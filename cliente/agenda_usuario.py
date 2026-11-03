"""Agenda de Licitações — programa dos usuários.

Acha o servidor da agenda e abre o sistema no navegador padrão. Não guarda dados: só o
último endereço que funcionou. Ordem de tentativas:

1. o último endereço que funcionou;
2. pergunta na rede local (o servidor responde com o endereço dele);
3. o atalho "Abrir Agenda de Licitações.url" da pasta compartilhada do servidor, de onde
   este programa foi instalado (para redes em que a pergunta não chega).

Usa só a biblioteca padrão do Python, para o executável ficar pequeno.
"""
import argparse
import configparser
import json
import os
import socket
import sys
import time
import urllib.request
import webbrowser

# Os mesmos valores estão em licitacoes/descoberta.py.
PORTA_DESCOBERTA = 8081
PERGUNTA = b"AGENDA-LICITACOES?"
RESPOSTA = b"AGENDA-LICITACOES "
ESPERA_RESPOSTA = 2.0       # segundos
ESPERA_SERVIDOR = 3.0       # segundos
NOME_ATALHO = "Abrir Agenda de Licitações.url"
TITULO = "Agenda de Licitações"

PASTA_CONFIG = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                            "AgendaLicitacoes")
ARQUIVO_CONFIG = os.path.join(PASTA_CONFIG, "usuario.json")


def ler_config():
    try:
        with open(ARQUIVO_CONFIG, encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except (OSError, ValueError):
        return {}


def gravar_config(config):
    os.makedirs(PASTA_CONFIG, exist_ok=True)
    with open(ARQUIVO_CONFIG, "w", encoding="utf-8") as arquivo:
        json.dump(config, arquivo, ensure_ascii=False, indent=1)


# O servidor está na rede interna: um proxy configurado no Windows não deve se meter.
SEM_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def e_a_agenda(url):
    """O endereço responde e é mesmo a Agenda de Licitações?"""
    if not url or not url.startswith(("http://", "https://")):
        return False
    try:
        with SEM_PROXY.open(url.rstrip("/") + "/agenda-licitacoes.json",
                            timeout=ESPERA_SERVIDOR) as resposta:
            return json.load(resposta).get("sistema") == "agenda-licitacoes"
    except (OSError, ValueError):
        return False


def _destinos():
    """Para onde enviar a pergunta: a rede toda, as sub-redes deste computador e ele mesmo."""
    destinos = {"255.255.255.255", "127.0.0.1"}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                destinos.add(ip.rsplit(".", 1)[0] + ".255")
    except OSError:
        pass
    return destinos


def perguntar_na_rede():
    """Endereços oferecidos pelo primeiro servidor que responder (lista vazia se nenhum)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        if hasattr(socket, "SIO_UDP_CONNRESET"):  # Windows: ver licitacoes/descoberta.py
            sock.ioctl(socket.SIO_UDP_CONNRESET, False)
        for destino in _destinos():
            try:
                sock.sendto(PERGUNTA, (destino, PORTA_DESCOBERTA))
            except OSError:
                pass
        limite = time.monotonic() + ESPERA_RESPOSTA
        while (restante := limite - time.monotonic()) > 0:
            sock.settimeout(restante)
            try:
                resposta, _origem = sock.recvfrom(2048)
            except ConnectionResetError:
                continue
            except OSError:
                break
            if resposta.startswith(RESPOSTA):
                try:
                    dados = json.loads(resposta[len(RESPOSTA):])
                except ValueError:
                    continue
                return [u for u in (dados.get("url"), dados.get("url_ip")) if u]
    return []


def endereco_do_atalho(pasta):
    """URL do atalho que o servidor mantém na pasta compartilhada."""
    if not pasta:
        return None
    leitor = configparser.ConfigParser(interpolation=None)
    try:
        leitor.read(os.path.join(pasta, NOME_ATALHO), encoding="utf-8")
        return leitor.get("InternetShortcut", "URL", fallback=None)
    except (OSError, configparser.Error):
        return None


def descobrir(config):
    candidatos = [config.get("ultimo_endereco")]
    candidatos += perguntar_na_rede()
    candidatos.append(endereco_do_atalho(config.get("pasta_servidor")))
    for url in candidatos:
        if e_a_agenda(url):
            return url
    return None


def avisar(texto):
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, texto, TITULO, 0x30)  # ícone de atenção
    except (ImportError, AttributeError, OSError):
        print(texto, file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=TITULO)
    parser.add_argument("--pasta-servidor", help="Pasta compartilhada do servidor (gravada "
                                                 "pelo instalador)")
    parser.add_argument("--descobrir", metavar="ARQUIVO",
                        help="Só descobre o endereço e o grava no arquivo (para testes)")
    args = parser.parse_args()

    config = ler_config()
    if args.pasta_servidor:
        config["pasta_servidor"] = args.pasta_servidor
        gravar_config(config)
        return

    url = descobrir(config)
    if args.descobrir:
        with open(args.descobrir, "w", encoding="utf-8") as saida:
            saida.write(url or "")
        sys.exit(0 if url else 1)
    if not url:
        avisar("O servidor da Agenda de Licitações não foi encontrado na rede.\n\n"
               "Verifique se o computador servidor está ligado e se este computador está "
               "conectado à rede da secretaria. Se o problema continuar, procure o "
               "administrador do sistema.")
        sys.exit(1)
    if url != config.get("ultimo_endereco"):
        config["ultimo_endereco"] = url
        try:
            gravar_config(config)
        except OSError:
            pass
    webbrowser.open(url)


if __name__ == "__main__":
    main()
