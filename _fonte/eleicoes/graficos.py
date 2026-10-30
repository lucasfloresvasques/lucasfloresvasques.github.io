"""Gráficos da página Eleições 2026, em SVG, a partir dos CSVs em assets/eleicoes-2026/dados.

Rode quando mudar os dados ou o desenho:
    python _fonte/eleicoes/graficos.py
Saída: _fonte/eleicoes/graficos/<nome>.<pt|en>.svg, que o construir.py embute nas páginas.
O texto fica como texto (usa a fonte do site) e as cores viram variáveis do CSS, então os
gráficos acompanham o modo escuro. Se a variável FONTE_GRAFICOS apontar para o .ttf da
Source Serif 4, as medidas do texto ficam exatas; sem ela, o matplotlib usa uma serifa parecida.
"""
import os
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager

RAIZ = Path(__file__).resolve().parents[2]
DADOS = RAIZ / "assets" / "eleicoes-2026" / "dados"
SAIDA = Path(__file__).resolve().parent / "graficos"

# Cores de trabalho; no SVG viram variáveis do CSS do site.
TINTA, SUAVE, FIO, DESTAQUE, OCRE = "#1b1d1a", "#5b6058", "#e3e4df", "#1f4e5a", "#c08a2e"
VARIAVEIS = {TINTA: "var(--tinta)", SUAVE: "var(--suave)", FIO: "var(--fio)", DESTAQUE: "var(--destaque)"}

TEXTOS = {
    "pt": {
        "apuradas": "seções apuradas (%)",
        "projecao": "projeção",
        "contagem": "contagem do TSE",
        "faixa": "faixa de erro",
        "resultado": "leitura final: 51,76%",
        "pp": "p.p.",
        "faixa_2022": "faixa do teste com 2022",
        "erro_2026": "erro da projeção em 2026",
        "erro_contagem": "erro da contagem",
        "variacao": "variação de Lula, 2022 → 2026 (pontos percentuais)",
        "portes": ["até 20 mil", "20 a 100 mil", "100 a 200 mil", "200 mil ou mais"],
        "porte_eixo": "variação de Lula por porte do município (p.p.)",
    },
    "en": {
        "apuradas": "polling sections counted (%)",
        "projecao": "projection",
        "contagem": "official count (TSE)",
        "faixa": "error band",
        "resultado": "final reading: 51.76%",
        "pp": "pp",
        "faixa_2022": "error band from the 2022 test",
        "erro_2026": "projection error in 2026",
        "erro_contagem": "error of the raw count",
        "variacao": "change in Lula's share, 2022 → 2026 (percentage points)",
        "portes": ["up to 20k votes", "20k to 100k", "100k to 200k", "200k or more"],
        "porte_eixo": "change in Lula's share by municipality size (pp)",
    },
}


def configurar():
    fonte = os.environ.get("FONTE_GRAFICOS")
    if fonte:
        font_manager.fontManager.addfont(fonte)
    plt.rcParams.update({
        "font.family": ["Source Serif 4", "Georgia", "DejaVu Serif"],
        "font.size": 12.5,
        "svg.fonttype": "none",
        "svg.hashsalt": "lfv-eleicoes-2026",
        "axes.edgecolor": SUAVE,
        "axes.labelcolor": SUAVE,
        "xtick.color": SUAVE,
        "ytick.color": SUAVE,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": FIO,
        "grid.linewidth": 0.8,
        "axes.axisbelow": True,
        "figure.facecolor": "none",
        "axes.facecolor": "none",
    })


def numero(valor, idioma, casas=2):
    texto = f"{valor:.{casas}f}"
    return texto.replace(".", ",") if idioma == "pt" else texto


def salvar(fig, nome, idioma, descricao):
    SAIDA.mkdir(parents=True, exist_ok=True)
    caminho = SAIDA / f"{nome}.{idioma}.svg"
    fig.savefig(caminho, format="svg", bbox_inches="tight", pad_inches=0.14, metadata={"Date": None})
    plt.close(fig)
    svg = caminho.read_text(encoding="utf-8")
    svg = svg[svg.index("<svg"):]
    svg = re.sub(r"<metadata>.*?</metadata>\s*", "", svg, flags=re.S)
    svg = re.sub(r'(<svg[^>]*?) width="[^"]+" height="[^"]+"', r"\1", svg, count=1)
    svg = svg.replace("<svg ", f'<svg role="img" aria-label="{descricao}" ', 1)
    # ids próprios de cada gráfico, para não colidirem quando vários ficam na mesma página
    svg = re.sub(r'id="([^"]+)"', rf'id="{nome}-\1"', svg)
    svg = re.sub(r"url\(#([^)]+)\)", rf"url(#{nome}-\1)", svg)
    svg = re.sub(r'xlink:href="#([^"]+)"', rf'xlink:href="#{nome}-\1"', svg)
    for cor, variavel in VARIAVEIS.items():
        svg = svg.replace(cor, variavel)
    caminho.write_text(svg, encoding="utf-8", newline="\n")


def noite(idioma):
    t = TEXTOS[idioma]
    df = pd.read_csv(DADOS / "serie_projecao_rodadas.csv")
    df = df[df["apurado"] >= 2]
    fig, ax = plt.subplots(figsize=(6.4, 3.9))
    ax.fill_between(df["apurado"], df["faixa_inf"], df["faixa_sup"], color=DESTAQUE, alpha=0.13, lw=0)
    ax.axhline(50, color=SUAVE, lw=0.9, ls=(0, (4, 3)))
    ax.plot(df["apurado"], df["contagem"], color=SUAVE, lw=1.4)
    ax.plot(df["apurado"], df["projecao"], color=DESTAQUE, lw=2.2)
    final = df.iloc[-1]
    ax.plot([final["apurado"]], [51.764], "o", color=TINTA, ms=4.5)
    ax.annotate(t["resultado"], (final["apurado"], 51.764), xytext=(-6, 12), textcoords="offset points",
                ha="right", color=TINTA, fontsize=11.5)
    ax.text(30, 51.93, t["projecao"], color=DESTAQUE, fontsize=12)
    ax.text(30, 49.05, t["contagem"], color=SUAVE, fontsize=12)
    ax.set_xlim(0, 101)
    ax.set_ylim(48.5, 53.2)
    ax.set_yticks([49, 50, 51, 52, 53])
    ax.set_yticklabels([f"{v}%" for v in [49, 50, 51, 52, 53]])
    ax.set_xlabel(t["apuradas"])
    ax.grid(axis="x", visible=False)
    salvar(fig, "noite", idioma, t["projecao"] + " × " + t["contagem"])


def erro(idioma):
    t = TEXTOS[idioma]
    bt = pd.read_csv(DADOS / "backtest_2022_vs_2026.csv")
    em = pd.read_csv(DADOS / "erro_por_marco.csv")
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.plot(bt["apurado_real"], bt["erro_real_2026"], color=DESTAQUE, lw=2.2, marker="o", ms=3.5, label=t["erro_2026"])
    ax.plot(bt["apurado"], bt["faixa_teste_2022"], color=SUAVE, lw=1.4, ls=(0, (4, 3)), label=t["faixa_2022"])
    ax.plot(em["apurado"], em["erro_contagem_abs"], color=OCRE, lw=1.6, marker="o", ms=3.5, label=t["erro_contagem"])
    legenda = ax.legend(frameon=False, loc="upper right", handlelength=2.4, fontsize=11.5, borderaxespad=0.2)
    for texto in legenda.get_texts():
        texto.set_color(TINTA)
    ax.set_xlim(0, 101)
    ax.set_ylim(0, 2.6)
    ax.set_yticks([0, 0.5, 1, 1.5, 2, 2.5])
    ax.set_yticklabels([numero(v, idioma, 1) + " " + t["pp"] if v else "0" for v in [0, 0.5, 1, 1.5, 2, 2.5]])
    ax.set_xlabel(t["apuradas"])
    ax.grid(axis="x", visible=False)
    salvar(fig, "erro", idioma, t["erro_2026"])


def estados(idioma):
    t = TEXTOS[idioma]
    df = pd.read_csv(DADOS / "estados_2022_2026.csv").sort_values("variacao")
    fig, ax = plt.subplots(figsize=(6.4, 7.4))
    cores = [DESTAQUE if v > 0 else OCRE for v in df["variacao"]]
    y = range(len(df))
    ax.hlines(y, 0, df["variacao"], color=cores, lw=1.6)
    ax.scatter(df["variacao"], y, color=cores, s=26, zorder=3)
    ax.axvline(0, color=SUAVE, lw=0.9)
    ax.set_yticks(list(y))
    ax.set_yticklabels(df["nome"], fontsize=11.5)
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(-3.4, 5.4)
    ax.set_xticks([-3, -2, -1, 0, 1, 2, 3, 4, 5])
    ax.set_xticklabels([("+" if v > 0 else "") + numero(v, idioma, 0) for v in [-3, -2, -1, 0, 1, 2, 3, 4, 5]])
    ax.set_xlabel(t["variacao"])
    ax.grid(axis="y", visible=False)
    ax.spines["left"].set_visible(False)
    salvar(fig, "estados", idioma, t["variacao"])


def porte(idioma):
    t = TEXTOS[idioma]
    df = pd.read_csv(DADOS / "municipios_por_porte.csv")
    fig, ax = plt.subplots(figsize=(6.4, 2.5))
    y = list(range(len(df)))[::-1]
    cores = [DESTAQUE if v > 0 else OCRE for v in df["variacao_ponderada"]]
    ax.barh(y, df["variacao_ponderada"], color=cores, height=0.55)
    for yi, v in zip(y, df["variacao_ponderada"]):
        rotulo = ("+" if v > 0 else "") + numero(v, idioma)
        ax.text(v + (0.08 if v >= 0 else -0.08), yi, rotulo, va="center", ha="left" if v >= 0 else "right",
                color=TINTA, fontsize=11.5)
    ax.axvline(0, color=SUAVE, lw=0.9)
    ax.set_yticks(y)
    ax.set_yticklabels(t["portes"], fontsize=11.5)
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(-3.7, 3.8)
    ax.set_xticks([])
    ax.set_xlabel(t["porte_eixo"])
    ax.grid(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    salvar(fig, "porte", idioma, t["porte_eixo"])


if __name__ == "__main__":
    configurar()
    for idioma in ("pt", "en"):
        for grafico in (noite, erro, estados, porte):
            grafico(idioma)
    print(f"Gráficos gravados em {SAIDA.relative_to(RAIZ)}.")
