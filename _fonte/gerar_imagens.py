"""Gera as imagens fixas do site: o ícone para celulares e o cartão de compartilhamento.

Rode só quando mudar a foto, o favicon ou o texto do cartão:
    python _fonte/gerar_imagens.py
Usa Pillow e PyMuPDF, e as fontes Georgia e Segoe UI do Windows.
"""
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parent.parent
ASSETS = RAIZ / "assets"
FONTES = Path("C:/Windows/Fonts")


def icone_celular():
    pagina = fitz.open(ASSETS / "favicon.svg")[0]
    escala = 180 / pagina.rect.width
    pagina.get_pixmap(matrix=fitz.Matrix(escala, escala), alpha=False).save(ASSETS / "apple-touch-icon.png")


def cartao():
    largura, altura = 1200, 630
    tinta, suave, destaque = (37, 41, 35), (89, 96, 88), (52, 83, 104)
    cartao = Image.new("RGB", (largura, altura), (255, 255, 255))
    foto = Image.open(ASSETS / "lucas-vasques-retrato.webp").convert("RGB")
    foto = foto.resize((round(foto.width * altura / foto.height), altura), Image.LANCZOS)
    cartao.paste(foto, (0, 0))
    desenho = ImageDraw.Draw(cartao)
    x = foto.width + 64
    serifa = ImageFont.truetype(str(FONTES / "georgia.ttf"), 64)
    sans = ImageFont.truetype(str(FONTES / "segoeui.ttf"), 30)
    sans_menor = ImageFont.truetype(str(FONTES / "segoeui.ttf"), 26)
    desenho.rectangle([x, 196, x + 56, 200], fill=destaque)
    desenho.text((x, 222), "Lucas Flôres", font=serifa, fill=tinta)
    desenho.text((x, 296), "Vasques", font=serifa, fill=tinta)
    desenho.text((x, 396), "Sociologist · PhD candidate, UNESP", font=sans, fill=suave)
    desenho.text((x, 438), "Classification, markets, elites", font=sans, fill=suave)
    desenho.text((x, 480), "Geometric Data Analysis", font=sans, fill=suave)
    desenho.text((x, 552), "lucasfloresvasques.github.io", font=sans_menor, fill=destaque)
    cartao.save(ASSETS / "cartao-compartilhamento.jpg", quality=86, optimize=True, progressive=True)


if __name__ == "__main__":
    icone_celular()
    cartao()
    print("Imagens geradas em assets/.")
