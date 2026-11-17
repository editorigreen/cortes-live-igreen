"""
Draft NATIVO do CapCut para o formato "corte de live" (tudo editável).

Uso: python capcut_nativo.py --projeto P cortes/corte1.json --nome "<AAAA-MM-DD_..._vN_nativo>"

Trilhas:
  * LIVE (A-roll)          — trechos da LIVE SÁBADO.mp4 com escala/posição que encaixam o recorte 16:9 do Thiago
                             no card (zoom alternado + punch por keyframe). Áudio original do trecho.
  * FUNDO + MOLDURA        — PNG 1080x1920 = background da marca com um "furo" arredondado no lugar do card + borda
                             neon (cantos exatos sem depender da máscara do CapCut). No end card, o background inteiro.
  * TÍTULO / CRÉDITO / END — textos nativos (Anton / Montserrat) nas mesmas posições do MP4.
  * LEGENDAS               — um texto por bloco, palavras-chave em verde neon.
  * MÚSICA + SFX
"""
import argparse
import json
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # acha _base.py mesmo com python -I
import _base  # noqa: F401
import pyJianYingDraft as draft
from pyJianYingDraft import Clip_settings, Keyframe_property as KP, trange
from pyJianYingDraft.text_segment import TextStyleRange
import corte_live as CL
import render_reels as RR
import sfx as SFX
from capcut_comum import us, hex_rgb01, fonte_path, salvar_draft, exigir_capcut_fechado


def text_style(est, escala=1.0, align=1):
    """Estilo nativo calibrado: corpo /4,2 (2026-11-11); tracking do motor é % do corpo e o CapCut usa passos de
    0,05 em -> tracking/5 (com o valor cru o eyebrow/crédito esticavam para fora do quadro — feedback 2026-11-16)."""
    return draft.Text_style(size=round(est.get("tamanho", 80) * escala / 4.2, 1), color=hex_rgb01(est.get("cor", "#ffffff")),
                            align=align, letter_spacing=int(round(est.get("tracking", 0) / 5)), bold=False)

W, H = CL.W, CL.H


def frame_em(t):
    b = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(CL.LIVE), "-frames:v", "1", "-f", "rawvideo",
                        "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return np.frombuffer(b, np.uint8).reshape(CL.SH, CL.SW, 3)


def para_capcut(area, zoom, foco):
    """Recorte (área útil da live + zoom) -> (escala, tx, ty) para o recorte ocupar exatamente o card."""
    x, y, w, h = area
    cw, ch = w / zoom, h / zoom
    cx = min(max(x + w * foco[0], x + cw / 2), x + w - cw / 2)
    cy = min(max(y + h * foco[1], y + ch / 2), y + h - ch / 2)
    fit = W / CL.SW
    esc = CL.CARD_W / (cw * fit)
    k = fit * esc
    card_cy = CL.CARD_Y + CL.CARD_H / 2
    tx = -(cx - CL.SW / 2) * k / (W / 2)
    ty = ((cy - CL.SH / 2) * k + (H / 2 - card_cy)) / (H / 2)
    return esc, tx, ty


def png_moldura(path, furo=True):
    bg = Image.fromarray((CL.fundo() * 255).astype(np.uint8)).convert("RGBA")
    if furo:
        m = Image.new("L", (W * 4, H * 4), 0)
        ImageDraw.Draw(m).rounded_rectangle([CL.MARG * 4, CL.CARD_Y * 4, (CL.MARG + CL.CARD_W) * 4,
                                             (CL.CARD_Y + CL.CARD_H) * 4], CL.RAIO * 4, fill=255)
        hole = np.asarray(m.resize((W, H), Image.LANCZOS))
        a = np.array(bg)
        a[..., 3] = 255 - hole
        bg = Image.fromarray(a)
        glow = Image.fromarray((np.clip(CL.moldura_card(), 0, 1) * 255).astype(np.uint8))
        # sombra/glow só fora do card (dentro fica a imagem)
        ga = np.array(glow)
        ga[..., 3] = (ga[..., 3].astype(np.float32) * (255 - hole) / 255).astype(np.uint8)
        bg.alpha_composite(Image.fromarray(ga))
        bg.alpha_composite(Image.fromarray((np.clip(CL.borda_card(), 0, 1) * 255).astype(np.uint8)))
    bg.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corte")
    ap.add_argument("--projeto", required=True)
    ap.add_argument("--nome", required=True)
    a = ap.parse_args()
    exigir_capcut_fechado()
    CL.configurar(a.projeto)
    PROJ = CL.PROJ
    C, segs, total_fala, end, palavras = CL.carregar(PROJ / a.corte)
    total = total_fala + end
    CL.camada_textos(C)       # preenche C["_caixas"] com as posições exatas dos textos do MP4
    caixas = C["_caixas"]
    blocos = CL.blocos_legenda(C, palavras)
    destaques = {d.lower() for d in C.get("destaques", [])}
    cc = PROJ / "06_capcut" / f"nativo_{C['nome']}"
    cc.mkdir(parents=True, exist_ok=True)
    png_moldura(cc / "fundo_moldura.png", True)
    png_moldura(cc / "fundo_end.png", False)

    script = draft.Script_file(W, H, fps=30)
    textos_json = []

    # 1) LIVE
    script.add_track(draft.Track_type.video, "LIVE (A-roll)")
    probe = json.loads(subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(CL.LIVE)],
                                      capture_output=True, text=True, encoding="utf-8").stdout)
    mat = draft.Video_material("video", path=str(CL.LIVE), material_name=CL.LIVE.name,
                               duration=float(probe["format"]["duration"]), width=CL.SW, height=CL.SH)
    for s in segs:
        area = CL.AREA_DIV if CL.eh_dividida(frame_em(s["ini"] + min(0.1, s["dur"] / 2))) else CL.AREA_CHEIA
        foco = tuple(s.get("foco", C.get("foco", [0.5, 0.45])))
        seg = draft.Video_segment(mat, trange(us(s["out0"]), us(s["dur"])), source_timerange=trange(us(s["ini"]), us(s["dur"])),
                                  volume=1.0, clip_settings=Clip_settings())
        am = set(np.round(np.arange(0, s["dur"], 0.5), 3).tolist() + [max(0.0, s["dur"] - 1 / 30)])
        for p in s.get("punch", []):
            am |= set(np.round(np.arange(p["t"], p["t"] + 0.2, 1 / 30), 3).tolist())
        last = None
        for tk in sorted(x for x in am if 0 <= x < s["dur"]):
            v = tuple(round(q, 4) for q in para_capcut(area, CL.zoom_em(s, tk), foco))
            if v == last:
                continue
            last = v
            seg.add_keyframe(KP.uniform_scale, us(tk), v[0])
            seg.add_keyframe(KP.position_x, us(tk), v[1])
            seg.add_keyframe(KP.position_y, us(tk), v[2])
        script.add_segment(seg, "LIVE (A-roll)")

    # 2) fundo com furo + end
    script.add_track(draft.Track_type.video, "FUNDO + MOLDURA", absolute_index=10000)
    for png, t0, t1 in ((cc / "fundo_moldura.png", 0.0, total_fala), (cc / "fundo_end.png", total_fala, total)):
        m = draft.Video_material("photo", path=str(png), material_name=f"{C['nome']}_{png.name}")
        m.width, m.height = W, H
        script.add_segment(draft.Video_segment(m, trange(us(t0), us(t1 - t0)), source_timerange=trange(0, us(t1 - t0)),
                                               clip_settings=Clip_settings()), "FUNDO + MOLDURA")

    # 3) textos fixos (eyebrow, título, crédito) — cada um numa trilha; sem sombra (pedido do cliente)
    for k, cx in enumerate(caixas):
        est = cx["est"]
        nm = f"TEXTO {k + 1}: {cx['txt'][:18]}"
        script.add_track(draft.Track_type.text, nm)
        tx_cc = ((cx["x0"] + cx["x1"]) / 2 / W - 0.5) * 2
        if cx["txt"].startswith("•"):
            tx_cc = CL.EYEBROW_X_CAPCUT    # posição do ajuste manual do cliente (o CapCut desenha o eyebrow mais largo)
        seg = draft.Text_segment(cx["txt"], trange(0, us(total_fala)), style=text_style(est, align=0),
                                 clip_settings=Clip_settings(transform_x=tx_cc,
                                                             transform_y=(0.5 - cx["cy"] / H) * 2))
        for i0, i1, es_ in cx.get("faixas", []):
            try:
                seg.add_text_style(TextStyleRange(i0, i1, text_style(es_, align=0)))
            except Exception as e:  # noqa
                print("aviso faixa:", e)
        script.add_segment(seg, nm)
        textos_json.append((cx["txt"], fonte_path(est)))
    # end card: logotipo oficial como imagem própria (editável) + linha "LIVE OFICIAL · 14/11"
    CL.camada_end(C)
    lg = C["_logo"]
    lpng = cc / "logo_igreen.png"
    li = Image.open(CL.LOGO).convert("RGBA")
    li = li.crop(li.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox())
    li.save(lpng)
    script.add_track(draft.Track_type.video, "LOGO iGreen", absolute_index=10001)
    lm = draft.Video_material("photo", path=str(lpng), material_name="logo_igreen.png")
    lm.width, lm.height = li.width, li.height
    script.add_segment(draft.Video_segment(lm, trange(us(total_fala), us(end)), source_timerange=trange(0, us(end)),
                                           clip_settings=Clip_settings(scale_x=lg["w"] / W, scale_y=lg["w"] / W,
                                                                       transform_y=(0.5 - lg["y"] / H) * 2)),
                       "LOGO iGreen")
    fe = Image.open(cc / "fundo_end.png").convert("RGBA")   # linha neon do end card fica no fundo do end
    ImageDraw.Draw(fe).rounded_rectangle([W / 2 - 60, C["_linha_y"], W / 2 + 60, C["_linha_y"] + 6], 3,
                                         fill=(30, 255, 46, 255))
    fe.save(cc / "fundo_end.png")
    script.add_track(draft.Track_type.text, "END CARD 2")
    es = draft.Text_segment(C["_end_sub"], trange(us(total_fala), us(end)), style=text_style(CL.EST["end_sub"]),
                            clip_settings=Clip_settings(transform_y=(0.5 - C["_sub_cy"] / H) * 2))
    script.add_segment(es, "END CARD 2")
    textos_json.append((C["_end_sub"], fonte_path(CL.EST["end_sub"])))

    # 4) legendas
    script.add_track(draft.Track_type.text, "LEGENDAS")
    en, ed = CL.ESTILOS["legenda"], CL.ESTILOS["legenda_destaque"]
    last_end = 0.0
    for b in blocos:
        t0, t1 = max(b["t0"], last_end), min(b["t1"], total_fala)
        if t1 - t0 < 0.05:
            continue
        last_end = t1
        palav = [w["p"].strip(",;") for w in b["palavras"]]
        txt = " ".join(palav)
        dest = lambda w: (w.strip(".!?:").lower() in destaques) or any(c.isdigit() for c in w)  # noqa: E731
        larg = sum(RR._ink_crop_x(RR.render_linha(w, ed if dest(w) else en)).width for w in palav)
        larg += (len(palav) - 1) * en.get("tamanho", 88) * 0.34
        f = min(1.0, 0.84 * W / max(1, larg))
        seg = draft.Text_segment(txt, trange(us(t0), us(t1 - t0)), style=text_style(en, f),
                                 clip_settings=Clip_settings(transform_y=(0.5 - CL.LEG_Y) * 2))
        pos = 0
        for w in palav:
            if dest(w):
                try:
                    seg.add_text_style(TextStyleRange(pos, pos + len(w), text_style(ed, f)))
                except Exception:
                    pass
            pos += len(w) + 1
        try:
            seg.add_animation(draft.CapCut_Text_intro.Pop_Up, duration=us(0.18))
        except Exception:
            pass
        script.add_segment(seg, "LEGENDAS")
        textos_json.append((txt, fonte_path(en)))

    # 5) música + SFX
    mp = C.get("musica")
    if mp:
        mdur = float(json.loads(subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", mp["arquivo"]],
                                               capture_output=True, text=True, encoding="utf-8").stdout)["format"]["duration"])
        d = min(total, mdur)
        script.add_track(draft.Track_type.audio, "MUSICA")
        am_ = draft.Audio_material(path=mp["arquivo"], material_name=mp.get("_nome", "musica"), duration=mdur)
        aseg = draft.Audio_segment(am_, trange(0, us(d)), source_timerange=trange(0, us(d)),
                                   volume=10 ** ((mp["volume_db"] + mp["ducking_db"] / 2) / 20) * 2.0)
        try:
            aseg.add_fade(us(0.2), us(mp.get("fade_out", 1.6)))
        except Exception:
            pass
        script.add_segment(aseg, "MUSICA")
    sfx_dir = PROJ / "04_assets" / "sfx"
    sfx_dir.mkdir(parents=True, exist_ok=True)
    fins = []
    for ev in C.get("sfx", []):
        t_ev = max(0.0, ev["t"] - ev.get("antecipa", 0.0))
        wp = sfx_dir / f"{ev['tipo']}.wav"
        if not wp.exists():
            x = SFX.gerar(ev["tipo"], 48000, ev.get("dur"))
            with wave.open(str(wp), "wb") as wf:
                wf.setnchannels(2), wf.setsampwidth(2), wf.setframerate(48000)
                wf.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
        with wave.open(str(wp), "rb") as wf:
            d = min(wf.getnframes() / wf.getframerate(), total - t_ev)
        ti = next((i for i, fim in enumerate(fins) if fim <= t_ev), None)
        if ti is None:
            fins.append(0)
            ti = len(fins) - 1
            script.add_track(draft.Track_type.audio, f"SFX {ti + 1}")
        fins[ti] = t_ev + d
        am_ = draft.Audio_material(path=str(wp), material_name=wp.name, duration=d)
        script.add_segment(draft.Audio_segment(am_, trange(us(t_ev), us(d)), source_timerange=trange(0, us(d)),
                                               volume=10 ** (ev.get("vol", -12) / 20) * 2.0), f"SFX {ti + 1}")

    dest = salvar_draft(script, a.nome, total, PROJ, capa_mp4=PROJ / "05_render" / f"{C['nome']}.mp4",
                        fontes_por_texto=dict(textos_json))
    print(f"OK draft NATIVO '{a.nome}' -> {dest} ({total:.1f}s, {len(segs)} trechos da live, {len(blocos)} legendas)")

if __name__ == "__main__":
    main()
