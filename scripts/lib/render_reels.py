"""
Motor de render iGreen — edição de talking head nível agência a partir de um plano JSON.

Uso: python ferramentas/render_reels.py <plano_edicao.json> [--preview N] [--frames t1,t2,...]
  --preview N   renderiza só os N primeiros segundos (teste rápido)
  --frames ...  só exporta stills PNG nesses tempos (QA visual), sem vídeo

Recursos (todos configuráveis no plano, ver skills em .claude/skills/):
  * reenquadramento 16:9 -> 9:16 seguindo o rosto (03_analise/rosto.json)
  * cortes de respiro (segmentos), zoom base alternado por corte, push-in lento, zoom punch por palavra
  * câmera virtual (keyframes cx/cy/zoom) -> pans/"pseudo B-roll" dentro do 4K
  * transições: whip (pan com motion blur), flash, zoom_blur, corte seco
  * moldura/mask camera: card arredondado sobre fundo desfocado
  * letterings com animação (pop, slide, blur, type), camada FRENTE ou ATRÁS da pessoa (segmentação)
  * legendas cinéticas palavra-a-palavra com destaque de palavras-chave
  * color grading (curvas, saturação, temperatura, vinheta, grão)
  * áudio: voz com micro-crossfade nos cortes + SFX procedurais/arquivos + música com ducking
"""
import argparse
import json
import math
import subprocess
import sys
import wave
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# cópia empacotada na skill cortes-live-igreen: fontes e estilos vêm de <skill>/assets e scripts/lib
LIB = Path(__file__).resolve().parent
RAIZ = LIB.parent.parent                      # pasta da skill
FONTES = RAIZ / "assets" / "fontes"
sys.path.insert(0, str(LIB))
import sfx as SFX  # noqa: E402

# ----------------------------------------------------------------------------- util

def media_movel(x, k):
    """Média móvel de janela k (equivale a np.convolve(x, ones(k)/k, 'same')) em O(n) via soma acumulada."""
    x = np.asarray(x, np.float64)
    c = np.concatenate([[0.0], np.cumsum(x)])
    a = np.arange(len(x)) - (k - 1) // 2
    i0 = np.clip(a, 0, len(x)); i1 = np.clip(a + k, 0, len(x))
    return ((c[i1] - c[i0]) / k).astype(np.float32)


def ease_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def ease_in_out(x):
    x = min(max(x, 0.0), 1.0)
    return 3 * x * x - 2 * x * x * x


def back_out(x, s=1.70158):
    x = min(max(x, 0.0), 1.0) - 1
    return x * x * ((s + 1) * x + s) + 1


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


_font_cache = {}


def fonte(nome, tamanho, peso=None):
    key = (nome, int(tamanho), peso)
    if key in _font_cache:
        return _font_cache[key]
    p = FONTES / nome if (FONTES / nome).exists() else Path(nome)
    f = ImageFont.truetype(str(p), int(tamanho))
    if peso is not None:
        try:
            axes = f.get_variation_axes()
            vals = []
            for ax in axes:
                nm = ax.get("name", b"")
                nm = nm.decode() if isinstance(nm, bytes) else str(nm)
                if "eight" in nm or nm.lower().startswith("w"):
                    vals.append(peso)
                elif "ptical" in nm or nm.lower().startswith("o"):
                    vals.append(min(max(tamanho / 2, ax["minimum"]), ax["maximum"]))
                else:
                    vals.append(ax.get("default", ax["minimum"]))
            f.set_variation_by_axes(vals)
        except Exception:
            pass
    _font_cache[key] = f
    return f


# ----------------------------------------------------------------------------- cor

def construir_grade(cfg):
    """Retorna função frame_bgr(uint8) -> frame_bgr graded. Valores na escala do CapCut (-100..100)."""
    x = np.arange(256, dtype=np.float32) / 255.0
    contraste = cfg.get("contraste", 0) / 100.0
    brilho = cfg.get("brilho", 0) / 100.0
    sombras = cfg.get("sombras", 0) / 100.0
    destaques = cfg.get("destaques", 0) / 100.0
    pretos = cfg.get("pretos", 0) / 100.0  # >0 levanta pretos (fade)
    temp = cfg.get("temperatura", 0) / 100.0
    tint = cfg.get("matiz", 0) / 100.0
    sat = cfg.get("saturacao", 0) / 100.0
    vib = cfg.get("vibracao", 0) / 100.0
    vinheta = cfg.get("vinheta", 0) / 100.0
    grao = cfg.get("grao", 0) / 100.0
    nitidez = cfg.get("nitidez", 0) / 100.0
    split_sombra = cfg.get("split_sombras_rgb")  # ex [0,8,10] teal nas sombras (0..255 deslocamento)
    split_luz = cfg.get("split_luzes_rgb")      # ex [10,4,-6] quente nas luzes

    y = x + brilho * 0.25
    y = y + sombras * 0.35 * (1 - y) ** 2 * y * 4 * 0.25 * 4 * (y < 0.5)
    y = y + destaques * 0.35 * (y ** 2) * (1 - y) * 4 * 0.25 * 4 * (y > 0.5)
    # curva S de contraste em torno de 0.5
    if contraste:
        k = 1 + contraste * 1.2
        y = 0.5 + (y - 0.5) * k
        y = np.where(y < 0.5, 0.5 * (2 * np.clip(y, 0, 0.5)) ** (1 + contraste * 0.35),
                     1 - 0.5 * (2 * (1 - np.clip(y, 0.5, 1))) ** (1 + contraste * 0.35))
    y = pretos * 0.12 + y * (1 - pretos * 0.12)
    y = np.clip(y, 0, 1)
    base = (y * 255).astype(np.float32)
    lut_b = base - temp * 18 + tint * 4
    lut_g = base - tint * 10
    lut_r = base + temp * 18 + tint * 4
    if split_sombra or split_luz:
        w_s = (1 - x) ** 2
        w_l = x ** 2
        ss = split_sombra or [0, 0, 0]
        sl = split_luz or [0, 0, 0]
        lut_r = lut_r + w_s * ss[0] + w_l * sl[0]
        lut_g = lut_g + w_s * ss[1] + w_l * sl[1]
        lut_b = lut_b + w_s * ss[2] + w_l * sl[2]
    luts = [np.clip(l, 0, 255).astype(np.uint8) for l in (lut_b, lut_g, lut_r)]
    lut = np.stack(luts, axis=1).reshape(256, 1, 3)
    vign_cache = {}
    # LUT de saturação/vibração no canal S (uint8) — mesma curva, sem float no quadro inteiro
    s01 = np.arange(256, dtype=np.float32) / 255.0
    lut_s = np.clip((s01 * (1 + sat) + vib * s01 * (1 - s01) * 1.5) * 255, 0, 255).astype(np.uint8)
    rng = np.random.default_rng(7)
    grao_cache = {}

    def aplicar(fr):
        out = cv2.LUT(fr, lut)
        if sat or vib:
            hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV)
            hsv[..., 1] = cv2.LUT(hsv[..., 1], lut_s)
            out = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        if nitidez > 0:
            blur = cv2.GaussianBlur(out, (0, 0), 1.2)
            out = cv2.addWeighted(out, 1 + nitidez, blur, -nitidez, 0)
        if vinheta > 0:
            h, w = out.shape[:2]
            if (h, w) not in vign_cache:
                yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
                d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2) / math.sqrt(2)
                v = (1 - vinheta * np.clip(d - 0.35, 0, 1) ** 1.6 * 1.4).astype(np.float32)
                vign_cache[(h, w)] = cv2.merge([v, v, v])
            out = cv2.multiply(out, vign_cache[(h, w)], dtype=cv2.CV_8U)
        if grao > 0:
            h, w = out.shape[:2]
            if (h, w) not in grao_cache:   # 8 quadros de grão pré-gerados, em ciclo (grão "vivo" sem custo por frame)
                grao_cache[(h, w)] = [cv2.merge([g] * 3) for g in
                                      (rng.normal(0, 255 * 0.045 * grao, (h, w)).astype(np.int16) for _ in range(8))]
                grao_cache["i"] = 0
            gi = grao_cache["i"] = (grao_cache["i"] + 1) % 8
            out = cv2.add(out, grao_cache[(h, w)][gi], dtype=cv2.CV_8U) if False else                 np.clip(out.astype(np.int16) + grao_cache[(h, w)][gi], 0, 255).astype(np.uint8)
        return out

    return aplicar


# ----------------------------------------------------------------------------- texto

_linha_cache = {}


def render_linha(txt, est, escala=1.0):
    """Renderiza uma linha de texto como RGBA (PIL) segundo o estilo (com cache: legenda/GC pedem a mesma linha a cada frame)."""
    key = (txt, json.dumps(est, sort_keys=True), escala)
    img = _linha_cache.get(key)
    if img is None:
        if len(_linha_cache) > 4000:
            _linha_cache.clear()
        img = _linha_cache[key] = _render_linha(txt, est, escala)
    return img.copy()


def _render_linha(txt, est, escala=1.0):
    tam = est.get("tamanho", 80) * escala
    f = fonte(est.get("fonte", "Montserrat[wght].ttf"), tam, est.get("peso", 800))
    if est.get("caixa") == "alta":
        txt = txt.upper()
    elif est.get("caixa") == "baixa":
        txt = txt.lower()
    tracking = est.get("tracking", 0) * tam / 100
    # mede
    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    if tracking:
        larg = sum(tmp.textlength(c, font=f) + tracking for c in txt) - tracking
    else:
        larg = tmp.textlength(txt, font=f)
    asc, desc = f.getmetrics()
    pad = int(tam * 0.35) + int(est.get("contorno", 0)) + int(est.get("sombra_blur", 0) * 2)
    W, H = int(larg) + pad * 2, asc + desc + pad * 2
    img = Image.new("RGBA", (max(W, 2), max(H, 2)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cor = hex2rgb(est.get("cor", "#ffffff")) + (255,)
    stroke = int(est.get("contorno", 0))
    stroke_cor = hex2rgb(est.get("contorno_cor", "#000000")) + (255,)

    def desenhar(draw, fill, sw=0, sf=None):
        if tracking:
            x = pad
            for c in txt:
                draw.text((x, pad), c, font=f, fill=fill, stroke_width=sw, stroke_fill=sf)
                x += tmp.textlength(c, font=f) + tracking
        else:
            draw.text((pad, pad), txt, font=f, fill=fill, stroke_width=sw, stroke_fill=sf)

    if est.get("sombra"):
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        desenhar(ImageDraw.Draw(sh), hex2rgb(est.get("sombra_cor", "#000000")) + (int(255 * est.get("sombra_alpha", 0.6)),))
        sh = sh.filter(ImageFilter.GaussianBlur(est.get("sombra_blur", 8)))
        off = est.get("sombra_off", [0, 6])
        img.alpha_composite(sh, (int(off[0]), int(off[1])))
    if est.get("glow"):
        gl = Image.new("RGBA", img.size, (0, 0, 0, 0))
        desenhar(ImageDraw.Draw(gl), hex2rgb(est.get("glow_cor", est.get("cor", "#ffffff"))) + (200,))
        gl = gl.filter(ImageFilter.GaussianBlur(est.get("glow", 12)))
        img.alpha_composite(gl)
    if est.get("caixa_fundo"):
        bg = hex2rgb(est["caixa_fundo"]) + (int(255 * est.get("caixa_alpha", 1.0)),)
        r = int(tam * est.get("caixa_raio", 0.18))
        d.rounded_rectangle([pad * 0.45, pad * 0.55, W - pad * 0.45, H - pad * 0.45], r, fill=bg)
    desenhar(d, cor, stroke, stroke_cor)
    if est.get("gradiente"):
        g0, g1 = hex2rgb(est["gradiente"][0]), hex2rgb(est["gradiente"][1])
        grad = np.zeros((H, W, 3), np.float32)
        for c in range(3):
            grad[..., c] = np.linspace(g0[c], g1[c], H)[:, None]
        a = np.array(img)
        mask = a[..., 3:4] / 255.0
        a[..., :3] = (grad * mask + a[..., :3] * (1 - mask)).astype(np.uint8) if not stroke else a[..., :3]
        img = Image.fromarray(a)
    return img


def _ink_crop_x(img):
    """Recorta colunas totalmente transparentes (para espaçamento real entre palavras)."""
    a = np.array(img)[..., 3]
    cols = np.flatnonzero(a.max(axis=0) > 8)
    if len(cols) == 0:
        return img
    return img.crop((int(cols[0]), 0, int(cols[-1]) + 1, img.height))


_fit_cache = {}
AREA_SEGURA_TEXTO = 0.84     # largura máx. de qualquer lettering (pop_forte cresce ~10% -> 0,92 da largura, dentro da margem)
AREA_SEGURA_LEGENDA = 0.84   # largura máx. de cada linha de legenda (pop ~7%)
MARGEM_BORDA = 0.03          # QA: nenhum pixel de texto (exceto GC de barras) a menos de 3% da borda


def render_linha_fit(txt, est, W_out):
    """Renderiza e reduz o corpo até caber em largura_max (padrão 92% da tela)."""
    key = (txt, json.dumps(est, sort_keys=True), W_out)
    if key in _fit_cache:
        return _fit_cache[key]
    lim = min(est.get("largura_max", 0.92), AREA_SEGURA_TEXTO) * W_out   # R-024: nunca fora da área segura
    img = render_linha(txt, est)
    ink = _ink_crop_x(img)
    if ink.width > lim:
        e2 = dict(est)
        e2["tamanho"] = est.get("tamanho", 80) * lim / ink.width * 0.98
        img = render_linha(txt, e2)
    _fit_cache[key] = img
    return img


_ESTATICO = [False]   # True = camadas p/ CapCut: estado "parado" de cada texto (sem entrada/saída animada)


def animar(img, anim, prog, out_prog):
    """Aplica animação de entrada (prog 0..1) e saída (out_prog 0..1). Retorna (img, alpha, dx, dy)."""
    if _ESTATICO[0]:
        return img, 1.0, 0.0, 0.0
    alpha, dx, dy, sc, blur = 1.0, 0.0, 0.0, 1.0, 0.0
    if anim == "pop":
        sc = 0.55 + 0.45 * back_out(prog, 2.2)
        alpha = ease_out(prog * 1.6)
    elif anim == "pop_forte":
        sc = 0.3 + 0.7 * back_out(prog, 3.0)
        alpha = ease_out(prog * 2.0)
    elif anim == "slide_up":
        dy = (1 - ease_out(prog)) * img.height * 0.6
        alpha = ease_out(prog)
    elif anim == "blur_in":
        blur = (1 - ease_out(prog)) * 18
        sc = 1.12 - 0.12 * ease_out(prog)
        alpha = ease_out(prog)
    elif anim == "fade":
        alpha = ease_out(prog)
    elif anim == "zoom_in_lento":
        sc = 0.9 + 0.1 * ease_out(prog)
        alpha = ease_out(prog * 1.5)
    if out_prog > 0:
        alpha *= 1 - ease_out(out_prog)
        sc *= 1 + 0.08 * out_prog
    if blur > 0.5:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    if abs(sc - 1) > 0.01:
        img = img.resize((max(1, int(img.width * sc)), max(1, int(img.height * sc))), Image.LANCZOS)
    return img, alpha, dx, dy


def colar(base_rgba, img, cx, cy, alpha):
    if alpha <= 0.01:
        return
    if alpha < 1:
        a = np.array(img)
        a[..., 3] = (a[..., 3] * alpha).astype(np.uint8)
        img = Image.fromarray(a)
    x, y = int(cx - img.width / 2), int(cy - img.height / 2)
    base_rgba.alpha_composite(img, (max(0, x), max(0, y)),
                              (max(0, -x), max(0, -y)))


# ----------------------------------------------------------------------------- segmentação (texto atrás)

class Segmentador:
    def __init__(self):
        self.sess = None
        self.prev = None

    def mascara(self, frame_bgr):
        # ONNX direto (u2net_human_seg) — o rembg foi bloqueado pelo Controle de Aplicativo do Windows (numba DLL).
        if self.sess is None:
            import onnxruntime as ort
            modelo = Path(__file__).resolve().parent / "modelos" / "u2net_human_seg.onnx"
            self.sess = ort.InferenceSession(str(modelo), providers=["CPUExecutionProvider"])
            self.inp = self.sess.get_inputs()[0].name
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(cv2.resize(frame_bgr, (320, 320), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
        x = rgb.astype(np.float32) / 255.0
        x = (x - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
        pred = self.sess.run(None, {self.inp: x.transpose(2, 0, 1)[None]})[0][0, 0]
        pred = (pred - pred.min()) / max(1e-6, float(pred.max() - pred.min()))
        m = np.clip((pred - 0.5) * 4 + 0.5, 0, 1).astype(np.float32)  # endurece a borda
        m = cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)
        m = cv2.GaussianBlur(m, (0, 0), 2.0)
        if self.prev is not None and self.prev.shape == m.shape:
            m = 0.6 * m + 0.4 * self.prev  # estabilidade temporal
        self.prev = m
        return m


# ----------------------------------------------------------------------------- vídeo

class Fonte:
    """Lê frames de um trecho da fonte via ffmpeg pipe."""

    def __init__(self, path, W, H):
        self.path, self.W, self.H = path, W, H
        self.proc, self.t_ini, self.n = None, None, 0
        self.fps = None

    def abrir(self, t0, fps):
        self.fechar()
        self.fps = fps
        self.t_ini = t0
        self.n = 0
        self.proc = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-i", self.path, "-an", "-f", "rawvideo",
             "-pix_fmt", "bgr24", "-r", str(fps), "-"], stdout=subprocess.PIPE, bufsize=self.W * self.H * 3 * 2)

    def ler(self):
        buf = self.proc.stdout.read(self.W * self.H * 3)
        if len(buf) < self.W * self.H * 3:
            return None
        self.n += 1
        return np.frombuffer(buf, np.uint8).reshape(self.H, self.W, 3)

    def fechar(self):
        if self.proc:
            self.proc.stdout.close()
            self.proc.kill()
            self.proc = None


def interp_rosto(rosto, t):
    ts = rosto["_t"]
    i = np.searchsorted(ts, t)
    i = min(max(i, 1), len(ts) - 1)
    a, b = rosto["rosto"][i - 1], rosto["rosto"][i]
    k = 0 if b[0] == a[0] else (t - a[0]) / (b[0] - a[0])
    k = min(max(k, 0), 1)
    return [a[j] + (b[j] - a[j]) * k for j in (1, 2, 3)]


def cam_keyframes(kfs, t_rel):
    """kfs: [[t_rel, cx, cy, zoom, (easing)], ...] coordenadas normalizadas da fonte (0..1)."""
    if t_rel <= kfs[0][0]:
        return kfs[0][1:4]
    for a, b in zip(kfs[:-1], kfs[1:]):
        if a[0] <= t_rel <= b[0]:
            k = (t_rel - a[0]) / max(1e-6, b[0] - a[0])
            e = b[4] if len(b) > 4 else "in_out"
            k = ease_in_out(k) if e == "in_out" else ease_out(k) if e == "out" else k
            return [a[j] + (b[j] - a[j]) * k for j in (1, 2, 3)]
    return kfs[-1][1:4]


def crop_frame(fr, cx, cy, zoom, W_out, H_out, base_h_frac=1.0):
    """Recorta janela 9:16 centrada em (cx,cy) px com zoom, mantendo dentro do quadro."""
    H, W = fr.shape[:2]
    ch = H * base_h_frac / zoom
    cw = ch * W_out / H_out
    if cw > W:
        cw = W
        ch = cw * H_out / W_out
    x0 = min(max(cx - cw / 2, 0), W - cw)
    y0 = min(max(cy - ch / 2, 0), H - ch)
    M = np.array([[W_out / cw, 0, -x0 * W_out / cw], [0, H_out / ch, -y0 * H_out / ch]], np.float32)
    return cv2.warpAffine(fr, M, (W_out, H_out), flags=cv2.INTER_AREA if zoom < 1.6 else cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REFLECT)


# ----------------------------------------------------------------------------- legendas

def montar_legendas(palavras, cfg):
    """Agrupa palavras em blocos (max_palavras, quebra em pontuação/pausa)."""
    maxp = cfg.get("max_palavras", 3)
    # grafia correta de marcas/nomes: {"reclama": "Reclame", "aqui": "AQUI"} (casa sem pontuação, sem caixa)
    corr = {k.lower(): v for k, v in cfg.get("corrigir", {}).items()}
    if corr:
        novas = []
        for w in palavras:
            nucleo = w["p"].strip(".,!?;:")
            sub = corr.get(nucleo.lower())
            novas.append(dict(w, p=w["p"].replace(nucleo, sub)) if sub and nucleo else w)
        palavras = novas
    blocos, cur = [], []
    for i, w in enumerate(palavras):
        cur.append(w)
        fim_frase = w["p"].endswith((".", "?", "!", ","))
        pausa = i + 1 < len(palavras) and palavras[i + 1]["i"] - w["f"] > 0.25
        if len(cur) >= maxp or fim_frase or pausa or i == len(palavras) - 1:
            blocos.append(cur)
            cur = []
    out = []
    for i, b in enumerate(blocos):
        t1 = b[-1]["f"] + 0.12
        if i + 1 < len(blocos):
            t1 = min(max(t1, b[-1]["f"]), blocos[i + 1][0]["i"])
        out.append({"t0": b[0]["i"], "t1": t1, "palavras": b})
    return out


# ----------------------------------------------------------------------------- principal

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plano")
    ap.add_argument("--preview", type=float, default=None)
    ap.add_argument("--frames", default=None)
    ap.add_argument("--saida", default=None)
    ap.add_argument("--qa_dir", default="05_render/qa")
    ap.add_argument("--capcut", default=None, help="pasta (no projeto) p/ exportar as camadas do draft FIEL do CapCut:"
                    " base.mp4 (vídeo sem textos de frente), PNGs de lettering/legenda, voz.wav e musica.wav")
    ap.add_argument("--ignorar_borda", action="store_true", help="NÃO usar em entrega: pula a trava R-024")
    ap.add_argument("--checar_textos", action="store_true", help="só roda a trava R-024 (todos os frames, sem vídeo) e sai")
    ap.add_argument("--so_audio", action="store_true", help="reaproveita <saida>.video.mp4 já renderizado e refaz só áudio/mux")
    a = ap.parse_args()

    plano_path = Path(a.plano)
    proj = plano_path.parent
    P = json.load(open(plano_path, encoding="utf-8"))
    W_out, H_out = P.get("w", 1080), P.get("h", 1920)
    fps = P.get("fps", 24000 / 1001)
    src = str((proj / P["fonte"]).resolve()) if not Path(P["fonte"]).is_absolute() else P["fonte"]
    probe = json.loads(subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", src],
                                      capture_output=True, text=True).stdout)
    vs = next(s for s in probe["streams"] if s["codec_type"] == "video")
    SW, SH = int(vs["width"]), int(vs["height"])
    rosto = json.load(open(proj / P["rosto"], encoding="utf-8")) if P.get("rosto") else None
    if rosto:
        rosto["_t"] = np.array([r[0] for r in rosto["rosto"]])
    estilos = json.load(open(LIB / "estilos_igreen.json", encoding="utf-8"))
    estilos.update(P.get("estilos", {}))
    grade = construir_grade(P.get("cor", {}))
    enq = P.get("enquadramento", {"altura_rosto": 0.34})

    segs = P["segmentos"]
    t = 0.0
    for s in segs:
        s["out0"] = t
        s["dur"] = s["dur_saida"] if s.get("congelar") else (s["fim"] - s["ini"]) / s.get("velocidade", 1.0)
        t += s["dur"]
        s["out1"] = t
    total = t if a.preview is None else min(t, a.preview)
    n_frames = int(round(total * fps))

    # legendas
    leg_cfg = P.get("legendas", {"ativo": False})
    if "palavras" not in P and P.get("cortes"):
        P["palavras"] = json.load(open(proj / P["cortes"], encoding="utf-8"))["palavras"]
    blocos = montar_legendas(P.get("palavras", []), leg_cfg) if leg_cfg.get("ativo") else []
    destaques = {k.lower(): v for k, v in leg_cfg.get("destaques", {}).items()}
    ocultar = [(o[0], o[1]) for o in leg_cfg.get("ocultar_em", [])]

    textos = P.get("textos", [])
    trans = {tr["corte"]: tr for tr in P.get("transicoes", [])}
    precisa_mask = any(tx.get("camada") == "atras" for tx in textos)
    segm = Segmentador() if precisa_mask else None

    frames_q = None
    if a.frames:
        frames_q = sorted(float(x) for x in a.frames.split(","))
        n_frames = 0

    saida = Path(a.saida) if a.saida else proj / P.get("saida", "05_render/final.mp4")
    saida.parent.mkdir(parents=True, exist_ok=True)
    video_tmp = saida.with_suffix(".video.mp4")
    enc = None
    if a.so_audio:
        assert video_tmp.exists(), f"não existe {video_tmp}"
        n_frames = 0
    if frames_q is None and not a.so_audio:
        enc = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W_out}x{H_out}",
             "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", P.get("preset", "medium"), "-crf",
             str(P.get("crf", 17)), "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709",
             "-colorspace", "bt709", "-movflags", "+faststart", str(video_tmp)], stdin=subprocess.PIPE)

    fonte_v = Fonte(src, SW, SH)
    cur_seg = -1
    last_frame_by_seg = {}

    def camera_para(si, t_rel_src, t_out):
        """Retorna (cx, cy, zoom) em px da fonte para o segmento si."""
        s = segs[si]
        z0, z1 = s.get("zoom", [1.0, 1.0]) if isinstance(s.get("zoom"), list) else (s.get("zoom", 1.0),) * 2
        k = (t_out - s["out0"]) / max(1e-6, s["dur"])
        z = z0 + (z1 - z0) * ease_in_out(k)
        for p in s.get("punch", []):
            if t_out >= p["t"]:
                d = p.get("dur", 0.18)
                z *= 1 + (p["z"] - 1) * ease_out((t_out - p["t"]) / d)
        if s.get("cam"):
            cxn, cyn, zc = cam_keyframes(s["cam"], t_out - s["out0"])
            return cxn * SW, cyn * SH, z * zc
        if rosto:
            fx, fy, fsz = interp_rosto(rosto, s["ini"] + t_rel_src)
        else:
            fx, fy, fsz = SW / 2, SH / 3, SH / 5
        ch = SH / z
        cy = fy + ch * (0.5 - enq.get("altura_rosto", 0.34))
        off = enq.get("offset_x", 0.0)
        if s.get("desloc"):  # câmera desliza para abrir espaço ao título: [[t_rel, offset_frac], ...]
            kf = s["desloc"]
            tr_ = t_out - s["out0"]
            if tr_ <= kf[0][0]:
                off += kf[0][1]
            elif tr_ >= kf[-1][0]:
                off += kf[-1][1]
            else:
                for ka, kb in zip(kf[:-1], kf[1:]):
                    if ka[0] <= tr_ <= kb[0]:
                        off += ka[1] + (kb[1] - ka[1]) * ease_in_out((tr_ - ka[0]) / max(1e-6, kb[0] - ka[0]))
                        break
        cx = fx + off * SW
        # painel de slides na fonte (live com tela dividida): o recorte não invade x >= painel_x
        pn = enq.get("painel")
        if pn and fx < pn.get("se_rosto_x_menor", 1e9):
            cw = (SH / z) * W_out / H_out
            cx = min(cx, pn["x"] - cw / 2)
        return cx, cy, z

    def frame_fonte(si, t_out):
        """Lê o frame da fonte correspondente a t_out dentro do segmento si (sequencial)."""
        nonlocal cur_seg
        s = segs[si]
        if cur_seg != si:
            fonte_v.abrir(s["ini"], fps / s.get("velocidade", 1.0) if s.get("velocidade", 1.0) != 1 else fps)
            cur_seg = si
        if s.get("congelar") and last_frame_by_seg.get(si) is not None:
            return last_frame_by_seg[si]   # freeze frame
        fr = fonte_v.ler()
        if fr is None:
            fr = last_frame_by_seg.get(si)
        last_frame_by_seg[si] = fr
        return fr

    def compor(fi, t_out, fr_src, si):
        s = segs[si]
        t_rel = 0.0 if s.get("congelar") else (t_out - s["out0"]) * s.get("velocidade", 1.0)  # freeze: rosto do quadro parado
        cx, cy, z = camera_para(si, t_rel, t_out)
        fr = crop_frame(fr_src, cx, cy, z, W_out, H_out)
        # transição de entrada neste segmento
        tr = trans.get(si)
        if tr:
            d = tr.get("dur", 0.25)
            k = (t_out - s["out0"]) / d
            if 0 <= k < 1:
                fr = aplicar_transicao(fr, tr["tipo"], k, entrando=True, tr=tr)
        tr2 = trans.get(si + 1)
        if tr2:
            d = tr2.get("dur", 0.25)
            k = (s["out1"] - t_out) / d
            if 0 <= k < 1:
                fr = aplicar_transicao(fr, tr2["tipo"], k, entrando=False, tr=tr2)
        if s.get("moldura"):
            fr = aplicar_moldura(fr, s["moldura"], t_out - s["out0"])
        fr = grade(fr)
        return fr

    def aplicar_transicao(fr, tipo, k, entrando, tr):
        # k: 0 no ponto do corte -> 1 longe dele
        inten = 1 - ease_out(k)
        if tipo == "flash":
            return cv2.addWeighted(fr, 1 - inten * 0.85, np.full_like(fr, 255), inten * 0.85, 0)
        if tipo == "whip":
            ksz = int(3 + inten * tr.get("forca", 90))
            ker = np.zeros((1, ksz), np.float32)
            ker[0, :] = 1.0 / ksz
            b = cv2.filter2D(fr, -1, ker)
            sh = int(inten * W_out * 0.18) * (1 if entrando else -1) * tr.get("direcao", 1)
            return np.roll(b, sh, axis=1)
        if tipo == "zoom_blur":
            sc = 1 + inten * 0.18
            M = cv2.getRotationMatrix2D((W_out / 2, H_out / 2), 0, sc)
            zf = cv2.warpAffine(fr, M, (W_out, H_out), borderMode=cv2.BORDER_REFLECT)
            acc = zf.astype(np.float32)
            for i in range(1, 5):
                M = cv2.getRotationMatrix2D((W_out / 2, H_out / 2), 0, sc * (1 + inten * 0.03 * i))
                acc += cv2.warpAffine(fr, M, (W_out, H_out), borderMode=cv2.BORDER_REFLECT)
            return (acc / 5).astype(np.uint8)
        if tipo == "shake":
            dx = int(math.sin(k * 40) * inten * 22)
            dy = int(math.cos(k * 33) * inten * 14)
            M = np.float32([[1.04, 0, dx - W_out * 0.02], [0, 1.04, dy - H_out * 0.02]])
            return cv2.warpAffine(fr, M, (W_out, H_out), borderMode=cv2.BORDER_REFLECT)
        return fr

    def aplicar_moldura(fr, m, t_rel):
        """Mask camera: vídeo dentro de card arredondado sobre fundo desfocado/cor."""
        marg = int(m.get("margem", 70))
        raio = int(m.get("raio", 48))
        prog = ease_out(t_rel / m.get("entrada", 0.3)) if m.get("entrada") else 1
        if m.get("fundo", "blur") == "blur":
            bg = cv2.GaussianBlur(cv2.resize(fr, (W_out // 8, H_out // 8)), (0, 0), 4)
            bg = cv2.resize(bg, (W_out, H_out))
            bg = (bg * 0.55).astype(np.uint8)
        else:
            bg = np.full_like(fr, hex2rgb(m["fundo"])[::-1])
        cw, ch = W_out - 2 * marg, int((H_out - 2 * marg) * m.get("altura", 1.0))
        sc = 0.9 + 0.1 * prog
        cw2, ch2 = int(cw * sc), int(ch * sc)
        # NUNCA redimensionar o quadro direto para o card (achata/estica a imagem — feedback do cliente, R-013):
        # recorta do quadro a mesma proporção do card (cover), ancorado no rosto (terço superior), e só então escala.
        ar_card = cw2 / ch2
        if ar_card > W_out / H_out:          # card mais "largo" que o quadro -> corta altura
            rw, rh = W_out, int(round(W_out / ar_card))
        else:                                 # card mais "alto" -> corta largura
            rw, rh = int(round(H_out * ar_card)), H_out
        ry = int(min(max(0, H_out * m.get("ancora_y", 0.40) - rh / 2), H_out - rh))
        rx = (W_out - rw) // 2
        inner = cv2.resize(fr[ry:ry + rh, rx:rx + rw], (cw2, ch2), interpolation=cv2.INTER_AREA)
        mask = np.zeros((ch2, cw2), np.uint8)
        cv2.rectangle(mask, (raio, 0), (cw2 - raio, ch2), 255, -1)
        cv2.rectangle(mask, (0, raio), (cw2, ch2 - raio), 255, -1)
        for (px, py) in ((raio, raio), (cw2 - raio, raio), (raio, ch2 - raio), (cw2 - raio, ch2 - raio)):
            cv2.circle(mask, (px, py), raio, 255, -1, lineType=cv2.LINE_AA)
        mask = cv2.GaussianBlur(mask, (3, 3), 0).astype(np.float32)[..., None] / 255.0
        x0, y0 = (W_out - cw2) // 2, int(m.get("y", (H_out - ch2) // 2))
        out = bg.copy()
        # sombra do card
        sh = np.zeros((H_out, W_out), np.float32)
        sh[y0 + 18:y0 + 18 + ch2, x0:x0 + cw2] = mask[..., 0]
        sh = cv2.GaussianBlur(sh, (0, 0), 22)[..., None] * 0.6
        out = (out * (1 - sh)).astype(np.uint8)
        roi = out[y0:y0 + ch2, x0:x0 + cw2]
        out[y0:y0 + ch2, x0:x0 + cw2] = (inner * mask + roi * (1 - mask)).astype(np.uint8)
        if m.get("borda"):
            cor = hex2rgb(m["borda"])[::-1]
            cv2.rectangle(out, (x0, y0), (x0 + cw2, y0 + ch2), cor, 0)
        return out

    def overlay_atras(fr, t_out):
        """Textos 'atras' (entre fundo e pessoa, via segmentação)."""
        atras = [tx for tx in textos if tx.get("camada") == "atras" and tx["t0"] <= t_out < tx["t1"]]
        if atras:
            m = segm.mascara(fr)
            layer = Image.new("RGBA", (W_out, H_out), (0, 0, 0, 0))
            for tx in atras:
                desenhar_texto(layer, tx, t_out)
            la = np.array(layer)
            ys, xs = np.flatnonzero(la[..., 3].any(axis=1)), np.flatnonzero(la[..., 3].any(axis=0))
            if len(ys):
                y0, y1, x0, x1 = ys[0], ys[-1] + 1, xs[0], xs[-1] + 1
                sub = la[y0:y1, x0:x1].astype(np.float32)
                alpha = sub[..., 3:4] / 255.0 * (1 - m[y0:y1, x0:x1, None])
                fr = fr.copy()
                fr[y0:y1, x0:x1] = (fr[y0:y1, x0:x1] * (1 - alpha) + sub[..., :3][..., ::-1] * alpha).astype(np.uint8)
        return fr

    def camada_frente(t_out, quais=("textos", "legenda"), sem_gc=False):
        """RGBA (PIL) dos textos de frente e/ou da legenda no instante t_out."""
        layer = Image.new("RGBA", (W_out, H_out), (0, 0, 0, 0))
        if "textos" in quais:
            for tx in textos:
                if sem_gc and tx.get("tipo") == "gc_barras":
                    continue
                if tx.get("camada", "frente") == "frente" and tx["t0"] <= t_out < tx["t1"]:
                    desenhar_texto(layer, tx, t_out)
        if "legenda" in quais and blocos and not any(o0 <= t_out < o1 for o0, o1 in ocultar):
            desenhar_legenda(layer, t_out)
        return layer

    def compor_camada(fr, la):
        ys = np.flatnonzero(la[..., 3].any(axis=1))
        if len(ys):
            xs = np.flatnonzero(la[..., 3].any(axis=0))
            y0, y1, x0, x1 = ys[0], ys[-1] + 1, xs[0], xs[-1] + 1
            sub = la[y0:y1, x0:x1]
            alpha = sub[..., 3:4].astype(np.float32) / 255.0
            fr = fr.copy()
            fr[y0:y1, x0:x1] = (fr[y0:y1, x0:x1] * (1 - alpha) + sub[..., :3][..., ::-1] * alpha).astype(np.uint8)
        return fr

    def overlay_textos(fr, t_out):
        """Desenha textos e legendas. Textos 'atras' ficam entre fundo e pessoa."""
        return compor_camada(overlay_atras(fr, t_out), np.array(camada_frente(t_out)))

    def desenhar_gc_barras(layer, tx, t_out):
        """GC estilo REF11 (vídeo interno iGreen): barra preta full-width com NOME branco alinhado à direita +
        barra verde neon com CARGO verde-escuro. Entrada: barras em wipe da direita + texto revelado da direita
        p/ esquerda. Saída: textos esmaecem e a barra verde recolhe para a esquerda."""
        g = tx.get("gc", {})
        y0 = int(g.get("y", 0.843) * H_out)               # topo da barra preta (REF11: 1618/1920)
        h1 = int(g.get("h_nome", 0.080) * H_out)           # 154 px
        h2 = int(g.get("h_cargo", 0.044) * H_out)          # 84 px
        cor1 = hex2rgb(g.get("cor_barra_nome", "#000000"))
        cor2 = hex2rgb(g.get("cor_barra_cargo", "#38FD25"))
        din = tx.get("dur_anim", 0.40)
        dout = tx.get("dur_saida", 0.50)
        pin = ease_out(min(1.0, max(0.0, (t_out - tx["t0"]) / din)))
        pout = ease_in_out(min(1.0, max(0.0, (t_out - (tx["t1"] - dout)) / dout)))
        if _ESTATICO[0]:
            pin, pout = 1.0, 0.0
        d = ImageDraw.Draw(layer)
        a1 = int(255 * g.get("alpha_nome", 1.0) * (1 - pout))
        # barra preta: wipe da direita para a esquerda na entrada (2x mais rápida que o texto)
        xb = int(W_out * (1 - min(1.0, pin * 1.8)))
        if a1 > 2:
            d.rectangle([xb, y0, W_out, y0 + h1], fill=cor1 + (a1,))
        # barra verde: entra junto; na saída recolhe para a esquerda
        x2a, x2b = xb, int(W_out * (1 - pout))
        if x2b > x2a:
            d.rectangle([x2a, y0 + h1, x2b, y0 + h1 + h2], fill=cor2 + (255,))
        # textos com revelação por máscara (direita -> esquerda)
        rev_x = int(W_out * (1 - pin))
        for chave, est_nome, cy, alinh in (("nome", "gc_nome", y0 + h1 / 2, "dir"),
                                           ("cargo", "gc_cargo", y0 + h1 + h2 / 2, "centro")):
            txt = g.get(chave)
            if not txt:
                continue
            est = dict(estilos.get(est_nome, {}))
            img = _ink_crop_x(render_linha(txt, est))
            a = np.array(img)
            rows = np.flatnonzero(a[..., 3].max(axis=1) > 8)
            if len(rows):
                img = img.crop((0, int(rows[0]), img.width, int(rows[-1]) + 1))
            if alinh == "dir":
                x = int(W_out * g.get("x_nome_dir", 0.957)) - img.width
            else:
                x = int(W_out * g.get("x_cargo", 0.597) - img.width / 2)
            # baseline: centra a altura de caixa-alta (para o cargo, o bloco inteiro)
            y = int(cy - img.height / 2 + (est.get("tamanho", 60) * g.get("ajuste_y_" + chave, 0.0)))
            al = (1 - pout) if chave == "nome" else (1 - pout * 0.6)
            if al <= 0.02:
                continue
            ar = np.array(img)
            corte = max(0, rev_x - x)          # colunas ainda não reveladas
            if corte >= img.width:
                continue
            ar[:, :corte, 3] = 0
            ar[..., 3] = (ar[..., 3] * al).astype(np.uint8)
            layer.alpha_composite(Image.fromarray(ar), (max(0, x), max(0, y)), (max(0, -x), max(0, -y)))

    def desenhar_texto(layer, tx, t_out):
        if tx.get("tipo") == "gc_barras":
            return desenhar_gc_barras(layer, tx, t_out)
        y = tx.get("pos", [0.5, 0.5])[1] * H_out
        x0 = tx.get("pos", [0.5, 0.5])[0] * W_out
        gap = tx.get("entrelinha", 0.0)
        for li, ln in enumerate(tx["linhas"]):
            est = dict(estilos.get(ln.get("estilo", "titulo"), {}))
            est.update(ln.get("override", {}))
            t_in = tx["t0"] + ln.get("atraso", li * tx.get("cascata", 0.0))
            if t_out < t_in:
                img = render_linha_fit(ln["txt"], est, W_out)
                y += img.height * (0.78 + gap)
                continue
            img = render_linha_fit(ln["txt"], est, W_out)
            prog = (t_out - t_in) / tx.get("dur_anim", 0.22)
            out_prog = max(0.0, (t_out - (tx["t1"] - tx.get("dur_saida", 0.15))) / tx.get("dur_saida", 0.15)) if tx.get("saida", True) else 0
            im2, alpha, dx, dy = animar(img, ln.get("anim", tx.get("anim", "pop")), prog, out_prog)
            colar(layer, im2, x0 + dx + ln.get("dx", 0) * W_out, y + img.height / 2 + dy, alpha)
            y += img.height * (0.78 + gap)

    def desenhar_legenda(layer, t_out):
        b = next((b for b in blocos if b["t0"] - 0.03 <= t_out < b["t1"]), None)
        if b is None:
            return
        est_n = dict(estilos[leg_cfg.get("estilo", "legenda")])
        est_d = dict(estilos[leg_cfg.get("estilo_destaque", "legenda_destaque")])
        y = leg_cfg.get("y", 0.70) * H_out
        imgs = []
        for w in b["palavras"]:
            limpo = w["p"].strip(".,!?").lower()
            dest = destaques.get(limpo)
            est = dict(est_d) if dest else dict(est_n)
            if dest and dest != "sim":
                est["cor"] = dest
            visivel = t_out >= w["i"] - 0.02
            imgs.append((_ink_crop_x(render_linha(w["p"].strip(",") if not leg_cfg.get("pontuacao") else w["p"], est)), visivel, w))
        sp = est_n.get("tamanho", 70) * 0.26
        # R-024 (cliente: "aproximadamente" saiu da tela): quebra gulosa por largura real e, se uma linha ainda
        # passar da área segura (84% da largura — o pop de entrada cresce até ~7%), reduz SÓ aquela linha.
        lim = W_out * AREA_SEGURA_LEGENDA
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
        ajust = []
        for ln in linhas:
            lw = sum(im.width for im, _, _ in ln) + (len(ln) - 1) * sp
            if lw > lim:
                f = lim / lw
                ln = [(im.resize((max(1, int(im.width * f)), max(1, int(im.height * f))), Image.LANCZOS), v, w)
                      for im, v, w in ln]
            ajust.append(ln)
        linhas = ajust
        for li, ln in enumerate(linhas):
            pad_cut = -sp
            lw = sum(im.width for im, _, _ in ln) - (len(ln) - 1) * pad_cut
            x = W_out / 2 - lw / 2
            for im, vis, w in ln:
                if vis:
                    prog = (t_out - w["i"]) / 0.16
                    im2, alpha, dx, dy = animar(im, leg_cfg.get("anim", "pop"), prog, 0)
                    colar(layer, im2, x + im.width / 2 + dx, y + dy, alpha)
                x += im.width - pad_cut
            y += max(im.height for im, _, _ in ln) * 0.66

    def checar_bordas(tempos):
        """R-024: nenhum texto (legenda, lettering, atrás) a menos de MARGEM_BORDA da borda lateral, em nenhum frame
        (inclui o crescimento do pop de entrada). Retorna lista de (t, onde, texto_da_legenda)."""
        mx = int(W_out * MARGEM_BORDA)
        ruins = []
        for tq in tempos:
            camadas = [("frente", np.array(camada_frente(tq, sem_gc=True)))]
            atras_ = [tx for tx in textos if tx.get("camada") == "atras" and tx["t0"] <= tq < tx["t1"]]
            if atras_:
                lay = Image.new("RGBA", (W_out, H_out), (0, 0, 0, 0))
                for tx in atras_:
                    desenhar_texto(lay, tx, tq)
                camadas.append(("atras", np.array(lay)))
            for nome, la in camadas:
                a_ = la[..., 3] > 40
                if a_[:, :mx].any() or a_[:, -mx:].any():
                    b = next((b for b in blocos if b["t0"] - 0.03 <= tq < b["t1"]), None)
                    ruins.append((round(tq, 2), nome, " ".join(w["p"] for w in b["palavras"]) if b else ""))
        return ruins

    # ---------------------------------------------------------------- loop
    if a.checar_textos:
        ruins = checar_bordas([fi / fps for fi in range(int(round(total * fps)))])
        vistos = {}
        for tq, nome, txt in ruins:
            vistos.setdefault((nome, txt), tq)
        for (nome, txt), tq in sorted(vistos.items(), key=lambda x: x[1]):
            print(f"   {tq:7.2f}s  [{nome}] {txt}")
        print("R-024:", "ok" if not ruins else f"{len(vistos)} problemas")
        return
    if not a.ignorar_borda and (frames_q is None and not a.so_audio):
        ruins = checar_bordas([fi / fps for fi in range(int(round(total * fps)))])
        if ruins:
            vistos = {}
            for tq, nome, txt in ruins:
                vistos.setdefault((nome, txt), tq)
            print("ERRO R-024: texto encostando/saindo da borda — render ABORTADO. Corrija o plano:")
            for (nome, txt), tq in sorted(vistos.items(), key=lambda x: x[1]):
                print(f"   {tq:7.2f}s  [{nome}] {txt}")
            raise SystemExit(2)
        print("QA borda: nenhum texto fora da área segura em", int(round(total * fps)), "frames (R-024 ok)")
    if frames_q is not None:
        ruins = checar_bordas(frames_q)
        if ruins:
            print("ATENÇÃO R-024 (stills): texto na borda em", ruins)
        outdir = proj / a.qa_dir
        outdir.mkdir(parents=True, exist_ok=True)
        for tq in frames_q:
            si = next(i for i, s in enumerate(segs) if s["out0"] <= tq < s["out1"])
            s = segs[si]
            t_src = s["ini"] if s.get("congelar") else s["ini"] + (tq - s["out0"]) * s.get("velocidade", 1.0)
            fonte_v.abrir(t_src, fps)
            fr_src = fonte_v.ler()
            cur_seg = -1
            fr = compor(0, tq, fr_src, si)
            if segm:
                segm.prev = None
            fr = overlay_textos(fr, tq)
            cv2.imwrite(str(outdir / f"qa_{tq:06.2f}.jpg"), fr, [cv2.IMWRITE_JPEG_QUALITY, 90])
        fonte_v.fechar()
        print("QA frames em", outdir)
        return

    cc_dir = (proj / a.capcut) if a.capcut else None
    enc_base, cc_ev, cc_prev = None, {"textos": [], "legenda": []}, {"textos": None, "legenda": None}
    import hashlib
    if cc_dir and n_frames:
        (cc_dir / "png").mkdir(parents=True, exist_ok=True)
        enc_base = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W_out}x{H_out}",
             "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "14", "-pix_fmt", "yuv420p",
             "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-movflags", "+faststart",
             str(cc_dir / "base.mp4")], stdin=subprocess.PIPE)

    def cc_registrar(qual, la, t_out):
        """Agrupa frames consecutivos com a MESMA camada estática num evento (um PNG no CapCut)."""
        ys = np.flatnonzero(la[..., 3].any(axis=1))
        if len(ys):
            xs = np.flatnonzero(la[..., 3].any(axis=0))
            bb = (int(ys[0]), int(ys[-1]) + 1, int(xs[0]), int(xs[-1]) + 1)
            h = hashlib.md5(la[bb[0]:bb[1], bb[2]:bb[3]].tobytes() + str(bb).encode()).hexdigest()
        else:
            bb, h = None, None
        ev = cc_prev[qual]
        if ev and ev["hash"] == h:
            ev["t1"] = round(t_out + 1 / fps, 4)
            return
        if h:
            nome = f"{qual}_{len(cc_ev[qual]):04d}.png"
            cv2.imwrite(str(cc_dir / "png" / nome), cv2.cvtColor(la, cv2.COLOR_RGBA2BGRA), [cv2.IMWRITE_PNG_COMPRESSION, 3])
            ev = {"png": f"png/{nome}", "t0": round(t_out, 4), "t1": round(t_out + 1 / fps, 4), "bbox": bb, "hash": h}
            cc_ev[qual].append(ev)
            cc_prev[qual] = ev
        else:
            cc_prev[qual] = None

    si = 0
    for fi in range(n_frames):
        t_out = fi / fps
        while si < len(segs) - 1 and t_out >= segs[si]["out1"]:
            si += 1
            if segm:
                segm.prev = None
        fr_src = frame_fonte(si, t_out)
        fr = compor(fi, t_out, fr_src, si)
        fr = overlay_atras(fr, t_out)
        if enc_base:
            enc_base.stdin.write(np.ascontiguousarray(fr).tobytes())
            _ESTATICO[0] = True
            for qual in ("textos", "legenda"):
                cc_registrar(qual, np.array(camada_frente(t_out, (qual,))), t_out)
            _ESTATICO[0] = False
        fr = compor_camada(fr, np.array(camada_frente(t_out)))
        enc.stdin.write(np.ascontiguousarray(fr).tobytes())
        if fi % 48 == 0:
            print(f"\rframe {fi}/{n_frames} ({t_out:.1f}s)", end="", flush=True)
    fonte_v.fechar()
    if enc:
        enc.stdin.close()
        enc.wait()
    if enc_base:
        enc_base.stdin.close()
        enc_base.wait()
        for qual in cc_ev:
            for ev in cc_ev[qual]:
                ev.pop("hash", None)
        json.dump({"fps": fps, "w": W_out, "h": H_out, "duracao": total, "base": "base.mp4", "eventos": cc_ev},
                  open(cc_dir / "camadas.json", "w", encoding="utf-8"), indent=1)
        print(f"camadas CapCut: base.mp4 + {len(cc_ev['textos'])} PNG de lettering + {len(cc_ev['legenda'])} PNG de legenda")
    print()

    # ---------------------------------------------------------------- áudio
    sr = 48000
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vn", "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    full = np.frombuffer(pcm, np.float32).reshape(-1, 2)
    partes = []
    fade = int(sr * 0.012)

    def _continuo(a, b):
        """Áudio de a emenda sem salto no de b (mesma fonte, fim == ini, ambos com voz, velocidade 1)."""
        voz_a = not s_mudo(a)
        voz_b = not s_mudo(b)
        return (voz_a and voz_b and abs(a["fim"] - b["ini"]) < 0.004
                and a.get("velocidade", 1.0) == 1.0 and b.get("velocidade", 1.0) == 1.0)

    def s_mudo(x):
        return x.get("mudo") or (x.get("congelar") and not x.get("manter_audio"))

    for si_a, s in enumerate(segs):
        if s["out0"] >= total:
            break
        vel = s.get("velocidade", 1.0)
        a0, a1 = int(s["ini"] * sr), int(min(s["fim"], s["ini"] + (total - s["out0"]) * vel) * sr)
        p = full[a0:a1].copy()
        if s.get("congelar") and not s.get("manter_audio"):  # freeze frame: sem voz, duração = dur_saida (a música segue por baixo)
            p = np.zeros((int(round(s["dur"] * sr)), 2), np.float32)
        elif vel != 1.0 and len(p) > 1:  # speed ramp: reamostra para a duração de saída (B-roll costuma ir com mudo)
            n_out = max(1, int(round(len(p) / vel)))
            xi = np.linspace(0, len(p) - 1, n_out)
            p = np.stack([np.interp(xi, np.arange(len(p)), p[:, c]) for c in range(2)], axis=1).astype(np.float32)
        if s.get("mudo"):
            p[:] = 0
        # fade SÓ onde há descontinuidade real: corte contínuo na fonte (divisão do ritmo/freeze com voz) NÃO leva fade,
        # senão abre um buraco de ~24 ms no meio da palavra (bug do v1: "vida transformada" falhando — R-019)
        if len(p) > 2 * fade:
            ramp = np.linspace(0, 1, fade)[:, None]
            if not (si_a > 0 and _continuo(segs[si_a - 1], s)):
                p[:fade] *= ramp
            if not (si_a + 1 < len(segs) and segs[si_a + 1]["out0"] < total and _continuo(s, segs[si_a + 1])):
                p[-fade:] *= ramp[::-1]
        partes.append(p)
    voz = np.concatenate(partes) if partes else np.zeros((1, 2), np.float32)
    # QA automático (R-019): nenhuma emenda contínua pode ter "buraco" na voz
    _mono = np.abs(voz).mean(axis=1)
    _w = int(sr * 0.004)
    _ruins = []
    for si_a in range(1, len(segs)):
        b = segs[si_a]
        if b["out0"] >= total or not _continuo(segs[si_a - 1], b):
            continue
        c = int(round(b["out0"] * sr))
        if c - 8 * _w < 0 or c + 8 * _w > len(_mono):
            continue
        e = [20 * np.log10(np.sqrt((_mono[c + k * _w:c + (k + 1) * _w] ** 2).mean()) + 1e-9) for k in range(-8, 8)]
        # mesma medida na FONTE, no ponto da emenda: só é defeito se a saída afunda além do que a própria fala afunda
        cs_ = int(round(b["ini"] * sr))
        _fm = np.abs(full).mean(axis=1)
        ef = [20 * np.log10(np.sqrt((_fm[cs_ + k * _w:cs_ + (k + 1) * _w] ** 2).mean()) + 1e-9) for k in range(-8, 8)]
        ctx, ctxf = float(np.median(e[:4] + e[-4:])), float(np.median(ef[:4] + ef[-4:]))
        queda, queda_f = ctx - min(e[6:10]), ctxf - min(ef[6:10])
        if ctx > -40 and queda - queda_f > 6:
            _ruins.append(f"{b['out0']:.2f}s (-{queda:.1f} dB vs fonte -{queda_f:.1f} dB)")
    if _ruins:
        print("ATENÇÃO R-019: queda de voz em emendas contínuas:", ", ".join(_ruins))
    else:
        print("QA voz: emendas contínuas sem queda (R-019 ok)")
    aud = P.get("audio", {})
    voz *= 10 ** (aud.get("voz_ganho_db", 0) / 20)
    if aud.get("voz_eq", True):
        voz = SFX.eq_voz(voz, sr)
    mix = voz.copy()
    n = len(mix)
    mus_final = np.zeros_like(mix)
    # música com ducking
    if aud.get("musica"):
        mp = aud["musica"]
        mpath = str((proj / mp["arquivo"]).resolve()) if not Path(mp["arquivo"]).is_absolute() else mp["arquivo"]
        mpcm = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(mp.get("inicio", 0)), "-i", mpath, "-ac", "2",
                               "-ar", str(sr), "-f", "f32le", "-"], capture_output=True, check=True).stdout
        mus = np.frombuffer(mpcm, np.float32).reshape(-1, 2).copy()
        if len(mus) < n:
            mus = np.tile(mus, (int(np.ceil(n / len(mus))), 1))
        mus = mus[:n] * 10 ** (mp.get("volume_db", -16) / 20)
        env = np.abs(voz).max(axis=1)
        k = int(sr * 0.05)
        env = media_movel(env, k)
        duck = np.where(env > 0.02, 10 ** (mp.get("ducking_db", -8) / 20), 1.0)
        k2 = int(sr * 0.25)
        duck = media_movel(duck, k2)
        mus *= duck[:, None]
        fo = int(sr * mp.get("fade_out", 1.5))
        mus[-fo:] *= np.linspace(1, 0, fo)[:, None]
        mus[: int(sr * 0.3)] *= np.linspace(0, 1, int(sr * 0.3))[:, None]
        mix += mus
        mus_final = mus
    for ev in P.get("sfx", []):
        if ev["t"] >= total:
            continue
        clip = SFX.obter(ev, sr, RAIZ, proj)
        clip = clip * 10 ** (ev.get("vol", -12) / 20)
        i0 = int((ev["t"] - ev.get("antecipa", 0.0)) * sr)
        i0 = max(0, i0)
        i1 = min(n, i0 + len(clip))
        mix[i0:i1] += clip[: i1 - i0]
    # limiter suave
    peak = np.abs(mix).max()
    alvo = 10 ** (-1.0 / 20)
    mix = np.tanh(mix / alvo * 0.9) * alvo if peak > alvo else mix
    wav_tmp = saida.with_suffix(".wav")
    with wave.open(str(wav_tmp), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((np.clip(mix, -1, 1) * 32767).astype(np.int16).tobytes())
    if a.capcut:
        cc_dir = proj / a.capcut
        cc_dir.mkdir(parents=True, exist_ok=True)
        rel = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(wav_tmp), "-af", "ebur128", "-f", "null", "-"],
                             capture_output=True, text=True).stderr
        import re as _re
        m_i = _re.findall(r"I:\s+(-?[\d.]+) LUFS", rel)
        ganho = 10 ** ((-14.0 - float(m_i[-1])) / 20) if m_i else 1.0
        for nome, sinal in (("voz.wav", voz), ("musica.wav", mus_final)):
            with wave.open(str(cc_dir / nome), "wb") as wf:
                wf.setnchannels(2), wf.setsampwidth(2), wf.setframerate(sr)
                wf.writeframes((np.clip(sinal * ganho, -1, 1) * 32767).astype(np.int16).tobytes())
        json.dump({"ganho_master": ganho}, open(cc_dir / "audio.json", "w"))
        print(f"camadas CapCut: voz.wav + musica.wav (ganho do master {20 * np.log10(ganho):+.1f} dB)")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video_tmp), "-i", str(wav_tmp), "-c:v", "copy",
                    "-af", "loudnorm=I=-14:TP=-1.0:LRA=9", "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
                    "-shortest", "-movflags", "+faststart", str(saida)], check=True)
    video_tmp.unlink(missing_ok=True)
    wav_tmp.unlink(missing_ok=True)
    print("OK", saida)


if __name__ == "__main__":
    main()
