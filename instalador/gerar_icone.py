"""Gera o ícone dos programas (instalador/icone.ico).

Se existir instalador/brasao.png (o brasão do município), ele vira o ícone, centralizado num
quadrado transparente. Sem ele, desenha um ícone provisório: uma folha de calendário.
Usado pelo GitHub Actions antes de empacotar; à mão: python instalador/gerar_icone.py
"""
import os

from PIL import Image, ImageDraw

PASTA = os.path.dirname(os.path.abspath(__file__))
BRASAO = os.path.join(PASTA, "brasao.png")
ICONE = os.path.join(PASTA, "icone.ico")
TAMANHOS = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def do_brasao():
    with Image.open(BRASAO) as original:
        imagem = original.convert("RGBA")
    imagem.thumbnail((256, 256), Image.LANCZOS)
    quadro = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    quadro.paste(imagem, ((256 - imagem.width) // 2, (256 - imagem.height) // 2), imagem)
    return quadro


def provisorio():
    imagem = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(imagem)
    azul, vermelho, branco, cinza = "#1d4ed8", "#c2410c", "#ffffff", "#cbd5e1"
    d.rounded_rectangle((16, 28, 240, 240), radius=28, fill=branco, outline=azul, width=12)
    d.rounded_rectangle((16, 28, 240, 92), radius=28, fill=azul)
    d.rectangle((16, 64, 240, 92), fill=azul)
    for x in (72, 184):  # argolas
        d.rounded_rectangle((x - 10, 8, x + 10, 56), radius=10, fill=vermelho)
    for linha in range(3):
        for coluna in range(4):
            x, y = 44 + coluna * 46, 112 + linha * 40
            cor = vermelho if (linha, coluna) == (1, 2) else cinza
            d.rounded_rectangle((x, y, x + 30, y + 26), radius=6, fill=cor)
    return imagem


def main():
    imagem = do_brasao() if os.path.exists(BRASAO) else provisorio()
    imagem.save(ICONE, sizes=TAMANHOS)
    print(f"Ícone gerado em {ICONE} ({'brasão' if os.path.exists(BRASAO) else 'provisório'})")


if __name__ == "__main__":
    main()
