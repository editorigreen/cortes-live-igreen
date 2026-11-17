"""
Confere o recorte da transmissão ANTES de renderizar: para cada tempo, salva o quadro da live com as áreas
desenhadas (verde = área usada, vermelho = a outra) + a classificação tela dividida / tela cheia.

Uso: python medir_layout.py --projeto P --tempos 665,1090,1830,2085
Saída: 03_analise/layout_check.jpg (abra e olhe). A área usada não pode conter a plaquinha de nome, o logo da
transmissão nem o painel do convidado. Se a live tiver outro layout, ajuste projeto.json["layout_live"]
(área [x, y, largura, altura] em px da live, SEMPRE 16:9) e rode de novo.
"""
import argparse
import subprocess

import numpy as np
from PIL import Image, ImageDraw

import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # acha _base.py mesmo com python -I
from _base import carregar_projeto


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--projeto", required=True)
    ap.add_argument("--tempos", required=True)
    a = ap.parse_args()
    P = carregar_projeto(a.projeto)
    ll = P["layout_live"]
    y0, y1, x0, x1 = ll["faixa_teste"]
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(P["_live"])], capture_output=True, text=True).stdout.strip()
    sw, sh = map(int, probe.split(",")[:2])
    tiles = []
    for t in [float(x) for x in a.tempos.split(",")]:
        b = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(P["_live"]), "-frames:v", "1",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        fr = np.frombuffer(b, np.uint8).reshape(sh, sw, 3)
        luma = fr[y0:y1:4, x0:x1:4].mean()
        div = luma < ll["limiar_dividida"]
        im = Image.fromarray(fr.copy())
        d = ImageDraw.Draw(im)
        for area, usada in ((ll["area_dividida"], div), (ll["area_cheia"], not div)):
            x, y, w, h = area
            d.rectangle([x, y, x + w, y + h], outline=(30, 255, 46) if usada else (255, 60, 60), width=4 if usada else 2)
        d.rectangle([0, 0, 520, 34], fill=(0, 0, 0))
        d.text((8, 8), f"t={t:.1f}s  {'TELA DIVIDIDA' if div else 'TELA CHEIA'}  (luma faixa {luma:.0f})", fill=(255, 255, 255))
        tiles.append(im.resize((640, int(640 * sh / sw))))
    cols = 2
    rows = (len(tiles) + 1) // cols
    th = tiles[0].height
    S = Image.new("RGB", (640 * cols, th * rows))
    for i, im in enumerate(tiles):
        S.paste(im, ((i % cols) * 640, (i // cols) * th))
    out = P["_dir"] / "03_analise" / "layout_check.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    S.save(out, quality=90)
    print(out)


if __name__ == "__main__":
    main()
