"""
Acha na live completa o trecho exato de cada vídeo de referência (cortes feitos por terceiros da mesma live),
por correlação de espectrograma (50 quadros/s, 300–3400 Hz) — ~1 min para uma live de 40 min.

Uso: python localizar_referencias.py --projeto P --refs "PASTA_COM_AS_REFS"
Saída: tabela ref -> minuto da live (início/fim) e o mapa de jump cuts; grava 03_analise/mapa_refs.json.
Se uma ref NÃO for da mesma live (score < ~0,35), localize o tema pela transcrição em vez disso.
"""
import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
from scipy.signal import fftconvolve

import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # acha _base.py mesmo com python -I
from _base import carregar_projeto

SR, HOP, NF = 8000, 160, 512


def pcm(path):
    b = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                       capture_output=True, check=True).stdout
    return np.frombuffer(b, np.float32)


def feats(x):
    n = (len(x) - NF) // HOP
    idx = np.arange(NF)[None, :] + HOP * np.arange(n)[:, None]
    sp = np.abs(np.fft.rfft(x[idx] * np.hanning(NF)[None, :], axis=1))[:, 20:110]
    lg = np.log(sp + 1e-4).reshape(n, 30, 3).mean(2)
    lg -= lg.mean(1, keepdims=True)
    return lg.astype(np.float32)


def busca(chunk, Lw):
    c = (chunk - chunk.mean(0)) / (chunk.std(0) + 1e-6)
    n = len(c)
    num = np.zeros(len(Lw) - n + 1)
    for b in range(c.shape[1]):
        num += fftconvolve(Lw[:, b], c[::-1, b], mode="valid")
    e = np.cumsum(np.concatenate([[0], (Lw ** 2).sum(1)]))
    en = np.sqrt(np.maximum(e[n:] - e[:-n], 1e-6))
    return num / (en * np.sqrt((c ** 2).sum()) + 1e-6)


def mmss(t):
    return f"{int(t // 60)}:{t % 60:05.2f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--projeto", required=True)
    ap.add_argument("--refs", required=True)
    a = ap.parse_args()
    P = carregar_projeto(a.projeto)
    fps = SR / HOP
    print("lendo a live...", flush=True)
    L = feats(pcm(P["_live"]))
    L = (L - L.mean(0)) / (L.std(0) + 1e-6)
    res = {}
    refs = sorted(p for p in Path(a.refs).iterdir() if p.suffix.lower() in (".mp4", ".mov", ".m4v", ".webm"))
    for r in refs:
        R = feats(pcm(r))
        sc = busca(R[int(0.3 * fps):int(3.3 * fps)], L)
        g = int(np.argmax(sc))
        lo, hi = max(0, g - int(60 * fps)), min(len(L), g + int(240 * fps))
        W_, H_ = int(1.0 * fps), int(0.25 * fps)
        segs = []
        for st in range(0, len(R) - W_, H_):
            s2 = busca(R[st:st + W_], L[lo:hi])
            k = int(np.argmax(s2))
            if s2[k] < 0.35:
                continue
            t, off = st / fps, round((lo + k) / fps - st / fps, 1)
            if segs and abs(segs[-1][2] - off) < 0.15:
                segs[-1][1] = t + 1.0
            else:
                segs.append([t, t + 1.0, off])
        ini, fim = (segs[0][0] + segs[0][2], segs[-1][1] + segs[-1][2]) if segs else (g / fps, g / fps)
        res[r.name] = {"score": round(float(sc[g]), 3), "live_ini": round(ini, 2), "live_fim": round(fim, 2),
                       "mapa": [[round(x0, 2), round(x1, 2), round(x0 + o, 2)] for x0, x1, o in segs]}
        print(f"{r.name[:50]:50}  score {sc[g]:.2f}  live {mmss(ini)} -> {mmss(fim)}  ({len(segs)} trechos)")
    out = P["_dir"] / "03_analise" / "mapa_refs.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("mapa em", out)


if __name__ == "__main__":
    main()
