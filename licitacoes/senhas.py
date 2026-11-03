"""Regras das senhas pessoais: tamanho mínimo, nada fácil de adivinhar e sem repetir a anterior."""
import re
import unicodedata

from werkzeug.security import check_password_hash

TAMANHO_MINIMO = 8

# Senhas que aparecem no topo das listas de senhas vazadas.
COMUNS = {
    "12345678", "123456789", "1234567890", "0123456789", "87654321", "98765432", "11111111",
    "00000000", "12121212", "11223344", "12344321", "123123123", "12341234", "123qwe123",
    "1q2w3e4r", "1q2w3e4r5t", "q1w2e3r4", "qwer1234", "qwerty123", "abc12345", "abcd1234",
    "a1b2c3d4", "1a2b3c4d", "zaq12wsx", "asdf1234", "senha123", "mudar123", "trocar123",
}
# Palavras óbvias, que não ficam seguras só com números ou símbolos antes ou depois.
PALAVRAS = {
    "senha", "password", "admin", "administrador", "usuario", "teste", "acesso",
    "entrar", "mudar", "trocar", "mudarsenha", "novasenha", "bemvindo", "welcome", "qwerty",
    "asdf", "abc", "abcd", "abcde", "abcdef", "iloveyou", "teamo", "amor", "deus", "jesus",
    "familia", "brasil", "riodejaneiro", "tresrios", "prefeitura",
    "secretaria", "municipio", "licitacao", "licitacoes", "pregao", "pregoeiro", "compras",
    "contratacao", "agenda", "flamengo", "vasco", "fluminense", "botafogo", "corinthians",
    "palmeiras", "saopaulo", "gremio", "cruzeiro",
}
SEQUENCIAS = ("01234567890", "abcdefghijklmnopqrstuvwxyz", "qwertyuiop", "asdfghjkl",
              "zxcvbnm", "qazwsxedcrfvtgbyhnujmikolp")
TROCAS = str.maketrans("@4310$5!7", "aaeiossit")


def _simples(texto):
    """Sem acentos e em minúsculas."""
    texto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def _sequencia(texto):
    """Repetição de poucos caracteres ou trecho seguido do teclado/alfabeto/números."""
    if len(set(texto)) <= 3:
        return True
    return any(texto in s or texto in s[::-1] for s in SEQUENCIAS)


def problema(senha, login="", nome="", anteriores=()):
    """Motivo para recusar a senha, ou None se ela puder ser usada. ``anteriores`` são os
    hashes da senha atual e da usada antes dela."""
    if len(senha) < TAMANHO_MINIMO:
        return f"A senha deve ter ao menos {TAMANHO_MINIMO} caracteres."
    simples = _simples(senha)
    if not re.search(r"[a-z]", simples) or not re.search(r"[^a-z]", simples):
        return "Use letras e também números ou símbolos."
    # Tira números e símbolos das pontas e desfaz trocas como @→a e 3→e: "S3nh@2026" → "senha".
    miolos = {re.sub(r"^[^a-z]+|[^a-z]+$", "", simples).translate(TROCAS),
              re.sub(r"^[^a-z@$!]+|[^a-z@$!]+$", "", simples).translate(TROCAS)}
    sem_simbolos = re.sub(r"[^a-z0-9]", "", simples)
    if simples in COMUNS or sem_simbolos in COMUNS or miolos & PALAVRAS \
            or _sequencia(sem_simbolos) or any(_sequencia(m) for m in miolos):
        return "Senha fácil de adivinhar. Evite palavras óbvias e sequências como 12345678."
    for parte in [login] + re.split(r"\s+", nome):
        parte = _simples(parte.strip())
        if len(parte) >= 3 and (parte in simples or any(parte in m for m in miolos)):
            return "A senha não pode conter o seu login nem o seu nome."
    if any(h and check_password_hash(h, senha) for h in anteriores):
        return "Essa senha já foi usada. Escolha uma senha diferente da atual e da anterior."
    return None
