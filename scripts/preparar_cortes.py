"""
Prepara os cortes definidos em projeto.json -> cortes/<nome>.json (segmentos da live + transcrição), com:
  1. transcrição por palavra só das janelas usadas (faster-whisper, cache em 03_analise/)
  2. corte de respiros (cortar_respiros + refinar_respiros, padrão REF11: gap 0,25 / pre 0,06 / pos 0,09)
  3. emendas levadas para o silêncio dos DOIS lados (R-025) — sem silêncio = emenda desfeita
  4. QA: emendas, planos-fragmento, e o TEXTO COMPLETO da legenda de cada corte para revisão (R-026)

Uso: python preparar_cortes.py --projeto P [--so CORTE] [--sem_transcrever]

Cada item de projeto.json["cortes"]:
  {"nome": "corte1_tema", "titulo": [["LINHA 1", "branco"], ["LINHA 2", "branco"], ["LINHA 3.", "verde"]],
   "trechos": [[ini_s, fim_s], ...],           # tempos ABSOLUTOS na live (segundos); trechos distantes viram
                                                # momentos separados com flash entre eles
   "destaques": ["palavra", ...], "punch_palavras": ["palavra", ...],
   "inicio_fala": 1085.46,                     # opcional: ataque da 1ª palavra medido na energia
   "palavras_manuais": [{"faixa": [a, b], "palavras": [{"p": "x", "i": t0, "f": t1}]}],   # opcional
   "segmentos_manuais": [{"ini": a, "fim": b}, ...]}   # opcional: substitui o corte automático de respiros
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # acha _base.py mesmo com python -I
import _base
from _base import LIB, carregar_projeto

LIM_DB = -40.0     # silêncio para a emenda (dBFS RMS em 40 ms)
QA_DB = -38.0


def energia(live, a0, a1):
    y = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a0:.3f}", "-i", str(live), "-t", f"{a1 - a0:.3f}",
                                      "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True).stdout, np.float32)
    h = 160
    e = 20 * np.log10(np.sqrt((y[:len(y) // h * h].reshape(-1, h) ** 2).mean(1)) + 1e-9)
    return lambda t: float(e[max(0, int((t - a0) * 100) - 2):int((t - a0) * 100) + 2].max())


def ajustar_emendas(S, live):
    """Fim anda para dentro da pausa até o silêncio, início recua até o silêncio; sem silêncio entre os dois ->
    emenda desfeita. Plano < 0,25 s é fundido ao seguinte. Salto > 3 s (outro momento) só garante silêncio."""
    a0, a1 = min(x["ini"] for x in S) - 1, max(x["fim"] for x in S) + 1
    db = energia(live, a0, a1)
    S = [dict(x) for x in S]
    k = 0
    while k < len(S) - 1:
        if S[k]["fim"] - S[k]["ini"] < 0.25:
            extra = {kk: vv for kk, vv in S[k].items() if kk not in ("ini", "fim")}
            S[k + 1]["ini"] = S[k]["ini"]
            S[k + 1].update(extra)
            del S[k]
            continue
        k += 1
    out = [S[0]]
    for nx in S[1:]:
        cur = out[-1]
        if abs(nx["ini"] - cur["fim"]) <= 0.004 or nx["ini"] < cur["fim"] - 0.004 or nx["ini"] - cur["fim"] > 3.0:
            if nx["ini"] - cur["fim"] > 3.0:
                t = cur["fim"]
                while db(t) > LIM_DB and t < cur["fim"] + 0.6:
                    t += 0.01
                cur["fim"] = round(t + 0.02, 3)
                t = nx["ini"]
                while db(t) > LIM_DB and t > nx["ini"] - 0.6:
                    t -= 0.01
                nx["ini"] = round(t - 0.02, 3)
            out.append(nx)
            continue
        f, i = cur["fim"], nx["ini"]
        while db(f) > LIM_DB and f < i:
            f += 0.01
        while db(i) > LIM_DB and i > f:
            i -= 0.01
        if i - f < 0.05:
            cur["fim"] = nx["fim"]
            continue
        cur["fim"] = round(min(f + 0.03, i), 3)
        nx["ini"] = round(max(i - 0.03, cur["fim"]), 3)
        out.append(nx)
    return out


def qa_emendas(S, live):
    a0, a1 = min(s["ini"] for s in S) - 1, max(s["fim"] for s in S) + 1
    db = energia(live, a0, a1)
    ruins = []
    for k, s in enumerate(S):
        if s["fim"] - s["ini"] < 0.25:
            ruins.append(f"plano curto {s['ini']:.2f}-{s['fim']:.2f}")
        if k + 1 < len(S) and abs(S[k + 1]["ini"] - s["fim"]) > 0.004:
            eo, ei = db(s["fim"] - 0.02), db(S[k + 1]["ini"] + 0.02)
            if eo > QA_DB or ei > QA_DB:
                ruins.append(f"emenda {s['fim']:.2f}->{S[k + 1]['ini']:.2f}: saída {eo:.0f} dB, entrada {ei:.0f} dB")
    return ruins


def janelas(trechos, folga=8.0, juntar=30.0):
    tr = sorted([list(map(float, t)) for t in trechos])
    grupos = [[tr[0]]]
    for t in tr[1:]:
        if t[0] - grupos[-1][-1][1] <= juntar:
            grupos[-1].append(t)
        else:
            grupos.append([t])
    return [(max(0.0, g[0][0] - folga), g[-1][1] + folga, g) for g in grupos]


_modelo = {}


def transcrever(wav, saida, modelo):
    from faster_whisper import WhisperModel
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(wav), "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    audio = np.frombuffer(pcm, dtype=np.float32)
    if modelo not in _modelo:
        print(f"  carregando Whisper {modelo} (1ª vez baixa o modelo, ~1,6 GB)...", flush=True)
        _modelo[modelo] = WhisperModel(modelo, device="cpu", compute_type="int8")
    segments, info = _modelo[modelo].transcribe(audio, language="pt", word_timestamps=True, vad_filter=False, beam_size=5)
    data = {"idioma": info.language, "duracao": info.duration, "segmentos": []}
    for s in segments:
        data["segmentos"].append({"inicio": round(s.start, 3), "fim": round(s.end, 3), "texto": s.text.strip(),
                                  "palavras": [{"p": w.word.strip(), "i": round(w.start, 3), "f": round(w.end, 3),
                                                "conf": round(w.probability, 3)} for w in s.words]})
    json.dump(data, open(saida, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--projeto", required=True)
    ap.add_argument("--so", default=None, help="prepara só este corte (nome)")
    a = ap.parse_args()
    P = carregar_projeto(a.projeto)
    proj, live = P["_dir"], P["_live"]
    ana = proj / "03_analise"
    ana.mkdir(parents=True, exist_ok=True)
    (proj / "cortes").mkdir(exist_ok=True)
    import corte_live as CL
    CL.configurar(proj)
    for C in P.get("cortes", []):
        if a.so and C["nome"] != a.so:
            continue
        print(f"\n=== {C['nome']}")
        segs, transc = [], []
        for wi, (w0, w1, grupo) in enumerate(janelas(C["trechos"])):
            tag = f"{int(w0)}_{int(w1)}"
            wav, tj = ana / f"janela_{tag}.wav", ana / f"transcricao_{tag}.json"
            if not wav.exists():
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{w0:.3f}", "-i", str(live), "-t", f"{w1 - w0:.3f}",
                                "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)], check=True)
            if not tj.exists():
                print(f"  transcrevendo {w0:.0f}-{w1:.0f}s ...", flush=True)
                transcrever(wav, tj, P.get("whisper_modelo", "large-v3-turbo"))
            transc.append({"arquivo": f"03_analise/{tj.name}", "offset": round(w0, 3)})
            if C.get("segmentos_manuais"):
                continue
            rel = ",".join(f"{t[0] - w0:.2f}-{t[1] - w0:.2f}" for t in grupo)
            cj, cf = ana / f"cortes_{C['nome']}_{tag}.json", ana / f"cortes_fino_{C['nome']}_{tag}.json"
            subprocess.run([sys.executable, str(LIB / "cortar_respiros.py"), str(tj), str(wav), str(cj), "--gap", "0.25",
                            "--pre", "0.06", "--pos", "0.09", "--trechos", rel], check=True)
            subprocess.run([sys.executable, str(LIB / "refinar_respiros.py"), str(cj), str(wav), str(cf)], check=True)
            R = json.load(open(cf, encoding="utf-8"))
            for k, (x0, x1) in enumerate(R["segmentos"]):
                s = {"ini": round(x0 + w0, 3), "fim": round(x1 + w0, 3)}
                if k == 0 and wi > 0:
                    s["transicao"] = "flash"      # outro momento da live
                segs.append(s)
        if C.get("segmentos_manuais"):
            segs = [dict(s) for s in C["segmentos_manuais"]]
        segs = ajustar_emendas(segs, live)
        if C.get("inicio_fala"):
            segs[0]["ini"] = C["inicio_fala"]
        out = {k: v for k, v in C.items() if k not in ("trechos", "segmentos_manuais")}
        out.update({"segmentos": segs, "transcricoes": transc})
        cpath = proj / "cortes" / f"{C['nome']}.json"
        json.dump(out, open(cpath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        ruins = qa_emendas(segs, live)
        Cc, sg, tf, end, pal = CL.carregar(cpath)
        print(f"  {len(segs)} trechos -> {len(sg)} planos, {tf:.1f}s de fala + {end}s end card -> {cpath.name}")
        print("  QA emendas (R-025):", "ok" if not ruins else "; ".join(ruins))
        print("  LEGENDA COMPLETA (leia contra a fala — R-026):")
        print("   ", " ".join(w["p"] for w in pal))


if __name__ == "__main__":
    main()
