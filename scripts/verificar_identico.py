"""
Prova de reprodução idêntica: compara um MP4 renderizado com a impressão digital de referência.

  python verificar_identico.py --gerar  <mp4> [<mp4> ...] --saida referencia.json   # na máquina de referência
  python verificar_identico.py --conferir <mp4> [<mp4> ...] --ref referencia.json   # em qualquer máquina

Compara, em 8 instantes de cada corte, o quadro decodificado (hash exato + diferença média por pixel) e a
loudness integrada. "IDÊNTICO" = todos os hashes iguais; "EQUIVALENTE" = diferença média < 0,5 nível de 255
(invisível; acontece com versões diferentes de ffmpeg/opencv); acima disso = DIFERENTE (investigar).
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # acha _base.py mesmo com python -I
import _base  # noqa: F401

INSTANTES = [0.6, 3.0, 6.0, 9.0, 12.0, 15.0, 18.0, 21.0]


def quadro(mp4, t):
    b = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(mp4), "-frames:v", "1", "-f", "rawvideo",
                        "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return np.frombuffer(b, np.uint8).reshape(1920, 1080, 3)


def lufs(mp4):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(mp4), "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace").stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r)
    return float(m[-1]) if m else None


def impressao(mp4):
    out = {"lufs": lufs(mp4), "quadros": []}
    for t in INSTANTES:
        f = quadro(mp4, t)
        mini = f[::24, ::24].astype(np.uint8)
        out["quadros"].append({"t": t, "md5": hashlib.md5(f.tobytes()).hexdigest(), "mini": mini.flatten().tolist()})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mp4s", nargs="+")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--gerar", action="store_true")
    g.add_argument("--conferir", action="store_true")
    ap.add_argument("--saida")
    ap.add_argument("--ref")
    a = ap.parse_args()
    if a.gerar:
        ref = {Path(m).stem: impressao(m) for m in a.mp4s}
        json.dump(ref, open(a.saida, "w", encoding="utf-8"))
        print("referência gravada:", a.saida, list(ref))
        return
    ref = json.load(open(a.ref, encoding="utf-8"))
    pior = "IDÊNTICO"
    for m in a.mp4s:
        nome = Path(m).stem
        if nome not in ref:
            print(f"{nome}: sem referência")
            continue
        R, X = ref[nome], impressao(m)
        iguais = sum(r["md5"] == x["md5"] for r, x in zip(R["quadros"], X["quadros"]))
        dif = max(float(np.abs(np.array(r["mini"], np.int16) - np.array(x["mini"], np.int16)).mean())
                  for r, x in zip(R["quadros"], X["quadros"]))
        dl = abs((R["lufs"] or 0) - (X["lufs"] or 0))
        est = "IDÊNTICO" if iguais == len(R["quadros"]) and dl < 0.05 else ("EQUIVALENTE" if dif < 0.5 and dl < 0.3 else "DIFERENTE")
        if est == "DIFERENTE" or (est == "EQUIVALENTE" and pior == "IDÊNTICO"):
            pior = est
        print(f"{nome}: {est}  ({iguais}/{len(R['quadros'])} quadros bit a bit, dif. média máx {dif:.2f}/255, "
              f"loudness {X['lufs']} vs {R['lufs']} LUFS)")
    print("RESULTADO:", pior)
    sys.exit(0 if pior != "DIFERENTE" else 1)


if __name__ == "__main__":
    main()
