# Instalar a skill "cortes-live-igreen" em outra máquina

Para quem é: qualquer pessoa do time que vá produzir cortes de live no padrão iGreen com o Claude (app desktop,
aba Code, ou Claude Code no terminal), em Windows com CapCut Desktop 9.x.

## Pré-requisitos (uma vez por máquina)
| item | como instalar | por quê |
|---|---|---|
| Python 3.12 | `winget install Python.Python.3.12` | motor de render e pontes do CapCut |
| FFmpeg 9 "full" (gyan.dev) | `winget install Gyan.FFmpeg` e reabrir o terminal | leitura da live, encode, loudness |
| CapCut Desktop 9.x | site oficial; abrir uma vez | cria a pasta de projetos onde os drafts entram |
| Claude (app desktop ou Claude Code) | — | é quem executa a skill |

## Instalação
1. Descompacte `cortes-live-igreen.zip` em qualquer pasta.
2. Na pasta descompactada, clique com o botão direito em `instalar.ps1` › "Executar com o PowerShell"
   (ou no terminal: `powershell -ExecutionPolicy Bypass -File .\instalar.ps1`).
   O instalador: copia a skill para `%USERPROFILE%\.claude\skills\cortes-live-igreen` (vale em qualquer projeto),
   instala as versões exatas dos pacotes Python (`requirements.txt`) e roda a checagem do ambiente.
3. A checagem precisa terminar com `RESULTADO: pronto`. Itens `DIFERENTE` funcionam, mas podem mudar pixels; para
   ficar idêntico, instale as mesmas versões indicadas.
4. A 1ª transcrição baixa o modelo Whisper (~1,6 GB) automaticamente. Depois fica em cache.

Atualizar = rodar o `instalar.ps1` da versão nova (a anterior fica em `...\cortes-live-igreen.bak_<data>`).

## Conferir que ficou idêntico (5 min por corte)
1. Copie `exemplo_live_2026-11-14` (dentro da skill instalada) para a sua pasta de projetos.
2. No `projeto.json` copiado, troque `"live"` pelo caminho da `LIVE SÁBADO.mp4` (live de lançamentos de 14/11).
3. Feche o CapCut e rode (troque `<skill>` e `<projeto>` pelos caminhos):
   ```
   python "<skill>\scripts\renderizar.py" --projeto "<projeto>" --versao vteste
   python "<skill>\scripts\verificar_identico.py" "<projeto>\05_render\corte1_licenciado-novo-10-clientes.mp4" "<projeto>\05_render\corte2_50-clientes-tres-rendas.mp4" "<projeto>\05_render\corte3_igreen-comprando-um-banco.mp4" "<projeto>\05_render\corte4_pix-30-mil-no-natal.mp4" --conferir --ref "<skill>\exemplo_live_2026-11-14\referencia_aprovada.json"
   ```
   `IDÊNTICO` = bit a bit igual à versão aprovada pelo cliente (v4); `EQUIVALENTE` = diferença invisível (versão de
   pacote/ffmpeg diferente); `DIFERENTE` = algo errado na instalação.

## Como usar no dia a dia
No Claude, dentro da pasta de trabalho, peça em português normal, por exemplo:
- "Faça 3 cortes da live de ontem (C:\...\live.mp4) no padrão iGreen, um sobre o novo bônus, um sobre..."
- "Tenho 4 vídeos de referência em C:\...\refs — faça os mesmos cortes a partir da live completa."
A skill cuida do resto e entrega MP4 + drafts `..._vN` (fiel) e `..._vN_nativo` (editável) no CapCut.

## Problemas comuns
- **Draft não aparece no CapCut** → feche e abra o CapCut (ele só relê a lista ao abrir). Nunca grave com ele aberto.
- **Imagem borrada no CapCut** → é a prévia do player; ponha a prévia em qualidade alta e exporte em 1080p.
- **"Mídia ausente" no draft nativo** → a live foi movida de pasta; relinke no CapCut ou rode de novo.
- **Erro de política/Controle de Aplicativo** → não instale rembg/librosa/numba/soxr (bloqueados nas máquinas iGreen).
- **A trilha** (`assets/musica`) é da biblioteca do CapCut: use dentro do CapCut / nos vídeos da iGreen.
