"""Gera as páginas do site a partir dos dados (_fonte/dados) e dos modelos (_fonte/modelos).

Uso, na raiz do repositório:
    python _fonte/construir.py              gera as páginas HTML, o sitemap e o robots.txt
    python _fonte/construir.py --pdf        também gera cv.pdf e pt/cv.pdf (precisa do Edge ou do Chrome)
    python _fonte/construir.py --verificar  confere se as páginas publicadas correspondem aos dados
                                            e se os links internos apontam para arquivos e âncoras que existem

As páginas em inglês ficam na raiz e as em português em pt/, como o GitHub Pages as serve.
"""
from __future__ import annotations

import argparse
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
    "cv": "cv.html",
}
CV_PDF = {"en": "cv.pdf", "pt": "pt/cv.pdf"}

MESES = {
    "pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
           "agosto", "setembro", "outubro", "novembro", "dezembro"],
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
}
MESES_CURTOS = {
    "pt": ["jan.", "fev.", "mar.", "abr.", "maio", "jun.", "jul.", "ago.", "set.", "out.", "nov.", "dez."],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
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
def _autores(ctx, lista):
    return formatar_autores(lista or [], ctx["idioma"], ctx["perfil"]["nome"])


@pass_context
def _mes_ano(ctx, valor):
    texto = str(valor)
    if re.fullmatch(r"\d{4}-\d{2}", texto):
        ano, mes = texto.split("-")
        return f"{MESES_CURTOS[ctx['idioma']][int(mes) - 1]} {ano}"
    return texto


def criar_ambiente() -> Environment:
    env = Environment(
        loader=FileSystemLoader(FONTE / "modelos"),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters.update(t=_t, inline=inline, autores=_autores, mes_ano=_mes_ano)
    env.globals.update(rel=_rel)
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
        "knowsAbout": [traduzir(linha["nome"], idioma) for linha in perfil["linhas"]],
        "sameAs": [l["url"] for l in perfil["links"]] + [i["url"] for i in perfil["identificadores"]
                                                         if i.get("url") and i["url"] not in
                                                         {l["url"] for l in perfil["links"]}],
    }


def publicacoes_json_ld(dados, idioma) -> dict:
    site, perfil, pubs = dados["site"], dados["perfil"], dados["publicacoes"]
    partes = []
    for p in pubs["artigos"] + pubs["capitulos"]:
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
        if p.get("url") or p.get("doi"):
            item["url"] = p.get("url") or f"https://doi.org/{p['doi']}"
        partes.append(item)
    return {"@context": "https://schema.org", "@type": "CollectionPage",
            "name": traduzir(site["paginas"]["publicacoes"]["titulo"], idioma), "hasPart": partes}


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
        destaques=[p for p in artigos if p.get("destaque")],
        json_ld=(json_ld(pessoa_json_ld(dados, idioma)) if chave == "inicio"
                 else json_ld(publicacoes_json_ld(dados, idioma)) if chave == "publicacoes" else None),
    )


def sitemap(dados) -> str:
    site = dados["site"]
    absoluta = lambda a: f"{site['url']}/{caminho_publico(a)}"
    linhas = ['<?xml version="1.0" encoding="UTF-8"?>',
              '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    for pagina in site["paginas"].values():
        for idioma in IDIOMAS:
            linhas.append("  <url>")
            linhas.append(f"    <loc>{absoluta(pagina['arquivo'][idioma])}</loc>")
            for alt, hreflang in (("en", "en"), ("pt", "pt-BR"), ("en", "x-default")):
                linhas.append(f'    <xhtml:link rel="alternate" hreflang="{hreflang}" href="{absoluta(pagina["arquivo"][alt])}"/>')
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
            "keywords": "; ".join(traduzir(l["nome"], idioma) for l in perfil["linhas"]),
            "creator": "_fonte/construir.py",
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pdf", action="store_true", help="gera também os PDFs do currículo")
    parser.add_argument("--verificar", action="store_true", help="só confere, sem gravar nada")
    args = parser.parse_args()
    dados = carregar_dados()
    if args.verificar:
        sys.exit(verificar(dados))
    saida = gerar(dados)
    gravar(saida)
    print(f"{len(saida)} arquivos gerados.")
    if args.pdf:
        gerar_pdfs(dados)


if __name__ == "__main__":
    main()
