"""Gera as imagens fixas do site: o ícone para celulares e o cartão de compartilhamento.

Rode só quando mudar a foto, o favicon ou o texto do cartão:
    python _fonte/gerar_imagens.py
O cartão usa a Source Serif 4 se a variável FONTE_CARTAO apontar para o arquivo .ttf variável
(google/fonts, ofl/sourceserif4); sem ela, usa a Georgia do Windows.
"""
import os
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parent.parent
ASSETS = RAIZ / "assets"
GEORGIA = "C:/Windows/Fonts/georgia.ttf"
TINTA, SUAVE, DESTAQUE = (27, 29, 26), (91, 96, 88), (31, 78, 90)


def fonte(tamanho, peso=400, tamanho_otico=None):
    caminho = os.environ.get("FONTE_CARTAO")
    if not caminho:
        return ImageFont.truetype(GEORGIA, tamanho)
    serifa = ImageFont.truetype(caminho, tamanho)
    eixos = {eixo["name"]: eixo for eixo in serifa.get_variation_axes()}
    valores = {b"Weight": peso, b"Optical Size": tamanho_otico or min(60, tamanho)}
    serifa.set_variation_by_axes([valores.get(nome, eixo["default"]) for nome, eixo in eixos.items()])
    return serifa


def icone_celular():
    pagina = fitz.open(ASSETS / "favicon.svg")[0]
    escala = 180 / pagina.rect.width
    pagina.get_pixmap(matrix=fitz.Matrix(escala, escala), alpha=False).save(ASSETS / "apple-touch-icon.png")


def cartao():
    largura, altura = 1200, 630
    cartao = Image.new("RGB", (largura, altura), (253, 253, 251))
    foto = Image.open(ASSETS / "lucas-vasques-retrato.webp").convert("RGB")
    foto = foto.resize((round(foto.width * altura / foto.height), altura), Image.LANCZOS)
    cartao.paste(foto, (0, 0))
    desenho = ImageDraw.Draw(cartao)
    x = foto.width + 70
    desenho.rectangle([x, 214, x + 48, 217], fill=DESTAQUE)
    desenho.text((x, 238), "Lucas Flôres", font=fonte(68, 600), fill=TINTA)
    desenho.text((x, 316), "Vasques", font=fonte(68, 600), fill=TINTA)
    desenho.text((x, 418), "Sociologist, UNESP", font=fonte(32, 400, 20), fill=SUAVE)
    desenho.text((x, 540), "lucasfloresvasques.github.io", font=fonte(26, 400, 16), fill=DESTAQUE)
    cartao.save(ASSETS / "cartao-compartilhamento.jpg", quality=86, optimize=True, progressive=True)


if __name__ == "__main__":
    icone_celular()
    cartao()
    print("Imagens geradas em assets/.")
