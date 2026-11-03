"""Chave dos dados: cifra os logins no banco e as cópias enviadas à nuvem.

A chave (32 bytes aleatórios) fica no arquivo "chave_dados" da pasta de dados, que só
administradores do Windows acessam. Para a nuvem ela vai embrulhada com a senha de
recuperação: quem invadir a pasta do Google Drive não consegue abrir as cópias, e outro
computador só restaura a agenda com essa senha.

Os logins ficam no banco de duas formas: cifrados (AES-GCM), para serem mostrados na tela,
e como um índice HMAC, para o login ser encontrado sem decifrar todos.
"""
import base64
import hashlib
import hmac
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import current_app

ARQUIVO_CHAVE = "chave_dados"
# Custo da derivação da senha de recuperação (scrypt, ~32 MB de memória por tentativa).
SCRYPT = {"n": 2 ** 15, "r": 8, "p": 1}


def carregar_chave(pasta):
    """Lê a chave da pasta de dados, gerando-a (uma única vez) se ainda não existir."""
    caminho = os.path.join(pasta, ARQUIVO_CHAVE)
    if not os.path.exists(caminho):
        gravar_chave(pasta, os.urandom(32))
    with open(caminho, encoding="ascii") as arquivo:
        return base64.b64decode(arquivo.read().strip())


def gravar_chave(pasta, chave):
    caminho = os.path.join(pasta, ARQUIVO_CHAVE)
    with open(caminho + ".tmp", "w", encoding="ascii") as arquivo:
        arquivo.write(base64.b64encode(chave).decode())
    os.replace(caminho + ".tmp", caminho)


def _chave(chave=None):
    return chave or current_app.config["CHAVE_DADOS"]


def impressao(chave):
    """Identifica a chave sem revelá-la (para saber se duas cópias usam a mesma)."""
    return hmac.new(chave, b"impressao", hashlib.sha256).hexdigest()[:16]


def cifrar_bytes(dados, chave, contexto):
    nonce = os.urandom(12)
    return nonce + AESGCM(chave).encrypt(nonce, dados, contexto)


def decifrar_bytes(dados, chave, contexto):
    """ValueError se a chave estiver errada ou o conteúdo tiver sido alterado."""
    try:
        return AESGCM(chave).decrypt(dados[:12], dados[12:], contexto)
    except InvalidTag as erro:
        raise ValueError("chave incorreta ou conteúdo danificado") from erro


# --- logins -------------------------------------------------------------------------------

def indice_login(login, chave=None):
    """Valor guardado na coluna "login": permite a busca sem guardar o login aberto.
    Maiúsculas e minúsculas não importam, como antes."""
    texto = login.strip().lower().encode()
    return hmac.new(_chave(chave), b"login:" + texto, hashlib.sha256).hexdigest()


def cifrar_login(login, chave=None):
    return base64.b64encode(cifrar_bytes(login.strip().encode(), _chave(chave), b"login")).decode()


def decifrar_login(cifrado, chave=None):
    return decifrar_bytes(base64.b64decode(cifrado), _chave(chave), b"login").decode()


def com_login(usuario):
    """Dados do usuário (linha do banco) com o login decifrado, para as telas."""
    dados = dict(usuario)
    dados["login"] = decifrar_login(usuario["login_cifrado"])
    return dados


# --- senha de recuperação -------------------------------------------------------------------

def _derivar(senha, sal, n, r, p):
    return hashlib.scrypt(senha.encode(), salt=sal, n=n, r=r, p=p, maxmem=128 * r * n * 2,
                          dklen=32)


def embrulhar(chave, senha):
    """Chave protegida pela senha de recuperação, para guardar na nuvem."""
    sal = os.urandom(16)
    protegida = cifrar_bytes(chave, _derivar(senha, sal, **SCRYPT), b"chave")
    return {"versao": 1, "kdf": "scrypt", **SCRYPT,
            "sal": base64.b64encode(sal).decode(),
            "chave": base64.b64encode(protegida).decode(),
            "impressao": impressao(chave)}


def desembrulhar(embrulho, senha):
    """A chave dos dados, ou ValueError se a senha de recuperação estiver errada."""
    derivada = _derivar(senha, base64.b64decode(embrulho["sal"]),
                        embrulho["n"], embrulho["r"], embrulho["p"])
    try:
        return decifrar_bytes(base64.b64decode(embrulho["chave"]), derivada, b"chave")
    except ValueError as erro:
        raise ValueError("Senha de recuperação incorreta.") from erro
