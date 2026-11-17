"""
Motor "CORTE DE LIVE" iGreen — live 16:9 dentro de um card, sobre o background da marca, em Reels 9:16.

Uso (sempre com --projeto <pasta que tem projeto.json>):
  python corte_live.py --projeto P cortes/corte1.json                  # MP4 final + camadas do draft FIEL
  python corte_live.py --projeto P cortes/corte1.json --frames 0.5,4,9 # só stills de QA (05_render/qa_<nome>/)
  python corte_live.py --projeto P cortes/corte1.json --checar         # só a trava de borda R-024

Layout (inspirado nas refs "cortes lancamentos", com a identidade iGreen):
  eyebrow "LIVE OFICIAL iGREEN · 14/11" -> título Anton caixa alta (última linha verde neon com glow)
  -> card 16:9 arredondado com borda neon (live recortada: painel do Thiago na tela dividida / tela cheia)
  -> "THIAGO ALEXANDER · PRESIDENTE iGREEN" -> legenda dinâmica da casa (Montserrat 800/900, destaque verde)
  -> end card iGreen.
O recorte detecta sozinho, quadro a quadro, se a live está em tela dividida (Thiago + convidado) ou em tela cheia.
"""
import argparse
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # acha _base.py mesmo com python -I
import _base  # noqa: E402,F401  (caminhos da skill: lib/, capcut_vendor/)
from _base import SKILL, LIB, resolver, carregar_projeto  # noqa: E402
import render_reels as RR  # noqa: E402  (reuso: render_linha, legendas, animações, fontes)
import sfx as SFX  # noqa: E402

PROJ = None      # pasta do projeto (definida por configurar())
RAIZ = SKILL

W, H, FPS = 1080, 1920, 30
LIVE = None
BG = SKILL / "assets" / "background_corte_live.png"
LOGO = SKILL / "assets" / "logos" / "igreen_verde_claro.png"   # logo oficial (há também igreen_branco.png)
PROJETO = {}
LOGO_W = 600
SW, SH = 1280, 720
PAINEL = (26, 191, 601, 337)          # painel do Thiago na tela dividida (x, y, w, h) — medido no bruto
AREA_DIV = (68, 193, 516, 290)        # painel sem a plaquinha do nome (y >= 488)
AREA_CHEIA = (0, 0, 1120, 630)        # tela cheia sem plaquinha (y >= 662) e sem logo (x >= 1126)
VERDE, BRANCO, CINZA = "#1EFF2E", "#F3F5F2", "#C9D2CB"

# geometria do 9:16
MARG = 60
CARD_W = W - 2 * MARG                 # 960
CARD_H = int(round(CARD_W * 9 / 16))  # 540
CARD_Y = 684
RAIO = 30
LEG_Y = 0.75                          # centro da 1ª linha da legenda (fração da altura)

ESTILOS = json.load(open(LIB / "estilos_igreen.json", encoding="utf-8"))
# feedback do cliente (2026-11-16): títulos menores e mais clean, NENHUM texto com sombra/glow (premium),
# legenda menor e em minúsculas (exceto nomes próprios)
EST = {
    "eyebrow": {"fonte": "Montserrat[wght].ttf", "peso": 700, "tamanho": 28, "tracking": 8, "cor": CINZA},
    "titulo": {"fonte": "Anton-Regular.ttf", "tamanho": 82, "tracking": 0.5, "cor": BRANCO},
    "titulo_verde": {"fonte": "Anton-Regular.ttf", "tamanho": 82, "tracking": 0.5, "cor": VERDE},
    "nome": {"fonte": "Montserrat[wght].ttf", "peso": 800, "tamanho": 30, "tracking": 5, "cor": VERDE},
    "cargo": {"fonte": "Montserrat[wght].ttf", "peso": 600, "tamanho": 30, "tracking": 0, "cor": BRANCO},
    "end_marca": {"fonte": "Montserrat[wght].ttf", "peso": 900, "tamanho": 150, "tracking": -4, "cor": BRANCO},
    "end_marca_v": {"fonte": "Montserrat[wght].ttf", "peso": 900, "tamanho": 150, "tracking": -4, "cor": VERDE},
    "end_sub": {"fonte": "Montserrat[wght].ttf", "peso": 700, "tamanho": 32, "tracking": 10, "cor": CINZA},
    "end_cta": {"fonte": "Montserrat[wght].ttf", "peso": 800, "tamanho": 44, "cor": BRANCO},
    # legenda: ajuste manual do cliente no CapCut (corte 2, 2026-11-17) — tudo 12,68 no CapCut (= 53 px), Montserrat
    # Bold, destaque só pela COR (mesmo corpo e peso do texto normal)
    "legenda": {"fonte": "Montserrat[wght].ttf", "peso": 700, "tamanho": 53.25, "tracking": -1, "cor": BRANCO},
    "legenda_destaque": {"fonte": "Montserrat[wght].ttf", "peso": 700, "tamanho": 53.25, "tracking": -1, "cor": VERDE},
}
ESTILOS.update(EST)
GAP_TITULO_CARD = 52                  # do pé da última linha do título até o card
# diagramação aprovada pelo cliente no CapCut (ajuste manual no corte 4, 2026-11-16) — y do CapCut -> px:
#   eyebrow y +0,7299 (centro 259 px), crédito CENTRALIZADO y -0,3324 (centro 1279 px), legenda y -0,50 (1440 px)
EYEBROW_CY = 259
CREDITO_CY = 1279
EYEBROW_X_CAPCUT = -0.2720            # no CapCut o eyebrow renderiza mais largo: x do ajuste do cliente
# legenda em minúsculas; estes nomes próprios mantêm a grafia (chave = minúscula, sem pontuação)
NOMES_PROPRIOS = {"igreen": "iGreen", "green": "Green", "friday": "Friday", "pix": "Pix", "club": "Club",
                  "thiago": "Thiago", "calebe": "Calebe", "caleb": "Caleb", "brasil": "Brasil", "natal": "Natal"}
FAIXA_TESTE, LIMIAR_DIVIDIDA = (0, 170, 0, 1000), 25


def configurar(proj):
    """Lê projeto.json (+ padrão iGreen da skill) e ajusta os globais do motor."""
    global PROJ, LIVE, BG, LOGO, AREA_DIV, AREA_CHEIA, FAIXA_TESTE, LIMIAR_DIVIDIDA, PROJETO
    P = carregar_projeto(proj)
    PROJETO = P
    PROJ = P["_dir"]
    LIVE = P["_live"]
    BG = resolver(P["background"], PROJ)
    LOGO = resolver(P["logo"], PROJ)
    ll = P["layout_live"]
    AREA_DIV, AREA_CHEIA = tuple(ll["area_dividida"]), tuple(ll["area_cheia"])
    FAIXA_TESTE, LIMIAR_DIVIDIDA = tuple(ll["faixa_teste"]), ll["limiar_dividida"]
    NOMES_PROPRIOS.update({k.lower(): v for k, v in P.get("nomes_proprios", {}).items()})
    return P


def minusculas(p):
    """Legenda sempre minúscula, exceto nomes próprios (regra do cliente). Valores 'R$' ficam como estão."""
    if p.startswith("R$"):
        return p
    nucleo = p.strip(".,!?;:")
    if not nucleo:
        return p
    return p.replace(nucleo, NOMES_PROPRIOS.get(nucleo.lower(), nucleo.lower()))


# ----------------------------------------------------------------------------- utilidades
def lin(txt, est):
    return RR._ink_crop_x(RR.render_linha(txt, est))


def registrar(C, txt, est, img, x, y, x_esq=None, faixas=None):
    """Guarda a caixa de cada texto colado — a ponte nativa do CapCut usa as mesmas posições.
    x_esq/x_dir: borda esquerda do bloco (textos alinhados à esquerda no card); faixas: estilos por trecho."""
    al = np.asarray(img)[..., 3]
    ys, xs = np.nonzero(al > 8)
    if len(xs):
        C.setdefault("_caixas", []).append({"txt": txt, "est": est, "x0": x_esq if x_esq is not None else x + xs.min(),
                                            "x1": x + xs.max(), "cy": y + (ys.min() + ys.max()) / 2,
                                            "faixas": faixas or []})


def rgba_np(img):
    return np.array(img, dtype=np.float32) / 255.0


def compor(base, layer, x=0, y=0):
    """alpha composite de um RGBA (float 0..1, HxWx4) num RGB float 0..1."""
    h, w = layer.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(base.shape[1], x + w), min(base.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return
    L = layer[y0 - y:y1 - y, x0 - x:x1 - x]
    a = L[..., 3:4]
    base[y0:y1, x0:x1] = base[y0:y1, x0:x1] * (1 - a) + L[..., :3] * a


def fundo():
    im = Image.open(BG).convert("RGB")
    # cover 1080x1920 (o PNG já é 9:16: 3375x6000)
    return np.asarray(im.resize((W, H), Image.LANCZOS), dtype=np.float32) / 255.0


def mascara_card(w, h, r):
    m = Image.new("L", (w * 4, h * 4), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w * 4 - 1, h * 4 - 1], r * 4, fill=255)
    return np.asarray(m.resize((w, h), Image.LANCZOS), dtype=np.float32)[..., None] / 255.0


def moldura_card():
    """Sombra + glow verde + borda fina neon ao redor do card (camada RGBA de tela cheia)."""
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([MARG, CARD_Y + 18, MARG + CARD_W, CARD_Y + CARD_H + 18], RAIO,
                                         fill=(0, 0, 0, 170))
    lay.alpha_composite(sh.filter(ImageFilter.GaussianBlur(26)))
    gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(gl).rounded_rectangle([MARG - 2, CARD_Y - 2, MARG + CARD_W + 2, CARD_Y + CARD_H + 2], RAIO + 2,
                                         outline=(30, 255, 46, 150), width=6)
    lay.alpha_composite(gl.filter(ImageFilter.GaussianBlur(14)))
    return rgba_np(lay)


def borda_card():
    lay = Image.new("RGBA", (W * 2, H * 2), (0, 0, 0, 0))
    ImageDraw.Draw(lay).rounded_rectangle([MARG * 2, CARD_Y * 2, (MARG + CARD_W) * 2, (CARD_Y + CARD_H) * 2],
                                          RAIO * 2, outline=(30, 255, 46, 205), width=5)
    return rgba_np(lay.resize((W, H), Image.LANCZOS))


def camada_textos(C):
    """Eyebrow + título + crédito (estáticos durante o corte). Retorna RGBA PIL de tela cheia."""
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    lim = W * RR.AREA_SEGURA_TEXTO
    # tamanho ÚNICO para todas as linhas (cabe a mais larga) — linhas com corpos diferentes ficam amadoras
    tam = C.get("titulo_tamanho", EST["titulo"]["tamanho"])
    for txt, cor in C["titulo"]:
        im = lin(txt, dict(EST["titulo"], tamanho=tam))
        if im.width > lim:
            tam = tam * lim / im.width * 0.98
    ref = RR.render_linha("H", dict(EST["titulo"], tamanho=tam))
    ys = np.nonzero(np.asarray(ref)[..., 3].max(1) > 8)[0]
    topo, cap = int(ys.min()), int(ys.max() - ys.min())
    passo = cap * 1.36
    n = len(C["titulo"])
    y_tit = CARD_Y - GAP_TITULO_CARD - cap - (n - 1) * passo     # topo do glifo da 1ª linha
    # eyebrow (ponto verde + texto) acima do título
    eb_txt = C.get("eyebrow", PROJETO.get("eyebrow", "LIVE OFICIAL iGreen  ·  14/11"))
    eb = lin(eb_txt, EST["eyebrow"])
    ebi = RR.render_linha(eb_txt, EST["eyebrow"])
    eys = np.nonzero(np.asarray(ebi)[..., 3].max(1) > 8)[0]
    e_cap = int(eys.max() - eys.min())
    y_eb = int(EYEBROW_CY - e_cap / 2)                              # topo do glifo do eyebrow
    d = ImageDraw.Draw(lay)
    d.ellipse([MARG, y_eb + e_cap / 2 - 6, MARG + 12, y_eb + e_cap / 2 + 6], fill=(30, 255, 46, 255))
    lay.alpha_composite(eb, (MARG + 24, y_eb - int(eys.min())))
    registrar(C, "•  " + eb_txt, EST["eyebrow"], eb, MARG + 24, y_eb - int(eys.min()), x_esq=MARG,
              faixas=[(0, 1, dict(EST["eyebrow"], cor=VERDE))])
    y = y_tit
    for txt, cor in C["titulo"]:
        est = dict(EST["titulo_verde" if cor == "verde" else "titulo"], tamanho=tam)
        im = RR._ink_crop_x(RR.render_linha(txt, est))
        lay.alpha_composite(im, (MARG, int(y - topo)))
        registrar(C, txt, est, im, MARG, int(y - topo))
        y += passo
    # crédito sob o card, CENTRALIZADO (ajuste do cliente), registrado como UM texto com o nome em verde
    cred = C.get("credito", PROJETO.get("credito", {"nome": "THIAGO ALEXANDER", "cargo": "Presidente da iGreen"}))
    partes = [(cred["nome"], EST["nome"]), ("|", dict(EST["cargo"], cor="#8E9A91")), (cred["cargo"], EST["cargo"])]
    ims = [lin(tx_, es_) for tx_, es_ in partes]
    gw = sum(im.width for im in ims) + 16 * (len(ims) - 1)
    gh = max(im.height for im in ims)
    grupo = Image.new("RGBA", (gw, gh), (0, 0, 0, 0))
    x = 0
    for im in ims:
        grupo.alpha_composite(im, (x, (gh - im.height) // 2))
        x += im.width + 16
    ga = np.asarray(grupo)[..., 3]
    gys = np.nonzero(ga.max(1) > 8)[0]
    yc = int(CREDITO_CY - (gys.min() + gys.max()) / 2)
    xc = int(W / 2 - gw / 2)
    lay.alpha_composite(grupo, (xc, yc))
    n_ = len(cred["nome"])
    registrar(C, f"{cred['nome']}  |  {cred['cargo']}", EST["cargo"], grupo, xc, yc,
              faixas=[(0, n_, EST["nome"]), (n_ + 2, n_ + 3, dict(EST["cargo"], cor="#8E9A91"))])
    return lay


def camada_end(C):
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # logotipo OFICIAL (pasta logotipos/, pedido do cliente 2026-11-16) no lugar do lettering "iGreen"
    logo = Image.open(LOGO).convert("RGBA")
    logo = logo.crop(logo.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox())
    lw = LOGO_W
    logo = logo.resize((lw, int(logo.height * lw / logo.width)), Image.LANCZOS)
    y0 = int(H * 0.40)
    lay.alpha_composite(logo, (int(W / 2 - lw / 2), y0))
    C["_logo"] = {"x": W / 2, "y": y0 + logo.height / 2, "w": lw}
    y0 += logo.height
    d = ImageDraw.Draw(lay)
    yl = y0 + 48
    d.rounded_rectangle([W / 2 - 60, yl, W / 2 + 60, yl + 6], 3, fill=(30, 255, 46, 255))
    C["_end_sub"] = C.get("end_sub", PROJETO.get("end_sub", "LIVE OFICIAL  ·  14/11"))
    s = lin(C["_end_sub"], EST["end_sub"])
    lay.alpha_composite(s, (int(W / 2 - s.width / 2), yl + 40))
    C["_linha_y"] = yl
    C["_sub_cy"] = yl + 40 + s.height / 2
    if C.get("end_cta"):
        c = lin(C["end_cta"], EST["end_cta"])
        lay.alpha_composite(c, (int(W / 2 - c.width / 2), yl + 40 + s.height + 40))
    return lay


# ----------------------------------------------------------------------------- vídeo da live
def eh_dividida(fr):
    """Tela dividida: faixa superior é o fundo preto/verde da transmissão (luma ~5). Tela cheia: estante (~60-90)."""
    y0, y1, x0, x1 = FAIXA_TESTE
    return fr[y0:y1:4, x0:x1:4].mean() < LIMIAR_DIVIDIDA


def recorte(fr, zoom, foco=(0.5, 0.45)):
    # área útil 16:9 SEM a plaquinha "Thiago Alexander" e SEM o logo da transmissão (medidos no bruto)
    x, y, w, h = AREA_DIV if eh_dividida(fr) else AREA_CHEIA
    cw, ch = w / zoom, h / zoom
    cx = x + w * foco[0]
    cy = y + h * foco[1]
    x0 = min(max(cx - cw / 2, x), x + w - cw)
    y0 = min(max(cy - ch / 2, y), y + h - ch)
    M = np.float32([[CARD_W / cw, 0, -x0 * CARD_W / cw], [0, CARD_H / ch, -y0 * CARD_H / ch]])
    out = cv2.warpAffine(fr, M, (CARD_W, CARD_H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
    # nitidez leve (upscale de 600 px -> 960 px)
    bl = cv2.GaussianBlur(out, (0, 0), 1.2)
    return cv2.addWeighted(out, 1.35, bl, -0.35, 0)


class Leitor:
    def __init__(self, t0, dur):
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-i", str(LIVE), "-t", f"{dur + 0.2:.3f}",
                                   "-r", str(FPS), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        self.last = None

    def ler(self):
        b = self.p.stdout.read(SW * SH * 3)
        if len(b) == SW * SH * 3:
            self.last = np.frombuffer(b, np.uint8).reshape(SH, SW, 3)
        return self.last

    def fechar(self):
        self.p.stdout.close()
        self.p.kill()


# ----------------------------------------------------------------------------- plano -> timeline
def carregar(cpath):
    C = json.load(open(cpath, encoding="utf-8"))
    for k in ("end_card", "zoom_alt", "max_palavras"):
        C.setdefault(k, PROJETO.get(k))
    C["musica"] = dict(PROJETO.get("musica", {}), **C.get("musica", {})) if (C.get("musica") or PROJETO.get("musica")) else None
    if C.get("musica"):
        C["musica"]["arquivo"] = str(resolver(C["musica"]["arquivo"], PROJ))
        if not Path(C["musica"]["arquivo"]).exists():
            sys.exit(f"trilha não encontrada: {C['musica']['arquivo']}
"
                     "A trilha da casa (rock inspirador da biblioteca do CapCut) vem só no pacote interno do time. Copie-a "
                     "para <skill>/assets/musica/action_sport_motivational_rock.mp3 ou aponte projeto.json['musica']"
                     "['arquivo'] para outra trilha.")
    C["legenda_corrigir"] = dict(PROJETO.get("legenda_corrigir", {}), **C.get("legenda_corrigir", {}))
    segs, t = [], 0.0
    for s in C["segmentos"]:
        s = dict(s)
        s["out0"] = t
        s["dur"] = s["fim"] - s["ini"]
        t += s["dur"]
        segs.append(s)
    total_fala = t
    end = C.get("end_card", 1.8)
    # palavras da transcrição (tempos absolutos na live) -> timeline de saída
    pal = []
    for jan in C["transcricoes"]:
        T = json.load(open(PROJ / jan["arquivo"], encoding="utf-8"))
        for sg in T["segmentos"]:
            for w in sg["palavras"]:
                pal.append({"p": w["p"], "i": w["i"] + jan["offset"], "f": w["f"] + jan["offset"]})
    # palavras com tempo cravado na energia do áudio (Whisper desloca palavras esticadas sobre pausas)
    for pm in C.get("palavras_manuais", []):
        a_, b_ = pm["faixa"]
        pal = [w for w in pal if not (a_ <= (w["i"] + w["f"]) / 2 <= b_)] + [dict(w) for w in pm["palavras"]]
    pal.sort(key=lambda w: w["i"])
    pal = juntar_tokens(pal)
    corr = {k.lower(): v for k, v in C.get("legenda_corrigir", {}).items()}
    out = []
    for w in pal:
        if w["f"] - w["i"] < 0.12:   # Whisper às vezes devolve palavra com duração zero ("dinheiro." no corte 1)
            w = dict(w, f=w["i"] + 0.12)
        # trecho com MAIOR sobreposição (o Whisper estica palavras sobre pausas: o ponto médio caía no silêncio
        # cortado e a palavra sumia da legenda — "30" de "30 mil" no corte 4)
        ov = [(min(w["f"], s["fim"]) - max(w["i"], s["ini"]), s) for s in segs]
        o, s = max(ov, key=lambda x: x[0])
        # mínimo 0,06 s E (35% da palavra ou 0,15 s): tira a palavra-fantasma da borda ("Então," no fim do corte 1)
        # (o Whisper adianta o início da palavra depois de pausa: na borda INICIAL do trecho a palavra vale se
        #  terminar dentro dele — "Então," do corte 2)
        borda_ini = w["i"] < s["ini"] and w["f"] > s["ini"] + 0.06
        if o < 0.06 or (o < 0.35 * (w["f"] - w["i"]) and o < 0.15 and not borda_ini):
            continue
        i = max(w["i"], s["ini"]) - s["ini"] + s["out0"]
        f = min(w["f"], s["fim"]) - s["ini"] + s["out0"]
        p = w["p"]
        nucleo = p.strip(".,!?;:")
        if nucleo.lower() in corr:
            p = p.replace(nucleo, corr[nucleo.lower()])
        p = minusculas(p)
        if p.strip():
            out.append({"p": p, "i": i, "f": f})
    out.sort(key=lambda w: w["i"])
    auto_plano(C, segs, out)
    C["sfx"].append({"t": total_fala + 0.05, "tipo": "ding", "vol": -15})
    return C, segs, total_fala, end, out


def juntar_tokens(pal):
    """Whisper quebra valores: R | $ | 1 | .997, -> 'R$ 1.997,'; '1.000' | ',00,' -> '1.000,00,'."""
    out = []
    for w in pal:
        p = w["p"]
        if out and (re.match(r"^[.,]\d", p) or (p.startswith("$") and out[-1]["p"] == "R")):
            out[-1] = dict(out[-1], p=out[-1]["p"] + p, f=w["f"])
            continue
        if out and out[-1]["p"] == "R$" and re.match(r"^\d", p):
            out[-1] = dict(out[-1], p="R$ " + p, f=w["f"])
            continue
        out.append(dict(w))
    return out


def auto_plano(C, segs, palavras):
    """Zoom alternado em todo jump cut (1,00 <-> zoom_alt), punch nas palavras-chave, boom/whoosh/ding."""
    za = C.get("zoom_alt", 1.08)
    sfx = list(C.get("sfx", []))
    # ritmo (R-006): plano > 2,8 s vira jump cuts contínuos na fonte (sem buraco de áudio, R-019) a cada ~2,2 s,
    # sempre ENTRE palavras
    novos = []
    for s in segs:
        fim_out = s["out0"] + s["dur"]
        ws = [w for w in palavras if s["out0"] <= w["i"] < fim_out]
        cands = [(ws[k]["f"] + ws[k + 1]["i"]) / 2 for k in range(len(ws) - 1)]
        last, pedacos = s["out0"], []
        for c in cands:
            if c - last >= C.get("plano_alvo", 2.2) and fim_out - c >= 1.0:
                pedacos.append((last, c))
                last = c
        pedacos.append((last, fim_out))
        for k, (o0, o1) in enumerate(pedacos):
            n = {kk: vv for kk, vv in s.items() if kk not in ("transicao",) or k == 0}
            n.update({"ini": s["ini"] + (o0 - s["out0"]), "fim": s["ini"] + (o1 - s["out0"]), "out0": o0, "dur": o1 - o0})
            novos.append(n)
    segs[:] = novos
    for k, s in enumerate(segs):
        if "zoom" not in s:
            s["zoom"] = [1.0, 1.02] if k % 2 == 0 else [za, za + 0.02]
        s.setdefault("punch", [])
    usados = set()
    for alvo in C.get("punch_palavras", []):
        w = next((w for w in palavras if alvo.lower() in w["p"].lower() and w["i"] not in usados), None)
        if not w:
            print("  punch: palavra não encontrada:", alvo)
            continue
        usados.add(w["i"])
        si = next(k for k, s in enumerate(segs) if s["out0"] <= w["i"] < s["out0"] + s["dur"] + 1e-6)
        segs[si]["punch"].append({"t": w["i"] - segs[si]["out0"], "z": 0.07})
        sfx.append({"t": w["i"], "tipo": "boom", "vol": -17})
    sfx.append({"t": 0.0, "tipo": "whoosh", "vol": -16})
    for s in segs:
        if s.get("transicao") == "flash":
            sfx.append({"t": s["out0"], "tipo": "whoosh", "vol": -14, "antecipa": 0.15})
    C["sfx"] = sfx


def blocos_legenda(C, palavras):
    cfg = {"max_palavras": C.get("max_palavras", 3)}
    bl = RR.montar_legendas(palavras, cfg)
    return bl


def desenhar_legenda(layer, blocos, destaques, t_out, estatico=False):
    b = next((b for b in blocos if b["t0"] - 0.03 <= t_out < b["t1"]), None)
    if b is None:
        return None
    est_n = dict(ESTILOS["legenda"])
    est_d = dict(ESTILOS["legenda_destaque"])
    y = LEG_Y * H
    imgs = []
    for w in b["palavras"]:
        limpo = w["p"].strip(".,!?:;").lower()
        est = dict(est_d) if (limpo in destaques or re.search(r"\d", limpo)) else dict(est_n)
        visivel = t_out >= w["i"] - 0.02
        imgs.append((RR._ink_crop_x(RR.render_linha(w["p"].strip(",;"), est)), visivel, w))
    sp = est_n.get("tamanho", 70) * 0.34   # pop cresce ~7%: espaço folgado p/ não colar ("vocêganhar")
    lim = W * RR.AREA_SEGURA_LEGENDA
    linhas, cur, cw = [], [], 0.0
    for item in imgs:
        wi = item[0].width
        if cur and cw + sp + wi > lim:
            linhas.append(cur)
            cur, cw = [], 0.0
        cw = wi if not cur else cw + sp + wi
        cur.append(item)
    if cur:
        linhas.append(cur)
    aj = []
    for ln in linhas:
        lw = sum(im.width for im, _, _ in ln) + (len(ln) - 1) * sp
        if lw > lim:
            f = lim / lw
            ln = [(im.resize((max(1, int(im.width * f)), max(1, int(im.height * f))), Image.LANCZOS), v, w)
                  for im, v, w in ln]
        aj.append(ln)
    for ln in aj:
        lw = sum(im.width for im, _, _ in ln) + (len(ln) - 1) * sp
        x = W / 2 - lw / 2
        for im, vis, w in ln:
            if vis:
                prog = 1.0 if estatico else (t_out - w["i"]) / 0.16
                im2, alpha, dx, dy = RR.animar(im, "pop", prog, 0)
                RR.colar(layer, im2, x + im.width / 2 + dx, y + dy, alpha)
            x += im.width + sp
        y += max(im.height for im, _, _ in ln) * 0.66
    return b


def zoom_em(s, t_rel):
    z0, z1 = s.get("zoom", [1.0, 1.0]) if isinstance(s.get("zoom"), list) else (s.get("zoom", 1.0),) * 2
    z = z0 + (z1 - z0) * min(1.0, t_rel / max(s["dur"], 1e-3))
    for p in s.get("punch", []):
        tp = p["t"] if isinstance(p, dict) else p
        amp = p.get("z", 0.07) if isinstance(p, dict) else 0.07
        if t_rel >= tp:
            z *= 1 + amp * RR.ease_out(min(1.0, (t_rel - tp) / 0.18))
    return z


# ----------------------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corte")
    ap.add_argument("--projeto", required=True, help="pasta do projeto (com projeto.json)")
    ap.add_argument("--frames", default=None)
    ap.add_argument("--checar", action="store_true")
    ap.add_argument("--sem_capcut", action="store_true")
    a = ap.parse_args()
    configurar(a.projeto)
    cpath = (PROJ / a.corte) if not Path(a.corte).is_absolute() else Path(a.corte)
    C, segs, total_fala, end, palavras = carregar(cpath)
    nome = C["nome"]
    total = total_fala + end
    blocos = blocos_legenda(C, palavras)
    destaques = {d.lower() for d in C.get("destaques", [])}
    bg = fundo()
    moldura = moldura_card()
    borda = borda_card()
    mask = mascara_card(CARD_W, CARD_H, RAIO)
    txt_lay = camada_textos(C)
    end_lay = camada_end(C)
    txt_np, end_np = rgba_np(txt_lay), rgba_np(end_lay)
    out_dir = PROJ / "05_render"
    out_dir.mkdir(parents=True, exist_ok=True)

    # R-024: trava de borda (legenda + textos) em todos os frames
    def checar():
        ruins = []
        mx = int(W * RR.MARGEM_BORDA)
        for fi in range(int(total * FPS)):
            t = fi / FPS
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            if t < total_fala:
                lay.alpha_composite(txt_lay)
                desenhar_legenda(lay, blocos, destaques, t)
            else:
                lay.alpha_composite(end_lay)
            al = np.asarray(lay)[..., 3] > 40
            if al[:, :mx].any() or al[:, -mx:].any():
                ruins.append(round(t, 2))
        print("QA borda (R-024):", "ok" if not ruins else f"{len(ruins)} frames fora: {ruins[:10]}")
        return ruins

    def quadro(fr_src, si, t_out, estatico_leg=False, sem_textos=False):
        base = bg.copy()
        if t_out >= total_fala:   # end card
            ke = min(1.0, (t_out - total_fala) / 0.25)
            lay = end_np.copy()
            lay[..., 3] *= RR.ease_out(ke)
            compor(base, lay)
            return base
        s = segs[si]
        t_rel = t_out - s["out0"]
        card = recorte(fr_src, zoom_em(s, t_rel), tuple(s.get("foco", C.get("foco", [0.5, 0.45]))))
        compor(base, moldura)
        reg = base[CARD_Y:CARD_Y + CARD_H, MARG:MARG + CARD_W]
        base[CARD_Y:CARD_Y + CARD_H, MARG:MARG + CARD_W] = reg * (1 - mask) + (card.astype(np.float32) / 255) * mask
        if s.get("transicao") == "flash" and t_rel < 0.18:
            fl = (1 - t_rel / 0.18) ** 2 * 0.85
            base[CARD_Y:CARD_Y + CARD_H, MARG:MARG + CARD_W] = base[CARD_Y:CARD_Y + CARD_H, MARG:MARG + CARD_W] * (1 - fl * mask) + fl * mask
        compor(base, borda)
        if not sem_textos:
            # título: entra com slide/fade nos primeiros 0,35 s
            k = min(1.0, t_out / 0.35)
            tl = txt_np if k >= 1 else txt_np * np.array([1, 1, 1, RR.ease_out(k)], np.float32)
            compor(base, tl)
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            desenhar_legenda(lay, blocos, destaques, t_out, estatico_leg)
            compor(base, rgba_np(lay))
        return base

    def seg_de(t):
        for i, s in enumerate(segs):
            if s["out0"] <= t < s["out0"] + s["dur"]:
                return i
        return len(segs) - 1

    if a.checar:
        checar()
        return
    if a.frames:
        qa = out_dir / f"qa_{nome}"
        qa.mkdir(exist_ok=True)
        for tq in [float(x) for x in a.frames.split(",")]:
            si = seg_de(tq)
            s = segs[si]
            src_t = s["ini"] + (tq - s["out0"])
            rd = Leitor(src_t, 0.1)
            fr = rd.ler()
            rd.fechar()
            img = quadro(fr, si, tq)
            Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(qa / f"t{tq:06.2f}.png")
        print("stills em", qa)
        return

    if checar():
        sys.exit("R-024 falhou: corrija o texto antes do render")

    # ------------------------------------------------ render do vídeo (final + base p/ CapCut)
    final_v = out_dir / f"{nome}.video.mp4"
    cc = PROJ / "06_capcut" / f"camadas_{nome}"
    cc.mkdir(parents=True, exist_ok=True)
    enc = lambda path, crf: subprocess.Popen(  # noqa: E731
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
         "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", str(path)], stdin=subprocess.PIPE)
    e_final = enc(final_v, 16)
    e_base = None if a.sem_capcut else enc(cc / "base.mp4", 14)
    nfr = int(round(total * FPS))
    si_cur, rd = -1, None
    for fi in range(nfr):
        t = fi / FPS
        si = seg_de(t) if t < total_fala else None
        if si is not None and si != si_cur:
            if rd:
                rd.fechar()
            s = segs[si]
            rd = Leitor(s["ini"] + (t - s["out0"]), s["fim"] - (s["ini"] + (t - s["out0"])))
            si_cur = si
        fr = rd.ler() if si is not None else None
        img = quadro(fr, si, t)
        e_final.stdin.write((np.clip(img, 0, 1) * 255).astype(np.uint8).tobytes())
        if e_base:
            b = quadro(fr, si, t, sem_textos=True) if t < total_fala else bg.copy()
            e_base.stdin.write((np.clip(b, 0, 1) * 255).astype(np.uint8).tobytes())
        if fi % 150 == 0:
            print(f"  {nome}: {t:5.1f}/{total:.1f}s", flush=True)
    if rd:
        rd.fechar()
    for e in (e_final, e_base):
        if e:
            e.stdin.close()
            e.wait()

    # ------------------------------------------------ áudio
    sr = 48000
    a_ini = max(0.0, min(x["ini"] for x in segs) - 1.0)
    a_fim = max(x["fim"] for x in segs) + 1.0
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a_ini:.3f}", "-i", str(LIVE), "-t", f"{a_fim - a_ini:.3f}",
                          "-vn", "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    full = np.frombuffer(pcm, np.float32).reshape(-1, 2)
    fade = int(sr * 0.012)
    partes = []
    for k, s in enumerate(segs):
        i0 = int(round((s["ini"] - a_ini) * sr))
        p = full[i0:i0 + int(round(s["dur"] * sr))].copy()
        cont_a = k > 0 and abs(segs[k - 1]["fim"] - s["ini"]) < 0.004
        cont_b = k + 1 < len(segs) and abs(s["fim"] - segs[k + 1]["ini"]) < 0.004
        ramp = np.linspace(0, 1, fade)[:, None]
        if not cont_a:
            p[:fade] *= ramp
        if not cont_b:
            p[-fade:] *= ramp[::-1]
        partes.append(p)
    voz = np.concatenate(partes)
    voz = np.concatenate([voz, np.zeros((int(round(end * sr)), 2), np.float32)])
    n = int(round(total * sr))
    voz = np.pad(voz, ((0, max(0, n - len(voz))), (0, 0)))[:n]
    voz = SFX.eq_voz(voz, sr)
    mp = C.get("musica")
    mus = np.zeros_like(voz)
    if mp:
        mpcm = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(mp.get("inicio", 0)), "-i", mp["arquivo"], "-ac", "2",
                               "-ar", str(sr), "-f", "f32le", "-"], capture_output=True, check=True).stdout
        mus = np.frombuffer(mpcm, np.float32).reshape(-1, 2).copy()
        if len(mus) < n:
            mus = np.tile(mus, (int(np.ceil(n / len(mus))), 1))
        mus = mus[:n] * 10 ** (mp.get("volume_db", -22) / 20)
        env = RR.media_movel(np.abs(voz).max(axis=1), int(sr * 0.05))
        duck = RR.media_movel(np.where(env > 0.02, 10 ** (mp.get("ducking_db", -12) / 20), 1.0), int(sr * 0.25))
        mus *= duck[:, None]
        fo = int(sr * mp.get("fade_out", 1.6))
        mus[-fo:] *= np.linspace(1, 0, fo)[:, None]
        mus[:int(sr * 0.2)] *= np.linspace(0, 1, int(sr * 0.2))[:, None]
    mix = voz + mus
    for ev in C.get("sfx", []):
        clip = SFX.obter(ev, sr, RAIZ, PROJ) * 10 ** (ev.get("vol", -12) / 20)
        i0 = max(0, int((ev["t"] - ev.get("antecipa", 0.0)) * sr))
        i1 = min(n, i0 + len(clip))
        mix[i0:i1] += clip[:i1 - i0]
    alvo = 10 ** (-1.0 / 20)
    if np.abs(mix).max() > alvo:
        mix = np.tanh(mix / alvo * 0.9) * alvo
    wav = out_dir / f"{nome}.wav"
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(2), wf.setsampwidth(2), wf.setframerate(sr)
        wf.writeframes((np.clip(mix, -1, 1) * 32767).astype(np.int16).tobytes())
    rel = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(wav), "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m_i = re.findall(r"I:\s+(-?[\d.]+) LUFS", rel)
    ganho = 10 ** ((-14.0 - float(m_i[-1])) / 20) if m_i else 1.0
    saida = out_dir / f"{nome}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(final_v), "-i", str(wav), "-c:v", "copy",
                    "-af", "loudnorm=I=-14:TP=-1.0:LRA=9", "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
                    "-shortest", "-movflags", "+faststart", str(saida)], check=True)
    final_v.unlink(missing_ok=True)
    print("OK", saida, f"({total:.1f}s)")

    if a.sem_capcut:
        return
    # ------------------------------------------------ camadas do draft FIEL (capcut_ponte_fiel.py)
    for nm, sinal in (("voz.wav", voz), ("musica.wav", mus)):
        with wave.open(str(cc / nm), "wb") as wf:
            wf.setnchannels(2), wf.setsampwidth(2), wf.setframerate(sr)
            wf.writeframes((np.clip(sinal * ganho, -1, 1) * 32767).astype(np.int16).tobytes())
    json.dump({"ganho_master": ganho}, open(cc / "audio.json", "w"))
    png_dir = cc / "png"
    png_dir.mkdir(exist_ok=True)

    def bbox(img):
        al = np.asarray(img)[..., 3]
        ys, xs = np.nonzero(al > 8)
        return [int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())] if len(ys) else [0, 1, 0, 1]

    ev_txt = []
    txt_lay.save(png_dir / "titulo.png")
    ev_txt.append({"t0": 0.0, "t1": total_fala, "png": "png/titulo.png", "bbox": bbox(txt_lay)})
    end_lay.save(png_dir / "end_card.png")
    ev_txt.append({"t0": total_fala, "t1": total, "png": "png/end_card.png", "bbox": bbox(end_lay)})
    ev_leg = []
    k = 0
    for b in blocos:
        ws = b["palavras"]
        for j, w in enumerate(ws):
            t0 = b["t0"] if j == 0 else w["i"] - 0.02
            t1 = b["t1"] if j == len(ws) - 1 else ws[j + 1]["i"] - 0.02
            t1 = min(t1, total_fala)
            if t1 - t0 < 1 / 60:
                continue
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            desenhar_legenda(lay, [b], destaques, w["i"] + 0.001 if j else max(b["t0"], w["i"]) + 0.001, estatico=True)
            fn = f"png/leg_{k:04d}.png"
            lay.save(cc / fn)
            ev_leg.append({"t0": round(t0, 3), "t1": round(t1, 3), "png": fn, "bbox": bbox(lay)})
            k += 1
    json.dump({"w": W, "h": H, "duracao": total, "base": "base.mp4",
               "eventos": {"textos": ev_txt, "legenda": ev_leg}}, open(cc / "camadas.json", "w"), indent=1)
    # plano mínimo para a ponte FIEL (lê só "sfx")
    json.dump({"sfx": C.get("sfx", [])}, open(cc / "plano_fiel.json", "w"))
    print(f"camadas CapCut em {cc} ({len(ev_leg)} PNGs de legenda)")


if __name__ == "__main__":
    main()
