# Site acadêmico de Lucas Flôres Vasques

https://lucasfloresvasques.github.io/: inglês na raiz, português em `/pt/`.

*English: the pages are generated from the YAML files in `_fonte/dados/` by `_fonte/construir.py`. Edit the data, not the HTML.*

## Como atualizar

As páginas são geradas a partir de arquivos de dados. Não edite os `.html` à mão, porque eles são sobrescritos a cada geração.

1. Edite o arquivo certo em `_fonte/dados/`:

   | Arquivo | Conteúdo |
   |---|---|
   | `perfil.yml` | apresentação, linhas de pesquisa, perfis e novidades da página inicial |
   | `pesquisa.yml` | declaração de pesquisa, método, tese e próximo projeto |
   | `publicacoes.yml` | publicações; `destaque: true` leva o item à página inicial (no máximo 3); `id` cria a página própria do artigo |
   | `resumos.yml` | resumo e palavras-chave de cada artigo com `id`, como saíram na revista |
   | `manuscritos.yml` | manuscritos em avaliação ou em preparação |
   | `apresentacoes.yml` | apresentações em eventos |
   | `ensino.yml` | docência, minicursos, ementas de cursos (só aparecem com `publicar: true`), materiais didáticos, dados e código |
   | `curriculo.yml` | formação, bolsas, atuação acadêmica, prêmios e formação complementar |
   | `eleicoes.yml` | página Eleições 2026: textos, vídeo, tabela e arquivos de dados; os gráficos saem de `_fonte/eleicoes/graficos.py`; as legendas do vídeo ficam em `assets/eleicoes-2026/legendas-*.vtt`, e a transcrição da página sai delas |
   | `site.yml` | data de atualização, menu e textos fixos da interface |

   Cada texto tem uma versão `pt` e outra `en`. Nos textos, `*assim*` vira itálico e `[texto](endereço)` vira link.
2. Atualize `atualizado:` em `_fonte/dados/site.yml`.
3. Gere as páginas e os PDFs do currículo (os PDFs precisam do Edge ou do Chrome):

   ```
   pip install -r _fonte/requisitos.txt pymupdf
   python _fonte/construir.py --pdf
   ```

4. Confira os links internos, se as páginas correspondem aos dados e se os PDFs do currículo correspondem ao currículo atual:

   ```
   python _fonte/construir.py --verificar
   ```

5. Faça commit e push. O GitHub Pages publica em cerca de um minuto, e o GitHub Actions repete a verificação a cada push (`.github/workflows/verificar.yml`).
   No dia 1º de cada mês, outro fluxo confere os links externos (`.github/workflows/links.yml`); se algum quebrar, o GitHub avisa por e-mail. Para conferir na hora: `python _fonte/construir.py --links-externos`.

### Página de um artigo

Um artigo com `id` em `publicacoes.yml` ganha `publications/<id>.html` (e a versão em `pt/`), com resumo, palavras-chave, DOI e as meta tags que o Google Acadêmico lê. Se a licença da revista permitir redistribuir (Creative Commons), copie o PDF publicado para `publications/<id>.pdf` e preencha `pdf:` e `licenca:` no artigo.

## Regras de conteúdo

- Manuscritos em avaliação aparecem só com título, autores e situação, sem periódico e sem resumo. O resumo entra depois da publicação ou como preprint.
- Manuscrito em coautoria só entra com o acordo de todos os coautores.
- Resultados de pesquisa com bolsa FAPESP levam o número do processo e o aviso de responsabilidade (já estão nos modelos).
- O repositório é público, inclusive o histórico: não publique dados reais de pesquisa, microdados de terceiros (como os do PELA-USAL) nem pareceres.

## Estrutura

- `_fonte/`: gerador (`construir.py`), modelos HTML (`modelos/`), dados (`dados/`) e o script das imagens fixas (`gerar_imagens.py`).
- `assets/`: estilo, foto, ícones e cartão de compartilhamento.
- `resources/`: materiais didáticos, sob CC BY 4.0.
- `publications/`: página de cada artigo e os PDFs publicados que a licença permite redistribuir.
- Páginas geradas: `index.html`, `research.html`, `thesis.html`, `publications.html`, `teaching.html`, `elections-2026.html` e `cv.html`, as mesmas em `pt/`, as páginas de `publications/` e `teaching/`, além de `404.html`, `sitemap.xml`, `robots.txt`, `cv.pdf` e `pt/cv.pdf`. Os endereços antigos `work-in-progress.html`, `data-code.html` e `service.html` redirecionam para os novos.
