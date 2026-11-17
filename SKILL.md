---
name: cortes-live-igreen
description: Transforma uma live horizontal (16:9, YouTube/StreamYard) da iGreen em cortes Reels/TikTok/Shorts 9:16 no padrão aprovado pelo cliente — título no topo, live num card arredondado com borda neon sobre o background da marca, crédito do porta-voz, legenda dinâmica minúscula, end card com o logotipo oficial — e entrega MP4 + dois drafts no CapCut (fiel e editável). Também mapeia a live inteira e escolhe os melhores momentos pela ótica do Licenciado iGreen (ganhos financeiros, campanhas, novidades e oportunidades de mercado, carreira/liderança, valores). Use SEMPRE que alguém pedir cortes, recortes, "melhores momentos" ou "o que vale cortar" de uma live/transmissão/webinar/evento da iGreen, quiser replicar cortes de referência (vídeos de terceiros da mesma live), mencionar "corte de live", "reels da live", "live em formato reels", "título em cima e vídeo no meio", ou quiser reproduzir/atualizar os cortes da live de lançamentos de 14/11 — mesmo sem dizer "skill" ou "CapCut".
---

# Cortes de live iGreen (formato card 9:16)

Esta skill produz cortes **idênticos** aos aprovados pelo cliente na live de lançamentos de 14/11/2026: mesmo layout,
mesmas fontes, mesmo background, mesma trilha, mesmos níveis de áudio, mesmos drafts no CapCut. A identidade visual
está congelada no motor (`scripts/corte_live.py` + `scripts/_base.py`) — não reescreva o motor nem "melhore" o visual
por conta própria: o que está lá foi decidido pelo cliente em 3 rodadas de feedback (ver `references/regras_cliente.md`).

`<skill>` abaixo = a pasta deste SKILL.md. Rode tudo com o Python 3.12 da máquina: `python "<skill>/scripts/X.py" ...`.

## 0. Antes de tudo (1 min)
```
python "<skill>/scripts/checar_ambiente.py"
```
Se algo vier `FALTA`, resolva antes (ver `INSTALAR.md`). `DIFERENTE` funciona, mas pode mudar pixels — avise o usuário.

## 1. Projeto novo
```
python "<skill>/scripts/novo_projeto.py" --nome cortes-live-<tema> --live "<vídeo da live>" --destino "<pasta PROJETOS>" --data DD/MM
```
Cria `AAAA-MM-DD_HHhMM_<nome>/` com `projeto.json`. Preencha no `projeto.json`: `eyebrow`/`end_sub` (data da live),
`credito` (nome em CAIXA ALTA + cargo — padrão Thiago Alexander / Presidente da iGreen) e a lista `cortes`.
Tudo que não estiver lá usa o padrão iGreen (`_base.PADRAO`): background, logo, trilha, layout de recorte, estilos.

**Para reproduzir os 4 cortes de 14/11** (só no pacote interno do time — a pasta não vai para o GitHub público): copie
`<skill>/exemplo_live_2026-11-14/` para a pasta de projetos, ponha o caminho da `LIVE SÁBADO.mp4` em
`projeto.json["live"]` e vá direto ao passo 5 (os `cortes/*.json` já estão prontos).
A trilha da casa (`assets/musica/`) também vem só no pacote interno; sem ela o render para e pede a trilha.

## 2. Achar os momentos (curadoria pela ótica do Licenciado)
Somos o time de Marketing da iGreen e o objetivo é o **sucesso do LICENCIADO**: cada corte tem que motivá-lo a ganhar
dinheiro e a aproveitar oportunidades. Prioridade: ganho financeiro concreto → promoção/campanha com prazo →
novidade/oportunidade de mercado → carreira/liderança → valores. Critérios, checklist e alertas:
**leia `references/curadoria_igreen.md` antes de escolher**.
- **Sem referência (o caso normal)**: mapeie a live inteira e escolha você os momentos:
  `python "<skill>/scripts/mapear_momentos.py" --projeto P` → `03_analise/momentos_candidatos.md` (ranking por tema) +
  `transcricao_completa.txt` (contexto). Leia, pontue com o checklist, varie os temas e — se o usuário não definiu os
  temas — mostre a lista curta (minuto, gancho, título proposto, por que motiva) antes de cortar.
- **Com vídeos de referência** (cortes de terceiros da mesma live):
  `python "<skill>/scripts/localizar_referencias.py" --projeto P --refs "<pasta das refs>"` → minuto exato de cada ref.
  Seja fiel ao TEMA de cada referência, mas comece no gancho mais forte e termine em frase completa. Vale rodar também o
  mapeamento para sugerir cortes extras que as referências não pegaram.
- Se o título promete algo que a fala do trecho não diz (ex.: "300 clientes em 40 dias"), anexe o trecho em que ele
  diz isso (outro momento da live = segundo item em `trechos`; entra com flash) ou mude o título. Grafismo/título só
  com a fala presente.

Para cada corte, preencha em `projeto.json["cortes"]`:
```json
{"nome": "corte1_licenciado-novo-10-clientes",
 "titulo": [["LICENCIADO NOVO:", "branco"], ["10 CLIENTES E", "branco"], ["A LICENÇA VOLTA.", "verde"]],
 "trechos": [[663.9, 699.5]],
 "destaques": ["clientes", "volta", "dinheiro"], "punch_palavras": ["volta", "1.997", "997,00"]}
```
Título: 3 linhas curtas, escrito já em CAIXA ALTA à mão (o motor não força caixa — assim "iGreen" fica "iGreen"),
última linha em verde = a promessa/número. Linhas de largura parecida (uma linha longa encolhe o bloco inteiro).
Números são destacados em verde automaticamente; `destaques` acrescenta palavras; 3 `punch_palavras` por corte.

## 3. Conferir o recorte da transmissão
```
python "<skill>/scripts/medir_layout.py" --projeto P --tempos <2-4 tempos dentro dos trechos>
```
Abra `03_analise/layout_check.jpg`. A área verde (a usada) não pode pegar a plaquinha de nome, o logo da transmissão
nem o convidado. O padrão serve para as lives iGreen no StreamYard 1280×720 (tela dividida e tela cheia, detectadas
quadro a quadro). Outro layout → ajuste `projeto.json["layout_live"]` (áreas 16:9 em px da live) e confira de novo.

## 4. Preparar os cortes (transcrição + respiros + emendas)
```
python "<skill>/scripts/preparar_cortes.py" --projeto P
```
Gera `cortes/<nome>.json`. **Leia a LEGENDA COMPLETA que ele imprime de cada corte, contra a fala**:
- falta palavra (sobretudo número), ou entrou palavra da frase vizinha na borda → `palavras_manuais` com os tempos
  cravados na energia do áudio (como fazer: `references/armadilhas.md`);
- grafia errada (marca, nome, verbo) → `projeto.json["legenda_corrigir"]` / `nomes_proprios`;
- `QA emendas` precisa dizer `ok` (toda emenda em silêncio dos dois lados; nenhum pedaço de palavra).
Rode de novo até ficar limpo (a transcrição fica em cache; só refaz o corte).

## 5. Stills de QA (barato) e render
```
python "<skill>/scripts/corte_live.py" --projeto P cortes/<nome>.json --frames 0.5,8,15,<fim-0.3>
```
Olhe os PNGs em `05_render/qa_<nome>/`: título, card, crédito, legenda (nada colado, nada sobre a borda), end card.
Depois, com o **CapCut fechado**:
```
python "<skill>/scripts/renderizar.py" --projeto P --versao v1
```
Renderiza todos os cortes em paralelo (~15 min para 4 cortes de 30 s), grava os drafts e imprime
loudness + `05_render/folha_v1.jpg`. Abra a folha e confira. Cada revisão = nova versão (`v2`, `v3`…): nunca
sobrescreva um draft que o cliente editou à mão.
Se o CapCut precisar ficar aberto durante o render: `--sem_drafts` agora e, com ele fechado, `--so_drafts` depois
(grava os drafts sem renderizar de novo).

## 6. Entrega
Diga ao usuário: nomes dos drafts (`..._vN` = FIEL, igual ao MP4; `..._vN_nativo` = editável), onde estão os MP4
(`05_render/`), duração de cada corte e o que não foi verificado. Lembre:
- **fechar e reabrir o CapCut** para os projetos aparecerem;
- se a imagem parecer borrada **no CapCut**, é a prévia do player (até o texto vetorial borra): player em qualidade
  alta/original; exportar 1080p, 30 fps, taxa de bits mais alta. O arquivo tem a qualidade da live.

## Quando o cliente ajustar um draft à mão
Leia o `draft_content.json` do draft editado (em `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft\<nome>`),
compare com a cópia gerada em `06_capcut/<nome>_draft_content.json` (posições `clip.transform`, tamanhos, cores) e
transforme a diferença em constante do motor — não refaça no olho. Gere nova versão para todos os cortes. Em seguida
proponha atualizar esta skill (as constantes ficam em `scripts/corte_live.py`, bloco "diagramação aprovada").

## Regras que não mudam sem pedido do cliente
Resumo (detalhes e números em `references/padrao_visual.md`):
- nenhum texto com sombra ou glow; títulos Anton 82 @1080; legenda Montserrat Bold 53 px (12,7 no CapCut), destaque
  só pela cor verde (mesmo tamanho);
- legenda em minúsculas, exceto nomes próprios/marcas; "não" em branco (nunca vermelho); máx. 3 palavras por bloco;
- end card com o logotipo oficial (`assets/logos`), nunca "iGreen" digitado; "iGreen" nunca vira "IGREEN";
- áudio: nenhuma emenda no meio de palavra, nenhum fade em emenda contínua, trilha rock −22 dB/duck −12, master −14 LUFS;
- nenhum texto fora da área segura (o render aborta se acontecer — trava R-024);
- câmera sempre no porta-voz; sem material depois da última palavra.

## Arquivos
- `scripts/` — `novo_projeto`, `mapear_momentos` (curadoria), `localizar_referencias`, `medir_layout`, `preparar_cortes`, `corte_live` (motor),
  `capcut_fiel`, `capcut_nativo`, `renderizar` (tudo de uma vez), `checar_ambiente`; `lib/` = motor-base iGreen e a
  biblioteca de drafts do CapCut (pyJianYingDraft) já configurada para o CapCut 9.
- `assets/` — background, logos oficiais, fontes, trilha da casa.
- `references/curadoria_igreen.md` (missão, temas, checklist e títulos — leia no passo 2),
  `references/padrao_visual.md` (números do layout), `references/armadilhas.md` (o que deu errado e como evitar),
  `references/regras_cliente.md` (feedbacks do cliente que viraram regra).
- `exemplo_live_2026-11-14/` — os 4 cortes aprovados, prontos para re-renderizar.
