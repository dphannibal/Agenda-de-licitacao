"""Descoberta do servidor na rede local.

O programa dos usuários (cliente/agenda_usuario.py) envia por UDP a pergunta PERGUNTA para a
rede; o servidor responde com o endereço em que atende. Assim os usuários não precisam
saber o endereço, e ele continua certo se outro computador assumir a agenda.
"""
import json
import socket
import threading

# Os mesmos valores estão em cliente/agenda_usuario.py.
PORTA = 8081
PERGUNTA = b"AGENDA-LICITACOES?"
RESPOSTA = b"AGENDA-LICITACOES "


def ignorar_porta_fechada(sock):
    """No Windows, uma resposta UDP a quem já fechou a porta faz a próxima leitura falhar
    com "conexão reiniciada"; isto desliga esse aviso."""
    if hasattr(socket, "SIO_UDP_CONNRESET"):
        sock.ioctl(socket.SIO_UDP_CONNRESET, False)


def _ip_para(destino):
    """IP deste computador na rede por onde se chega a ``destino``."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(destino)
        return s.getsockname()[0]


def responder(url, porta_web, versao, ativo=lambda: True, porta=PORTA):
    """Responde às perguntas dos usuários numa linha de execução separada. ``ativo`` diz se
    este computador ainda é o anfitrião (com a cópia na nuvem, ele pode perder a vez).
    Devolve o soquete (para encerrar) ou None se a porta estiver ocupada."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("0.0.0.0", porta))
    except OSError as erro:
        sock.close()
        print(f"Descoberta automática indisponível (porta UDP {porta}): {erro}")
        return None
    ignorar_porta_fechada(sock)

    def atender():
        while True:
            try:
                pergunta, origem = sock.recvfrom(512)
            except ConnectionResetError:
                continue  # aviso de uma resposta anterior que não foi entregue
            except OSError:
                return  # soquete fechado
            if pergunta.strip() != PERGUNTA or not ativo():
                continue
            sufixo = "" if porta_web == 80 else f":{porta_web}"
            try:
                url_ip = f"http://{_ip_para(origem)}{sufixo}/"
            except OSError:
                url_ip = None
            dados = {"url": url, "url_ip": url_ip, "versao": versao}
            try:
                sock.sendto(RESPOSTA + json.dumps(dados).encode(), origem)
            except OSError:
                pass

    threading.Thread(target=atender, name="descoberta", daemon=True).start()
    return sock
