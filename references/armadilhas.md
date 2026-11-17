# Armadilhas (o que já deu errado e como a skill evita)

## Áudio / emendas
- **Pedaço de palavra na emenda.** O corte de respiros pela transcrição deixava a cauda da palavra (−20 a −36 dB) ou
  o começo da próxima. `preparar_cortes.py` leva cada emenda para o silêncio (< −40 dB em 40 ms) dos dois lados; se não
  há silêncio entre as duas falas, a emenda é desfeita. O QA mede de novo (< −38 dB) e lista o que sobrar.
- **Plano-fragmento** (< 0,25 s) vira "piscada" no vídeo: é fundido ao plano seguinte.
- **Silêncio morto no gancho.** Se o 1º trecho começa ~0,5 s antes da primeira palavra, use `inicio_fala` com o ataque
  medido na energia (passo a passo abaixo).
- **Fala colada sem pausa** (ex.: "...dezembro, a gente está falando de 40 dias"): não dá para cortar no meio. Prefira
  outra ocorrência da mesma frase que tenha silêncio dos dois lados (o Thiago repete muito) ou mantenha a frase inteira.
- Nunca fade em emenda contínua (o motor só faz fade de 12 ms em emenda descontínua).

## Legenda / Whisper
- O Whisper **estica palavras por cima das pausas** e **adianta o início depois de pausa**. Mapear palavra → trecho pelo
  ponto médio derrubava palavras ("30" de "30 mil") e criava fantasmas ("Então," da frase seguinte). O motor usa a maior
  sobreposição + regra assimétrica, mas SEMPRE leia o texto completo que `preparar_cortes.py` imprime.
- Palavra com duração zero ("dinheiro.") ganha 0,12 s automaticamente.
- Valores quebrados ("R", "$", "1", ".997,") são juntados em "R$ 1.997,".
- **Como cravar tempos (`palavras_manuais`)**: meça a energia RMS em passos de 10 ms ao redor do trecho
  (`ffmpeg -ss A -i live -t 2 -ac 1 -ar 16000 -f f32le -` → numpy, 160 amostras por passo). Fala ≈ −25 a −10 dB,
  silêncio < −60 dB. Atenção ao rótulo de tempo: passo de 10 ms = `a + i*0.01` (rotular com 0,02 dobra o erro).
  Depois: `{"faixa": [a, b], "palavras": [{"p": "validar", "i": 1231.86, "f": 1232.60}, ...]}` substitui tudo que o
  Whisper pôs dentro da faixa; `"palavras": []` só remove.
- Legenda minúscula exceto nomes próprios: amplie `nomes_proprios` no projeto quando aparecer um nome novo
  (pessoa, cidade, produto).

## Layout
- Live com tela dividida E tela cheia no mesmo arquivo: o recorte é decidido quadro a quadro; confira com
  `medir_layout.py` em tempos dos dois tipos.
- Zoom num painel pequeno pegava a plaquinha "Thiago Alexander" cortada ao meio → a área útil já a exclui.
- Título com uma linha muito mais longa encolhe o bloco todo (corpo único). Reescreva em 3 linhas parecidas.

## CapCut
- **Feche o CapCut antes de gravar drafts**: ao fechar, ele reescreve a lista de projetos e o draft novo some. Os
  scripts recusam gravar com o CapCut aberto.
- Tracking em % do corpo ≠ letter_spacing do CapCut (0,05 em por ponto): passar cru esticava o eyebrow/crédito para
  fora do quadro. A ponte converte (tracking/5).
- "Imagem em baixa qualidade no CapCut" = prévia do player. Confirme comparando um quadro do MP4 em 100% com o print;
  oriente a mudar a qualidade da prévia e exportar 1080p/30 fps/taxa alta.
- O draft nativo aponta para o arquivo ORIGINAL da live (sem cópia): se a live mudar de pasta, o CapCut pede para
  relinkar a mídia.

## Ambiente (Windows iGreen)
- rembg, librosa, numba, soxr são bloqueados pelo Controle de Aplicativo — não instale.
- Console em cp1252: os scripts já forçam UTF-8 na saída.
