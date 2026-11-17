# Padrão visual — corte de live iGreen (aprovado v4, 17/11/2026)

Tudo em px de um quadro 1080×1920, 30 fps. Os valores vivem em `scripts/corte_live.py` (constantes no topo) e
`scripts/_base.py` (`PADRAO`). Se mudar algum, mude lá — este arquivo só documenta.

## Camadas (de trás para frente)
1. Background `assets/background_corte_live.png` (verde escuro com brilho neon no topo e na base), redimensionado.
2. Sombra do card (preta, blur 26, deslocada 18 px) + glow neon da borda (blur 14).
3. Card 16:9: x 60–1020 (960×540), y 684–1224, raio 30. Live recortada da área útil (sem plaquinha/logo), zoom
   alternado 1,00 ↔ 1,08 a cada jump cut (+2% de push-in no plano), punch +7% em 0,18 s nas `punch_palavras`,
   nitidez leve (unsharp 1,35/−0,35, σ 1,2). Flash branco 0,18 s no card ao trocar de momento da live.
4. Borda neon #1EFF2E (alpha 205), 2,5 px.
5. Eyebrow: ponto verde Ø12 + "LIVE OFICIAL iGreen  ·  DD/MM", Montserrat 700, 28 px, tracking 8, cinza #C9D2CB,
   centro do glifo em y 259, alinhado à esquerda em x 60.
6. Título: Anton, 82 px (reduz para a linha mais larga caber em 84% da largura — mesmo corpo para todas as linhas),
   branco #F3F5F2, última linha verde #1EFF2E, entrelinha = cap height × 1,36, pé da última linha a 52 px do card,
   alinhado à esquerda em x 60. Entra com fade de 0,35 s.
7. Crédito, centralizado, centro em y 1279: "NOME" Montserrat 800 30 px tracking 5 verde + "|" cinza #8E9A91 +
   "Cargo" Montserrat 600 30 px branco.
8. Legenda: centro da 1ª linha em y 1440 (0,75 H). Montserrat 700 (Bold), 53,25 px (= 12,7 no CapCut), branco;
   destaque com o MESMO corpo e peso, só em verde #1EFF2E (números automáticos + `destaques`) — ajuste do cliente. Máx. 3 palavras por bloco, palavra a palavra com pop (0,16 s),
   espaço entre palavras 0,34 do corpo, linha ≤ 84% da largura. Sem sombra, sem contorno, sem glow.
9. End card (1,8 s): background + logotipo oficial verde-claro 600 px de largura (topo em y 768), linha neon
   120×6 px 48 px abaixo, "LIVE OFICIAL  ·  DD/MM" Montserrat 700 32 px tracking 10 cinza, fade de entrada 0,25 s.

## Áudio
Voz da live com EQ de broadcast (`sfx.eq_voz`), fades de 12 ms só em emendas descontínuas. Trilha
`assets/musica/action_sport_motivational_rock.mp3` a −22 dB com duck −12 dB (sobe nas pausas), fade-in 0,2 s,
fade-out 1,6 s. SFX: whoosh no início (−16), boom nos punches (−17), whoosh antecipando o flash (−14), ding no end
card (−15). Master loudnorm −14 LUFS / −1 dBTP, AAC 256 kbps.

## Vídeo
x264 CRF 16 (MP4 final) e CRF 14 (base do draft FIEL), yuv420p, bt709, 1080×1920 30 fps.

## Drafts no CapCut
- FIEL `<data>_<projeto>_<corte>_vN`: base sem textos + PNGs (título/crédito/end card e cada estado da legenda,
  pop por keyframe) + voz/música (níveis do master) + SFX. Abre idêntico ao MP4.
- NATIVO `..._vN_nativo`: live original em trechos com keyframes de escala/posição (zoom/punch), PNG do background
  com "furo" arredondado + borda (cantos exatos), textos nativos (corpo = px/4,2; letter_spacing = tracking/5 —
  unidade do CapCut é 0,05 em), legenda em um texto por bloco com faixas verdes, logo como imagem, música, SFX.
  O eyebrow nativo fica em x −0,272 (o CapCut o desenha mais largo que o PIL; posição aprovada pelo cliente).

## Recorte da transmissão (padrão StreamYard iGreen 1280×720)
- Tela dividida (Thiago + convidado): área útil (68, 193, 516×290) — sem a plaquinha de nome (y ≥ 488).
- Tela cheia: área útil (0, 0, 1120×630) — sem plaquinha (y ≥ 662) e sem o logo (x ≥ 1126).
- Classificação por quadro: luma média da faixa y 0–170, x 0–1000 < 25 → tela dividida (fundo preto/verde da
  transmissão); senão tela cheia.
