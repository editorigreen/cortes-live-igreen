# cortes-live-igreen

Skill do Claude (Claude Code / app Claude desktop) que transforma uma **live horizontal da iGreen** em **cortes verticais
para Reels, TikTok e Shorts** no padrão visual aprovado pelo time de Marketing da iGreen, e entrega o resultado como MP4
e como projeto no CapCut.

O objetivo de cada corte é o **sucesso do Licenciado iGreen**: a skill mapeia a live inteira e escolhe os momentos que
mais motivam o Licenciado a ganhar dinheiro e aproveitar novas oportunidades (ganhos, campanhas, novidades,
carreira, valores).

## O que ela entrega
- Curadoria: transcrição da live inteira + ranking dos melhores momentos pela ótica do Licenciado.
- Corte: transcrição por palavra, remoção de respiros com emendas sempre em silêncio, legenda dinâmica minúscula.
- Layout 9:16: título no topo (Anton), a live num card arredondado com borda neon sobre o background da marca, crédito
  do porta-voz, legenda Montserrat, end card com o logotipo oficial.
- Áudio: voz tratada, trilha com ducking, SFX, master −14 LUFS.
- CapCut: draft **fiel** (idêntico ao MP4) e draft **nativo** (tudo editável), já na lista de projetos do CapCut.
- Reprodutível: mesmas versões de pacotes = mesmo resultado bit a bit (`scripts/verificar_identico.py`).

## Requisitos
Windows 10/11 · Python 3.12 · FFmpeg 9 "full" no PATH · CapCut Desktop 9.x · Claude Code ou app Claude desktop.

## Instalação
```powershell
git clone https://github.com/editorigreen/cortes-live-igreen.git
cd cortes-live-igreen
powershell -ExecutionPolicy Bypass -File .\instalar.ps1
```
O instalador copia a skill para `%USERPROFILE%\.claude\skills\cortes-live-igreen`, instala as versões exatas de
`requirements.txt` e roda `scripts\checar_ambiente.py`. Detalhes e problemas comuns: [INSTALAR.md](INSTALAR.md).

**Itens internos (não estão neste repositório público):** a trilha da casa (`assets/musica/`, biblioteca do CapCut) e
o projeto-gabarito da live de 14/11 (`exemplo_live_2026-11-14/`). Eles vêm no pacote interno do time. Sem a trilha, o
render para e pede uma trilha em `projeto.json["musica"]["arquivo"]`.

## Uso
Abra o Claude na pasta de trabalho e peça em português, por exemplo:
> Faça 4 cortes da live de ontem (C:\Lives\live-2026-11-20.mp4) no padrão iGreen.

O roteiro completo que o Claude segue está em [SKILL.md](SKILL.md); o padrão visual em
[references/padrao_visual.md](references/padrao_visual.md) e os critérios de curadoria em
[references/curadoria_igreen.md](references/curadoria_igreen.md).

## Terceiros
- `scripts/lib/capcut_vendor/pyJianYingDraft` — Apache License 2.0 (`LICENSE-pyJianYingDraft-Apache-2.0.txt`).
- Fontes Anton e Montserrat — SIL Open Font License 1.1 (Google Fonts).
- Logotipos e background — marca iGreen Energy; uso restrito às peças da iGreen.
