"""
Draft FIEL do CapCut: abre exatamente como o MP4 final (vídeo 1080x1920 quase sem perdas + PNGs dos textos).

Uso: python capcut_fiel.py --projeto P --corte <nome_do_corte> --nome "<AAAA-MM-DD_..._vN>"
Pré-requisito: corte_live.py já renderizou o corte (gera 06_capcut/camadas_<nome_do_corte>/).

Trilhas: VIDEO FINAL (sem textos) · LETTERING (título/crédito/end card em PNG) · LEGENDA (um PNG por estado,
com pop de entrada por keyframe) · VOZ · MUSICA (com ducking) · SFX.
"""
import argparse
import json
import wave
from pathlib import Path

import numpy as np

import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # acha _base.py mesmo com python -I
import _base  # noqa: F401
from _base import SKILL
import pyJianYingDraft as draft
from pyJianYingDraft import Clip_settings, Keyframe_property as KP, trange
import sfx as SFX
from capcut_comum import us, salvar_draft


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--projeto", required=True)
    ap.add_argument("--corte", required=True, help="nome do corte (campo 'nome' do cortes/*.json)")
    ap.add_argument("--nome", required=True, help="nome do draft no CapCut")
    a = ap.parse_args()
    proj = Path(a.projeto).resolve()
    cdir = proj / "06_capcut" / f"camadas_{a.corte}"
    C = json.load(open(cdir / "camadas.json", encoding="utf-8"))
    plano = json.load(open(cdir / "plano_fiel.json", encoding="utf-8"))
    ganho = json.load(open(cdir / "audio.json")).get("ganho_master", 1.0)
    W, H, total = C["w"], C["h"], C["duracao"]
    script = draft.Script_file(W, H, fps=30)

    base = cdir / C["base"]
    script.add_track(draft.Track_type.video, "VIDEO FINAL (sem textos)")
    vmat = draft.Video_material("video", path=str(base), material_name="base_" + cdir.name + ".mp4",
                                duration=total, width=W, height=H)
    script.add_segment(draft.Video_segment(vmat, trange(0, us(total)), source_timerange=trange(0, us(total)),
                                           volume=0.0, clip_settings=Clip_settings()), "VIDEO FINAL (sem textos)")
    n_png = 0
    for qual, trilha in (("textos", "LETTERING"), ("legenda", "LEGENDA")):
        evs = C["eventos"].get(qual, [])
        if not evs:
            continue
        script.add_track(draft.Track_type.video, trilha)
        prev = None
        for ev in evs:
            t0, t1 = ev["t0"], min(ev["t1"], total)
            if t1 - t0 < 1 / 60:
                continue
            png = (cdir / ev["png"]).resolve()
            mat = draft.Video_material("photo", path=str(png), material_name=f"{cdir.name}_{png.name}")
            mat.width, mat.height = W, H
            seg = draft.Video_segment(mat, trange(us(t0), us(t1 - t0)), source_timerange=trange(0, us(t1 - t0)),
                                      clip_settings=Clip_settings())
            y0, y1, x0, x1 = ev["bbox"]
            novo = (prev is None or prev["t1"] < t0 - 0.02 or abs(prev["bbox"][0] - y0) > 60)
            if novo and t1 - t0 > 0.3:
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                for dt, sc, al in ((0.0, 0.86, 0.0), (0.07, 0.97, 1.0), (0.14, 1.03, 1.0), (0.20, 1.0, 1.0)):
                    off = us(dt)
                    seg.add_keyframe(KP.uniform_scale, off, sc)
                    seg.add_keyframe(KP.position_x, off, (1 - sc) * (cx - W / 2) / (W / 2))
                    seg.add_keyframe(KP.position_y, off, -(1 - sc) * (cy - H / 2) / (H / 2))
                    seg.add_keyframe(KP.alpha, off, al)
            script.add_segment(seg, trilha)
            prev = ev
            n_png += 1

    for nome, trilha in (("voz.wav", "VOZ"), ("musica.wav", "MUSICA (com ducking)")):
        wp = cdir / nome
        with wave.open(str(wp), "rb") as wf:
            d = wf.getnframes() / wf.getframerate()
        d = min(d, total)
        script.add_track(draft.Track_type.audio, trilha)
        amat = draft.Audio_material(path=str(wp), material_name=f"{cdir.name}_{nome}", duration=d)
        script.add_segment(draft.Audio_segment(amat, trange(0, us(d)), source_timerange=trange(0, us(d))), trilha)
    sfx_dir = cdir / "sfx"
    sfx_dir.mkdir(exist_ok=True)
    fins = []
    for k, ev in enumerate(plano.get("sfx", [])):
        t_ev = max(0.0, ev["t"] - ev.get("antecipa", 0.0))
        if t_ev >= total:
            continue
        x = SFX.obter(ev, 48000, SKILL, proj) * 10 ** (ev.get("vol", -12) / 20) * ganho
        wp = sfx_dir / f"sfx_{k:03d}_{ev.get('tipo', 'arq')}.wav"
        with wave.open(str(wp), "wb") as wf:
            wf.setnchannels(2), wf.setsampwidth(2), wf.setframerate(48000)
            wf.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
        d = min(len(x) / 48000, total - t_ev)
        ti = next((i for i, fim in enumerate(fins) if fim <= t_ev), None)
        if ti is None:
            fins.append(0)
            ti = len(fins) - 1
            script.add_track(draft.Track_type.audio, f"SFX {ti + 1}")
        fins[ti] = t_ev + d
        amat = draft.Audio_material(path=str(wp), material_name=f"{cdir.name}_{wp.name}", duration=len(x) / 48000)
        script.add_segment(draft.Audio_segment(amat, trange(us(t_ev), us(d)), source_timerange=trange(0, us(d))),
                           f"SFX {ti + 1}")

    dest = salvar_draft(script, a.nome, total, proj, capa_mp4=base)
    print(f"OK draft FIEL '{a.nome}' -> {dest} ({total:.1f}s, {n_png} PNGs de texto, {len(fins)} trilhas de SFX)")


if __name__ == "__main__":
    main()
