"""
Mapeia a live INTEIRA e ranqueia os melhores momentos para cortes, pela ótica do LICENCIADO iGreen
(ganho financeiro e novas oportunidades primeiro — ver references/curadoria_igreen.md).

Uso: python mapear_momentos.py --projeto P [--blocos 4] [--top 15]
Saída em 03_analise/:
  transcricao_completa.json / .txt   — a live toda com tempo ("[mm:ss] frase"), para ler e confirmar o contexto
  momentos_candidatos.md             — ranking de janelas (~40 s) com nota, temas e o texto de cada uma
A nota é só uma triagem por palavras-chave e números: QUEM DECIDE é a leitura do texto com o guia de curadoria.
"""
import argparse
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import numpy as np

import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # acha _base.py mesmo com python -I
from _base import carregar_projeto

# temas -> (peso, palavras sem acento, minúsculas). Peso reflete a missão: dinheiro e oportunidade primeiro.
TEMAS = {
    "ganho financeiro": (3.0, ["ganhar", "ganha", "ganhou", "ganho", "ganhos", "renda", "rendas", "dinheiro", "bonus",
                               "comissao", "recorrente", "residual", "lucro", "faturar", "fatura", "pix", "cashback",
                               "reais", "receber", "recebe", "paga", "pagar", "pagamento", "salario", "milhao", "milhoes",
                               "bolso", "conta bancaria", "investimento", "retorno", "devolve", "de volta"]),
    "promocao / campanha": (2.5, ["campanha", "promocao", "desafio", "green friday", "gratis", "gratuito", "desconto",
                                  "premio", "premiacao", "viagem", "cruzeiro", "natal", "meta", "valendo", "tabela",
                                  "inedito", "nunca mais", "so ate", "ate dia", "prazo"]),
    "oportunidade / novidade": (2.5, ["novidade", "lancamento", "lancar", "lancando", "novo produto", "aquisicao", "banco",
                                      "aplicativo", "app", "mercado", "oportunidade", "expansao", "estados", "telecom",
                                      "seguro", "energia solar", "mobilidade", "club", "2027", "parceria", "anunciar",
                                      "antecipar", "primeira vez", "jogo gigante", "outro patamar"]),
    "carreira / lideranca": (2.0, ["lider", "lideranca", "equipe", "estrutura", "executivo", "diretor", "gestor", "nivel",
                                   "carreira", "acionista", "licenciado", "licenciados", "indicar", "indica", "rede",
                                   "time", "construir", "crescer", "subir"]),
    "valores / motivacao": (1.5, ["sonho", "familia", "vida", "transformar", "transformada", "historia", "proposito",
                                  "acreditar", "deus", "compromisso", "foco", "disciplina", "conquista", "liberdade",
                                  "futuro", "visao", "orgulho", "ambicao", "fazer historia", "mudar de vida"]),
}
RUIDO = ["tira essa tela", "ta me ouvindo", "ta travando", "audio", "microfone", "tela aqui", "volta na tabela",
         "compartilhar a tela", "chat", "comenta ai"]
RE_VALOR = re.compile(r"(r\$\s?\d|\d[\d.,]*\s?(mil|milhao|milhoes|reais|%|por cento))")


def sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def mmss(t):
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:04.1f}" if t >= 3600 else f"{int(t // 60)}:{t % 60:04.1f}"


def transcrever_bloco(live, t0, t1, saida, modelo):
    from faster_whisper import WhisperModel
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-i", str(live), "-t", f"{t1 - t0:.3f}", "-vn",
                          "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True, check=True).stdout
    audio = np.frombuffer(pcm, np.float32)
    m = WhisperModel(modelo, device="cpu", compute_type="int8")
    segs, _ = m.transcribe(audio, language="pt", vad_filter=True, beam_size=1, word_timestamps=False)
    out = [{"i": round(s.start + t0, 2), "f": round(s.end + t0, 2), "t": s.text.strip()} for s in segs]
    json.dump(out, open(saida, "w", encoding="utf-8"), ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--projeto", required=True)
    ap.add_argument("--blocos", type=int, default=4)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--janela", type=float, default=40.0)
    ap.add_argument("--_bloco", nargs=3, type=float, help=argparse.SUPPRESS)
    a = ap.parse_args()
    P = carregar_projeto(a.projeto)
    ana = P["_dir"] / "03_analise"
    ana.mkdir(parents=True, exist_ok=True)
    modelo = P.get("whisper_modelo", "large-v3-turbo")
    if a._bloco:   # processo filho
        k, t0, t1 = a._bloco
        transcrever_bloco(P["_live"], t0, t1, ana / f"_bloco_{int(k)}.json", modelo)
        return
    tj = ana / "transcricao_completa.json"
    if not tj.exists():
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                    str(P["_live"])], capture_output=True, text=True).stdout.strip())
        # blocos com 3 s de sobreposição (frase cortada na borda aparece inteira em um dos dois)
        cortes = np.linspace(0, dur, a.blocos + 1)
        print(f"transcrevendo {mmss(dur)} em {a.blocos} blocos paralelos (Whisper {modelo}, VAD)...", flush=True)
        procs = [subprocess.Popen([sys.executable, __file__, "--projeto", str(P["_dir"]), "--_bloco", str(k),
                                   str(max(0, cortes[k] - 3)), str(cortes[k + 1])]) for k in range(a.blocos)]
        for p in procs:
            p.wait()
        frases = []
        for k in range(a.blocos):
            for s in json.load(open(ana / f"_bloco_{k}.json", encoding="utf-8")):
                if frases and s["i"] < frases[-1]["f"] - 0.5 and sem_acento(s["t"])[:20] in sem_acento(frases[-1]["t"]):
                    continue  # duplicada na sobreposição
                frases.append(s)
            (ana / f"_bloco_{k}.json").unlink()
        frases.sort(key=lambda s: s["i"])
        json.dump(frases, open(tj, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        with open(ana / "transcricao_completa.txt", "w", encoding="utf-8") as f:
            for s in frases:
                f.write(f"[{mmss(s['i'])}] {s['t']}\n")
    frases = json.load(open(tj, encoding="utf-8"))
    # janelas deslizantes (passo 10 s) -> nota por tema + valores em dinheiro - ruído
    fim = frases[-1]["f"]
    cands = []
    t = 0.0
    while t < fim:
        fr = [s for s in frases if s["i"] >= t and s["f"] <= t + a.janela]
        if fr:
            txt = sem_acento(" ".join(s["t"] for s in fr))
            nota, temas = 0.0, {}
            for tema, (peso, pals) in TEMAS.items():
                n = sum(len(re.findall(r"\b" + re.escape(p) + r"\b", txt)) for p in pals)
                if n:
                    temas[tema] = n
                    nota += peso * min(n, 6)
            valores = len(RE_VALOR.findall(txt))
            nota += 2.0 * min(valores, 5)
            nota -= 3.0 * sum(txt.count(r) for r in RUIDO)
            nota *= min(1.0, len(txt.split()) / 60)     # janela com pouca fala vale menos
            cands.append({"t0": fr[0]["i"], "t1": fr[-1]["f"], "nota": round(nota, 1), "temas": temas,
                          "valores": valores, "texto": " ".join(s["t"] for s in fr)})
        t += 10.0
    cands.sort(key=lambda c: -c["nota"])
    escolhidos = []
    for c in cands:
        if all(c["t1"] < e["t0"] - 5 or c["t0"] > e["t1"] + 5 for e in escolhidos):
            escolhidos.append(c)
        if len(escolhidos) >= a.top:
            break
    md = ana / "momentos_candidatos.md"
    with open(md, "w", encoding="utf-8") as f:
        f.write("# Momentos candidatos (triagem automática — confirme lendo o texto e o contexto)\n\n")
        f.write("Critérios: references/curadoria_igreen.md. Contexto completo: transcricao_completa.txt\n\n")
        for k, c in enumerate(escolhidos, 1):
            temas = ", ".join(f"{t} ×{n}" for t, n in sorted(c["temas"].items(), key=lambda x: -x[1]))
            f.write(f"## {k}. {mmss(c['t0'])}–{mmss(c['t1'])}  (nota {c['nota']}, valores em R$/mil: {c['valores']})\n")
            f.write(f"Temas: {temas or '—'}\n\n> {c['texto']}\n\n")
    print(f"{len(frases)} frases transcritas -> {tj.name} / transcricao_completa.txt")
    print(f"top {len(escolhidos)} momentos -> {md}")
    for k, c in enumerate(escolhidos, 1):
        print(f"  {k:2}. {mmss(c['t0']):>8}–{mmss(c['t1']):<8} nota {c['nota']:5.1f}  {c['texto'][:90]}")


if __name__ == "__main__":
    main()
