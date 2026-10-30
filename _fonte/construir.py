"""Gera as páginas do site a partir dos dados (_fonte/dados) e dos modelos (_fonte/modelos).

Uso, na raiz do repositório:
    python _fonte/construir.py              gera as páginas HTML, o sitemap e o robots.txt
    python _fonte/construir.py --pdf        também gera cv.pdf e pt/cv.pdf (precisa do Edge ou do Chrome)
    python _fonte/construir.py --verificar  confere se as páginas publicadas correspondem aos dados
                                            e se os links internos apontam para arquivos e âncoras que existem
    python _fonte/construir.py --links-externos  confere os links para fora do site (roda todo mês no GitHub)

As páginas em inglês ficam na raiz e as em português em pt/, como o GitHub Pages as serve.
Além das páginas fixas de site.yml, cada artigo com "id" ganha sua página em publications/ e
cada ementa com "publicar: true" ganha a sua em teaching/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, pass_context, select_autoescape
from markupsafe import Markup, escape

RAIZ = Path(__file__).resolve().parent.parent
FONTE = RAIZ / "_fonte"
IDIOMAS = ("en", "pt")

MODELOS = {
    "inicio": "inicio.html",
    "pesquisa": "pesquisa.html",
    "tese": "tese.html",
    "publicacoes": "publicacoes.html",
    "ensino": "ensino.html",
    "eleicoes": "eleicoes.html",
    "cv": "cv.html",
}
CV_PDF = {"en": "cv.pdf", "pt": "pt/cv.pdf"}
# Páginas que saem das listas dos dados: uma por artigo com "id" e uma por ementa com "publicar: true".
PAGINA_PUBLICACAO = {"en": "publications/{}.html", "pt": "pt/publications/{}.html"}
PAGINA_EMENTA = {"en": "teaching/{}.html", "pt": "pt/teaching/{}.html"}

MESES = {
    "pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
           "agosto", "setembro", "outubro", "novembro", "dezembro"],
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
}
NAVEGADORES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "msedge", "google-chrome", "chromium", "chromium-browser",
]

LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
ENFASE = re.compile(r"\*([^*]+)\*")


# ---------------------------------------------------------------- utilidades

def carregar_dados() -> dict:
    dados = {arq.stem: yaml.safe_load(arq.read_text(encoding="utf-8"))
             for arq in sorted((FONTE / "dados").glob("*.yml"))}
    erros = list(_pares_quebrados(dados))
    if erros:
        sys.exit("Texto com vírgula sem aspas em {pt: ..., en: ...}; ponha o texto entre aspas:\n  "
                 + "\n  ".join(erros))
    return dados


def _pares_quebrados(valor, caminho=""):
    """Acha pares {pt, en} que o YAML partiu por causa de uma vírgula fora de aspas."""
    if isinstance(valor, dict):
        if ("pt" in valor or "en" in valor) and (set(valor) - {"pt", "en"}):
            yield caminho
        for chave, filho in valor.items():
            yield from _pares_quebrados(filho, f"{caminho}.{chave}" if caminho else str(chave))
    elif isinstance(valor, list):
        for i, filho in enumerate(valor):
            yield from _pares_quebrados(filho, f"{caminho}[{i}]")


def traduzir(valor, idioma):
    """Escolhe a versão do idioma quando o valor é um par {pt: ..., en: ...}."""
    if isinstance(valor, dict) and valor and set(valor) <= {"pt", "en"}:
        if idioma in valor:
            return valor[idioma] if valor[idioma] is not None else ""
        return valor.get("pt", valor.get("en", ""))
    return valor


def inline(texto) -> Markup:
    """Converte o markdown mínimo dos dados (*itálico* e [texto](endereço)) em HTML seguro."""
    html = str(escape(texto or ""))
    html = LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', html)
    html = ENFASE.sub(r"<em>\1</em>", html)
    return Markup(html)


def caminho_publico(arquivo: str) -> str:
    """Endereço público de um arquivo do site: index.html vira a pasta."""
    return arquivo[: -len("index.html")] if arquivo.endswith("index.html") else arquivo


def relativo(origem: str, destino: str) -> str:
    """Link da página `origem` para `destino`, ambos relativos à raiz do site (ex.: 'pt/cv.html')."""
    destino, _, ancora = destino.partition("#")
    destino = caminho_publico(destino)
    base = os.path.dirname(origem) or "."
    if destino == "" or destino.endswith("/"):
        r = os.path.relpath(destino.rstrip("/") or ".", base).replace(os.sep, "/")
        r = "./" if r == "." else r + "/"
    else:
        r = os.path.relpath(destino, base).replace(os.sep, "/")
    return r + (f"#{ancora}" if ancora else "")


def data_extenso(data, idioma: str) -> str:
    if idioma == "pt":
        return f"{data.day} de {MESES['pt'][data.month - 1]} de {data.year}"
    return f"{data.day} {MESES['en'][data.month - 1]} {data.year}"


def formatar_autores(autores, idioma: str, eu: str) -> Markup:
    nomes = [Markup('<span class="eu">{}</span>').format(n) if n == eu else escape(n) for n in autores]
    if len(nomes) <= 1:
        return Markup("").join(nomes)
    conjuncao = " e " if idioma == "pt" else " and "
    return Markup(", ").join(nomes[:-1]) + Markup(conjuncao) + nomes[-1]


def json_ld(objeto) -> Markup:
    texto = json.dumps(objeto, ensure_ascii=False, indent=1)
    return Markup(texto.replace("</", "<\\/"))


def licenca_url(rotulo: str) -> str:
    """'CC BY-NC-ND 4.0' vira https://creativecommons.org/licenses/by-nc-nd/4.0/."""
    tipo, versao = rotulo.removeprefix("CC ").rsplit(" ", 1)
    return f"https://creativecommons.org/licenses/{tipo.lower()}/{versao}/"


def tamanho_arquivo(arquivo: str, idioma: str) -> str:
    kb = (RAIZ / arquivo).stat().st_size / 1024
    texto = f"{kb:.0f} KB" if kb < 1000 else f"{kb / 1024:.1f} MB"
    return texto.replace(".", ",") if idioma == "pt" else texto


def transcricao(arquivo: str) -> list[str]:
    """Texto de uma legenda WebVTT em parágrafos: uma pausa de mais de 1,5 s entre trechos abre parágrafo novo."""
    blocos = (RAIZ / arquivo).read_text(encoding="utf-8").replace("\r\n", "\n").split("\n\n")[1:]
    paragrafos, fim_anterior = [], None
    for bloco in blocos:
        linhas = [l for l in bloco.strip().split("\n") if l]
        tempos = next((l for l in linhas if "-->" in l), None)
        if not tempos:
            continue
        antes, depois = tempos.split("-->")
        inicio, fim = segundos(antes.strip()), segundos(depois.split()[0])
        texto = " ".join(linhas[linhas.index(tempos) + 1:])
        if fim_anterior is None or inicio - fim_anterior > 1.5:
            paragrafos.append(texto)
        else:
            paragrafos[-1] += " " + texto
        fim_anterior = fim
    return paragrafos


def segundos(marca: str) -> float:
    """'00:01:04.250' ou '01:04.250' em segundos."""
    partes = [float(p) for p in marca.split(":")]
    return sum(valor * 60 ** i for i, valor in enumerate(reversed(partes)))


def resumir(texto: str, limite: int = 155) -> str:
    """Começo do texto para a meta description: a frase inteira se couber, senão até uma palavra inteira."""
    texto = " ".join((texto or "").split())
    if len(texto) <= limite:
        return texto
    corte = texto[: limite + 1]
    fim_da_frase = corte.rfind(". ")
    if fim_da_frase >= 80:
        return corte[: fim_da_frase + 1]
    return corte[:limite].rsplit(" ", 1)[0].rstrip(",;:.") + "…"


# ---------------------------------------------------------------- páginas

@pass_context
def _t(ctx, valor):
    return traduzir(valor, ctx["idioma"])


@pass_context
def _rel(ctx, destino):
    if ctx.get("absoluto"):
        return "/" + caminho_publico(destino)
    return relativo(ctx["arquivo"], destino)


@pass_context
def _grafico(ctx, nome):
    """Embute o SVG do gráfico no idioma da página (ver _fonte/eleicoes/graficos.py)."""
    return Markup((FONTE / "eleicoes" / "graficos" / f"{nome}.{ctx['idioma']}.svg").read_text(encoding="utf-8"))


@pass_context
def _autores(ctx, lista):
    return formatar_autores(lista or [], ctx["idioma"], ctx["perfil"]["nome"])


@pass_context
def _pagina_publicacao(ctx, p):
    return PAGINA_PUBLICACAO[ctx["idioma"]].format(p["id"])


@pass_context
def _pagina_ementa(ctx, e):
    return PAGINA_EMENTA[ctx["idioma"]].format(e["id"])


@pass_context
def _tamanho(ctx, arquivo):
    return tamanho_arquivo(arquivo, ctx["idioma"])


def criar_ambiente() -> Environment:
    env = Environment(
        loader=FileSystemLoader(FONTE / "modelos"),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters.update(t=_t, inline=inline, autores=_autores)
    env.globals.update(rel=_rel, grafico=_grafico, pagina_publicacao=_pagina_publicacao,
                       pagina_ementa=_pagina_ementa, tamanho=_tamanho, licenca_url=licenca_url,
                       transcricao=transcricao)
    return env


def pessoa_json_ld(dados, idioma) -> dict:
    site, perfil = dados["site"], dados["perfil"]
    unesp = {"@type": "CollegeOrUniversity", "name": perfil["instituicao"], "url": "https://www.unesp.br/"}
    return {
        "@context": "https://schema.org",
        "@type": "Person",
        "@id": f"{site['url']}/#pessoa",
        "name": perfil["nome"],
        "alternateName": perfil["outros_nomes"],
        "url": f"{site['url']}/",
        "image": f"{site['url']}/{perfil['foto']}",
        "email": f"mailto:{perfil['email']}",
        "jobTitle": "Doutorando em Ciências Sociais" if idioma == "pt" else "PhD candidate in Social Sciences",
        "affiliation": unesp,
        "alumniOf": unesp,
        "knowsAbout": [traduzir(linha, idioma) for linha in perfil["linhas"]],
        "sameAs": [l["url"] for l in perfil["links"]] + [i["url"] for i in perfil["identificadores"]
                                                         if i.get("url") and i["url"] not in
                                                         {l["url"] for l in perfil["links"]}],
    }


def publicacao_ld(dados, p, idioma) -> dict:
    site, perfil, pubs = dados["site"], dados["perfil"], dados["publicacoes"]
    item = {
        "@type": "ScholarlyArticle" if p in pubs["artigos"] else "Chapter",
        "name": p["titulo"],
        "inLanguage": p.get("lingua", "pt"),
        "datePublished": str(p["ano"]),
        "author": [{"@type": "Person", "name": a} | ({"@id": f"{site['url']}/#pessoa"} if a == perfil["nome"] else {})
                   for a in p["autores"]],
    }
    if p in pubs["artigos"]:
        item["isPartOf"] = {"@type": "Periodical", "name": traduzir(p["veiculo"], idioma)}
    if p.get("doi"):
        item["sameAs"] = f"https://doi.org/{p['doi']}"
    if p.get("id"):
        item["url"] = f"{site['url']}/{PAGINA_PUBLICACAO[idioma].format(p['id'])}"
    elif p.get("url") or p.get("doi"):
        item["url"] = p.get("url") or f"https://doi.org/{p['doi']}"
    return item


def publicacoes_json_ld(dados, idioma) -> dict:
    site, pubs = dados["site"], dados["publicacoes"]
    return {"@context": "https://schema.org", "@type": "CollectionPage",
            "name": traduzir(site["paginas"]["publicacoes"]["titulo"], idioma),
            "hasPart": [publicacao_ld(dados, p, idioma) for p in pubs["artigos"] + pubs["capitulos"]]}


def artigo_json_ld(dados, p, idioma) -> dict:
    extra = dados["resumos"].get(p["id"], {})
    item = {"@context": "https://schema.org"} | publicacao_ld(dados, p, idioma)
    if p.get("titulo_en"):
        item["alternativeHeadline"] = p["titulo_en"]
    if extra.get("resumo"):
        item["abstract"] = traduzir(extra["resumo"], p.get("lingua", "pt"))
    if extra.get("palavras_chave"):
        item["keywords"] = traduzir(extra["palavras_chave"], p.get("lingua", "pt"))
    if p.get("pdf"):
        item["license"] = licenca_url(p["licenca"])
        item["encoding"] = {"@type": "MediaObject", "encodingFormat": "application/pdf",
                            "contentUrl": f"{dados['site']['url']}/{p['pdf']}"}
    return item


def metadados_citacao(dados, p) -> list[tuple[str, str]]:
    """Meta tags no formato que o Google Acadêmico lê (Highwire Press), na página de cada artigo."""
    tags = [("citation_title", p["titulo"])] + [("citation_author", a) for a in p["autores"]]
    tags += [("citation_publication_date", str(p["ano"])), ("citation_journal_title", traduzir(p["veiculo"], "pt"))]
    volume = re.fullmatch(r"(\d+)(?:\((\d+)\))?", str(p.get("volume", "")))
    if volume:
        tags.append(("citation_volume", volume.group(1)))
        if volume.group(2):
            tags.append(("citation_issue", volume.group(2)))
    if p.get("paginas"):
        inicio, _, fim = p["paginas"].partition("–")
        tags.append(("citation_firstpage", inicio))
        if fim:
            tags.append(("citation_lastpage", fim))
    if p.get("doi"):
        tags.append(("citation_doi", p["doi"]))
    tags.append(("citation_language", p.get("lingua", "pt")))
    chaves = dados["resumos"].get(p["id"], {}).get("palavras_chave")
    tags += [("citation_keywords", k) for k in traduzir(chaves, p.get("lingua", "pt")) or []]
    if p.get("pdf"):
        tags.append(("citation_pdf_url", f"{dados['site']['url']}/{p['pdf']}"))
    return tags


def contexto(dados, chave, idioma, arquivo, alternativas_arquivos) -> dict:
    site, perfil = dados["site"], dados["perfil"]
    paginas = site["paginas"]
    pagina = paginas.get(chave, {})
    absoluta = lambda a: f"{site['url']}/{caminho_publico(a)}"
    titulo = traduzir(pagina.get("titulo", ""), idioma)
    if chave == "inicio":
        titulo_documento = f"{perfil['nome']} · " + ("Sociólogo, UNESP" if idioma == "pt" else "Sociologist, UNESP")
    else:
        titulo_documento = f"{titulo} · {perfil['nome']}"
    artigos = dados["publicacoes"]["artigos"]
    return dict(
        idioma=idioma,
        lingua_html="pt-BR" if idioma == "pt" else "en",
        pagina=chave,
        arquivo=arquivo,
        arquivos=alternativas_arquivos,
        menu_ativo=pagina.get("menu_ativo", chave),
        menu=[{"chave": k, "rotulo": traduzir(paginas[k]["menu"], idioma), "arquivo": paginas[k]["arquivo"][idioma]}
              for k in site["menu"]],
        site=site,
        perfil=perfil,
        paginas=paginas,
        r=site["rotulos"],
        titulo_pagina=titulo,
        titulo_documento=titulo_documento,
        descricao=traduzir(pagina.get("descricao", ""), idioma),
        url_absoluta=absoluta(arquivo),
        alternativas={i: absoluta(a) for i, a in alternativas_arquivos.items()},
        data_atualizacao=data_extenso(site["atualizado"], idioma),
        cv_pdf=CV_PDF[idioma],
        pesquisa=dados["pesquisa"],
        publicacoes=dados["publicacoes"],
        manuscritos=dados["manuscritos"],
        apresentacoes=dados["apresentacoes"],
        ensino=dados["ensino"],
        curriculo=dados["curriculo"],
        eleicoes=dados["eleicoes"],
        destaques=[p for p in artigos if p.get("destaque")],
        ementas=ementas_publicadas(dados),
        og_tipo="profile" if chave == "inicio" else "website",
        citacao=[],
        json_ld=(json_ld(pessoa_json_ld(dados, idioma)) if chave == "inicio"
                 else json_ld(publicacoes_json_ld(dados, idioma)) if chave == "publicacoes" else None),
    )


def ementas_publicadas(dados) -> list:
    return [e for e in dados["ensino"].get("ementas", []) if e.get("publicar")]


def contexto_publicacao(dados, p, idioma, arquivos) -> dict:
    extra = dados["resumos"].get(p["id"], {})
    ctx = contexto(dados, "publicacoes", idioma, arquivos[idioma], arquivos)
    ctx.update(
        pagina="publicacao",
        p=p,
        resumo=extra.get("resumo") or {},
        palavras_chave=extra.get("palavras_chave"),
        titulo_pagina=p["titulo"],
        titulo_documento=f"{p['titulo']} · {dados['perfil']['nome']}",
        descricao=resumir(traduzir(extra.get("resumo"), idioma)),
        og_tipo="article",
        citacao=metadados_citacao(dados, p),
        json_ld=json_ld(artigo_json_ld(dados, p, idioma)),
    )
    return ctx


def contexto_ementa(dados, e, idioma, arquivos) -> dict:
    ctx = contexto(dados, "ensino", idioma, arquivos[idioma], arquivos)
    titulo = traduzir(e["titulo"], idioma)
    ctx.update(
        pagina="ementa",
        e=e,
        titulo_pagina=titulo,
        titulo_documento=f"{titulo} · {dados['perfil']['nome']}",
        descricao=resumir(traduzir(e["ementa"], idioma)),
    )
    return ctx


def paginas_geradas(dados):
    """(modelo, arquivos por idioma, função de contexto, item) de cada página que sai de uma lista dos dados."""
    for p in dados["publicacoes"]["artigos"]:
        if p.get("id"):
            yield "publicacao.html", {i: PAGINA_PUBLICACAO[i].format(p["id"]) for i in IDIOMAS}, contexto_publicacao, p
    for e in ementas_publicadas(dados):
        yield "ementa.html", {i: PAGINA_EMENTA[i].format(e["id"]) for i in IDIOMAS}, contexto_ementa, e


def sitemap(dados) -> str:
    site = dados["site"]
    absoluta = lambda a: f"{site['url']}/{caminho_publico(a)}"
    todas = [pagina["arquivo"] for pagina in site["paginas"].values()]
    todas += [arquivos for _, arquivos, _, _ in paginas_geradas(dados)]
    linhas = ['<?xml version="1.0" encoding="UTF-8"?>',
              '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    for arquivos in todas:
        for idioma in IDIOMAS:
            linhas.append("  <url>")
            linhas.append(f"    <loc>{absoluta(arquivos[idioma])}</loc>")
            for alt, hreflang in (("en", "en"), ("pt", "pt-BR"), ("en", "x-default")):
                linhas.append(f'    <xhtml:link rel="alternate" hreflang="{hreflang}" href="{absoluta(arquivos[alt])}"/>')
            linhas.append(f"    <lastmod>{site['atualizado']}</lastmod>")
            linhas.append("  </url>")
    linhas.append("</urlset>")
    return "\n".join(linhas) + "\n"


def gerar(dados) -> dict[str, str]:
    """Devolve {caminho relativo à raiz: conteúdo} de tudo o que o site gera."""
    env = criar_ambiente()
    site = dados["site"]
    saida = {}
    for chave, pagina in site["paginas"].items():
        for idioma in IDIOMAS:
            arquivo = pagina["arquivo"][idioma]
            ctx = contexto(dados, chave, idioma, arquivo, pagina["arquivo"])
            saida[arquivo] = env.get_template(MODELOS[chave]).render(**ctx)
    for modelo, arquivos, montar_contexto, item in paginas_geradas(dados):
        for idioma in IDIOMAS:
            saida[arquivos[idioma]] = env.get_template(modelo).render(**montar_contexto(dados, item, idioma, arquivos))
    for movida in site["redirecionamentos"]:
        for idioma in IDIOMAS:
            arquivo = movida["de"][idioma]
            alternativas = {i: movida["para"][i].partition("#")[0] for i in IDIOMAS}
            ctx = contexto(dados, "movida", idioma, arquivo, alternativas)
            ctx.update(destino=movida["para"][idioma],
                       destino_absoluto=f"{site['url']}/{caminho_publico(movida['para'][idioma])}")
            saida[arquivo] = env.get_template("redireciona.html").render(**ctx)
    ctx = contexto(dados, "inicio", "en", "404.html", site["paginas"]["inicio"]["arquivo"])
    ctx.update(absoluto=True, pagina="404", menu_ativo=None, json_ld=None,
               titulo_documento=f"Page not found · Página não encontrada · {dados['perfil']['nome']}")
    saida["404.html"] = env.get_template("404.html").render(**ctx)
    saida["sitemap.xml"] = sitemap(dados)
    saida["robots.txt"] = f"User-agent: *\nAllow: /\n\nSitemap: {site['url']}/sitemap.xml\n"
    return saida


def gravar(saida: dict[str, str]) -> None:
    for caminho, conteudo in saida.items():
        destino = RAIZ / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(conteudo, encoding="utf-8", newline="\n")


# ---------------------------------------------------------------- PDF do currículo

def achar_navegador() -> str | None:
    for candidato in NAVEGADORES:
        if os.path.isabs(candidato) and os.path.exists(candidato):
            return candidato
        if not os.path.isabs(candidato) and shutil.which(candidato):
            return shutil.which(candidato)
    return None


def _aguardar_arquivo(caminho: Path, limite: float = 60) -> None:
    """O Edge pode devolver o controle antes de terminar de gravar o PDF: espera o tamanho estabilizar."""
    import time

    inicio, anterior, estaveis = time.monotonic(), -1, 0
    while time.monotonic() - inicio < limite:
        tamanho = caminho.stat().st_size if caminho.exists() else -1
        estaveis = estaveis + 1 if tamanho > 0 and tamanho == anterior else 0
        if estaveis >= 3:
            return
        anterior = tamanho
        time.sleep(0.5)
    sys.exit(f"O navegador não terminou de gravar {caminho.name}.")


def marca_do_cv(html: str) -> str:
    """Impressão digital do HTML do currículo. Vai gravada no PDF, e a verificação compara as duas."""
    return hashlib.sha256(html.replace("\r\n", "\n").encode("utf-8")).hexdigest()[:16]


MARCA_NO_PDF = re.compile(rb"cv\.html ([0-9a-f]{16})")


def gerar_pdfs(dados) -> None:
    import fitz  # PyMuPDF; só é preciso aqui, porque o GitHub não gera os PDFs

    navegador = achar_navegador()
    if not navegador:
        sys.exit("Para gerar os PDFs, instale o Microsoft Edge ou o Google Chrome.")
    perfil = dados["perfil"]
    for idioma, pdf in CV_PDF.items():
        html = RAIZ / dados["site"]["paginas"]["cv"]["arquivo"][idioma]
        destino = RAIZ / pdf
        destino.unlink(missing_ok=True)
        with tempfile.TemporaryDirectory() as pasta_perfil:
            subprocess.run(
                [navegador, "--headless=new", "--disable-gpu", "--no-first-run", "--disable-extensions",
                 "--no-pdf-header-footer", "--print-to-pdf-no-header", f"--user-data-dir={pasta_perfil}",
                 f"--print-to-pdf={destino}", html.as_uri()],
                check=True, capture_output=True, timeout=180,
            )
            _aguardar_arquivo(destino)
        documento = fitz.open(destino)
        documento.set_metadata({
            "title": f"{perfil['nome']} — " + ("Currículo" if idioma == "pt" else "Curriculum vitae"),
            "author": perfil["nome"],
            "subject": traduzir(perfil["cargo"], idioma),
            "keywords": "; ".join(traduzir(linha, idioma) for linha in perfil["linhas"]),
            "creator": f"_fonte/construir.py; cv.html {marca_do_cv(html.read_text(encoding='utf-8'))}",
            "producer": documento.metadata.get("producer", ""),
        })
        documento.set_language("pt-BR" if idioma == "pt" else "en")
        temporario = destino.with_suffix(".tmp.pdf")
        documento.save(temporario, garbage=3, deflate=True)
        documento.close()
        temporario.replace(destino)
        print(f"PDF gerado: {pdf}")


# ---------------------------------------------------------------- verificação

class _Coletor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        if atributos.get("id"):
            self.ids.add(atributos["id"])
        for nome in ("href", "src"):
            valor = atributos.get(nome)
            if valor and not (tag == "link" and atributos.get("rel") in ("canonical", "alternate")):
                self.links.append(valor)


def verificar(dados) -> int:
    problemas = []
    saida = gerar(dados)
    for caminho, conteudo in saida.items():
        atual = RAIZ / caminho
        if not atual.exists():
            problemas.append(f"{caminho}: não existe; rode python _fonte/construir.py")
        elif atual.read_text(encoding="utf-8").replace("\r\n", "\n") != conteudo:
            problemas.append(f"{caminho}: desatualizado em relação aos dados; rode python _fonte/construir.py")
    for idioma, pdf in CV_PDF.items():
        arquivo = RAIZ / pdf
        marca = MARCA_NO_PDF.search(arquivo.read_bytes()) if arquivo.exists() else None
        esperada = marca_do_cv(saida[dados["site"]["paginas"]["cv"]["arquivo"][idioma]])
        if not marca or marca.group(1).decode() != esperada:
            problemas.append(f"{pdf}: não corresponde ao currículo atual; rode python _fonte/construir.py --pdf")
    for p in dados["publicacoes"]["artigos"]:
        if p.get("pdf") and not (RAIZ / p["pdf"]).exists():
            problemas.append(f"{p['pdf']}: o PDF indicado em publicacoes.yml não existe")

    paginas_html = {c: v for c, v in saida.items() if c.endswith(".html")}
    ids = {}
    for caminho, conteudo in paginas_html.items():
        coletor = _Coletor()
        coletor.feed(conteudo)
        ids[caminho] = (coletor.ids, coletor.links)
    for caminho, (_, links) in ids.items():
        if caminho == "404.html":
            continue
        for link in links:
            if re.match(r"^(https?:|mailto:|data:)", link):
                continue
            alvo, _, ancora = link.partition("#")
            if alvo:
                resolvido = os.path.normpath(os.path.join(os.path.dirname(caminho), alvo)).replace(os.sep, "/")
                if resolvido.startswith(".."):
                    problemas.append(f"{caminho}: link para fora do site: {link}")
                    continue
                if alvo.endswith("/") or alvo == ".":
                    resolvido = "index.html" if resolvido == "." else f"{resolvido}/index.html"
            else:
                resolvido = caminho
            if resolvido not in paginas_html and not (RAIZ / resolvido).exists():
                problemas.append(f"{caminho}: link quebrado: {link}")
            elif ancora and resolvido in ids and ancora not in ids[resolvido][0]:
                problemas.append(f"{caminho}: âncora inexistente: {link}")

    for problema in problemas:
        print(problema)
    print("Tudo certo." if not problemas else f"{len(problemas)} problema(s).")
    return 1 if problemas else 0


# Sites que barram robôs: o link existe, mas a resposta automática não prova nada.
NAO_VERIFICAVEIS = ("linkedin.com", "scholar.google.com", "lattes.cnpq.br", "scopus.com", "webofscience.com")


def verificar_links_externos(dados) -> int:
    """Confere os links externos das páginas (DOIs, revistas, perfis). Roda uma vez por mês no GitHub."""
    import urllib.error
    import urllib.request

    links = set()
    for caminho, conteudo in gerar(dados).items():
        if caminho.endswith(".html"):
            coletor = _Coletor()
            coletor.feed(conteudo)
            links |= {l for l in coletor.links if l.startswith(("http://", "https://"))}
    quebrados, avisos = [], []
    cabecalhos = {"User-Agent": "Mozilla/5.0 (verificacao de links; lucasfloresvasques.github.io)"}
    for url in sorted(links):
        if any(dominio in url for dominio in NAO_VERIFICAVEIS):
            continue
        situacao = None
        for metodo in ("HEAD", "GET"):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, method=metodo, headers=cabecalhos), timeout=30) as r:
                    situacao = r.status
                    break
            except urllib.error.HTTPError as erro:
                situacao = erro.code
            except Exception as erro:  # DNS, tempo esgotado, certificado
                situacao = type(erro).__name__
        if isinstance(situacao, int) and situacao < 400:
            continue
        (avisos if situacao in (401, 403, 429) else quebrados).append(f"{situacao}  {url}")
    for linha in avisos:
        print(f"não verificável  {linha}")
    for linha in quebrados:
        print(f"quebrado  {linha}")
    print(f"{len(links)} links externos; {len(quebrados)} quebrado(s), {len(avisos)} não verificável(is).")
    return 1 if quebrados else 0


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # mensagens com acento também em terminais do Windows
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pdf", action="store_true", help="gera também os PDFs do currículo")
    parser.add_argument("--verificar", action="store_true", help="só confere, sem gravar nada")
    parser.add_argument("--links-externos", action="store_true", help="confere os links para fora do site")
    args = parser.parse_args()
    dados = carregar_dados()
    if args.links_externos:
        sys.exit(verificar_links_externos(dados))
    if args.verificar:
        sys.exit(verificar(dados))
    saida = gerar(dados)
    gravar(saida)
    print(f"{len(saida)} arquivos gerados.")
    if args.pdf:
        gerar_pdfs(dados)


if __name__ == "__main__":
    main()
