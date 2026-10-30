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
   | `publicacoes.yml` | publicações; `destaque: true` leva o item à página inicial (no máximo 3) |
   | `manuscritos.yml` | manuscritos em avaliação ou em preparação |
   | `apresentacoes.yml` | apresentações em eventos |
   | `ensino.yml` | docência, minicursos, materiais didáticos, dados e código |
   | `curriculo.yml` | formação, bolsas, atuação acadêmica, prêmios e formação complementar |
   | `site.yml` | data de atualização, menu e textos fixos da interface |

   Cada texto tem uma versão `pt` e outra `en`. Nos textos, `*assim*` vira itálico e `[texto](endereço)` vira link.
2. Atualize `atualizado:` em `_fonte/dados/site.yml`.
3. Gere as páginas e os PDFs do currículo (os PDFs precisam do Edge ou do Chrome):

   ```
   pip install -r _fonte/requisitos.txt pymupdf
   python _fonte/construir.py --pdf
   ```

4. Confira os links internos e se as páginas correspondem aos dados:

   ```
   python _fonte/construir.py --verificar
   ```

5. Faça commit e push. O GitHub Pages publica em cerca de um minuto, e o GitHub Actions repete a verificação a cada push (`.github/workflows/verificar.yml`).

## Regras de conteúdo

- Manuscritos em avaliação aparecem só com título, autores e situação, sem periódico e sem resumo. O resumo entra depois da publicação ou como preprint.
- Manuscrito em coautoria só entra com o acordo de todos os coautores.
- Resultados de pesquisa com bolsa FAPESP levam o número do processo e o aviso de responsabilidade (já estão nos modelos).
- O repositório é público, inclusive o histórico: não publique dados reais de pesquisa, microdados de terceiros (como os do PELA-USAL) nem pareceres.

## Estrutura

- `_fonte/`: gerador (`construir.py`), modelos HTML (`modelos/`), dados (`dados/`) e o script das imagens fixas (`gerar_imagens.py`).
- `assets/`: estilo, foto, ícones e cartão de compartilhamento.
- `resources/`: materiais didáticos, sob CC BY 4.0.
- Páginas geradas: `index.html`, `research.html`, `thesis.html`, `publications.html`, `teaching.html` e `cv.html`, as mesmas em `pt/`, além de `404.html`, `sitemap.xml`, `robots.txt`, `cv.pdf` e `pt/cv.pdf`. Os endereços antigos `work-in-progress.html`, `data-code.html` e `service.html` redirecionam para os novos.
