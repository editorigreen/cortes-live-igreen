"""
Biblioteca de SFX procedurais (sem direitos autorais) + EQ de voz.

Tipos: whoosh, whoosh_curto, pop, click, hit, boom, riser, swoosh_texto, flash, typing, ding
Uso no plano: {"t": 3.2, "tipo": "whoosh", "vol": -14, "dur": 0.4}
            ou {"t": 3.2, "arquivo": "04_assets/sfx/meu.wav", "vol": -10}
Também gera a biblioteca em WAV: python ferramentas/sfx.py <pasta_saida>
"""
import subprocess
import sys
from pathlib import Path

import numpy as np

RNG = np.random.default_rng(7)


def _env(n, a=0.01, r=0.3, sr=48000, curva=3.0):
    t = np.arange(n) / sr
    att = np.clip(t / max(a, 1e-4), 0, 1)
    rel = np.exp(-np.clip(t - a, 0, None) / max(r, 1e-4) * curva)
    return att * rel


def _bandpass_sweep(noise, sr, f0, f1, q=2.0):
    """Varredura de passa-banda simples via filtro de estado variável."""
    n = len(noise)
    f = np.geomspace(f0, f1, n)
    low = band = 0.0
    out = np.empty(n, np.float32)
    damp = 1.0 / q
    for i in range(n):
        g = 2 * np.sin(np.pi * min(f[i], sr / 6) / sr)
        high = noise[i] - low - damp * band
        band += g * high
        low += g * band
        out[i] = band
    return out


def _stereo(x, largura=0.3):
    d = int(48 * largura * 10)
    l = x
    r = np.concatenate([np.zeros(d, np.float32), x[:-d]]) if d else x
    return np.stack([l, r], axis=1).astype(np.float32)


def gerar(tipo, sr=48000, dur=None):
    if tipo in ("whoosh", "whoosh_curto", "swoosh_texto"):
        d = dur or {"whoosh": 0.55, "whoosh_curto": 0.3, "swoosh_texto": 0.22}[tipo]
        n = int(sr * d)
        noise = RNG.normal(0, 1, n).astype(np.float32)
        f0, f1 = (300, 5000) if tipo != "swoosh_texto" else (1500, 9000)
        s = _bandpass_sweep(noise, sr, f0, f1, q=1.4)
        t = np.linspace(0, 1, n)
        env = np.sin(np.pi * t ** 0.7) ** 2
        x = s * env
        return _stereo(x / (np.abs(x).max() + 1e-9) * 0.9, 0.6)
    if tipo == "pop":
        n = int(sr * 0.09)
        t = np.arange(n) / sr
        f = 900 * np.exp(-t * 35) + 280
        x = np.sin(2 * np.pi * np.cumsum(f) / sr) * _env(n, 0.002, 0.03, sr)
        return _stereo(x.astype(np.float32) * 0.9, 0)
    if tipo == "click":
        n = int(sr * 0.03)
        x = RNG.normal(0, 1, n) * _env(n, 0.0005, 0.006, sr)
        x = np.convolve(x, np.ones(3) / 3, mode="same")
        return _stereo(x.astype(np.float32) * 0.8, 0)
    if tipo in ("hit", "boom"):
        d = 0.9 if tipo == "boom" else 0.45
        n = int(sr * d)
        t = np.arange(n) / sr
        f = (110 if tipo == "boom" else 160) * np.exp(-t * 6) + 42
        sub = np.sin(2 * np.pi * np.cumsum(f) / sr) * _env(n, 0.003, d * 0.5, sr, 2.2)
        nz = RNG.normal(0, 1, n) * _env(n, 0.001, 0.04, sr) * 0.35
        x = np.tanh((sub + nz) * 1.6)
        return _stereo(x.astype(np.float32) * 0.95, 0.2)
    if tipo == "riser":
        d = dur or 1.2
        n = int(sr * d)
        noise = RNG.normal(0, 1, n).astype(np.float32)
        s = _bandpass_sweep(noise, sr, 200, 7000, q=3.0)
        t = np.linspace(0, 1, n)
        tone = np.sin(2 * np.pi * np.cumsum(np.geomspace(180, 900, n)) / sr) * 0.25
        x = (s + tone) * t ** 2.2
        x[-int(sr * 0.02):] *= np.linspace(1, 0, int(sr * 0.02))
        return _stereo(x / (np.abs(x).max() + 1e-9) * 0.9, 0.5)
    if tipo == "flash":
        n = int(sr * 0.35)
        noise = RNG.normal(0, 1, n).astype(np.float32)
        s = _bandpass_sweep(noise, sr, 6000, 2500, q=1.0)
        x = s * _env(n, 0.005, 0.12, sr)
        return _stereo(x / (np.abs(x).max() + 1e-9) * 0.7, 0.8)
    if tipo == "ding":
        n = int(sr * 0.8)
        t = np.arange(n) / sr
        x = (np.sin(2 * np.pi * 1318 * t) + 0.5 * np.sin(2 * np.pi * 2637 * t)) * _env(n, 0.002, 0.35, sr)
        return _stereo((x * 0.5).astype(np.float32), 0.3)
    if tipo == "typing":
        d = dur or 0.6
        n = int(sr * d)
        x = np.zeros(n, np.float32)
        pos = 0
        while pos < n - 1500:
            c = gerar("click", sr)[:, 0] * RNG.uniform(0.4, 1.0)
            x[pos:pos + len(c)] += c[: n - pos]
            pos += int(sr * RNG.uniform(0.05, 0.11))
        return _stereo(x, 0.1)
    raise ValueError(f"SFX desconhecido: {tipo}")


def obter(ev, sr, raiz, proj):
    if ev.get("arquivo"):
        p = Path(ev["arquivo"])
        if not p.is_absolute():
            p = (proj / p) if (proj / p).exists() else (raiz / p)
        pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"],
                             capture_output=True, check=True).stdout
        return np.frombuffer(pcm, np.float32).reshape(-1, 2).copy()
    return gerar(ev["tipo"], sr, ev.get("dur"))


def eq_voz(x, sr):
    """EQ de voz de broadcast: corta < 80 Hz, presença +2.5 dB @ 3.5 kHz, compressão leve."""
    from scipy.signal import butter, sosfilt
    hp = butter(2, 80, "highpass", fs=sr, output="sos")
    y = sosfilt(hp, x, axis=0)
    bp = butter(2, [2500, 5000], "bandpass", fs=sr, output="sos")
    y = y + sosfilt(bp, y, axis=0) * 0.33
    # compressor RMS simples (ratio ~3:1 acima de -20 dBFS)
    _k = int(sr * 0.02)
    _x = (y ** 2).mean(axis=1).astype(np.float64)
    _c = np.concatenate([[0.0], np.cumsum(_x)])
    _a = np.arange(len(_x)) - (_k - 1) // 2
    _m = (_c[np.clip(_a + _k, 0, len(_x))] - _c[np.clip(_a, 0, len(_x))]) / _k  # média móvel O(n)
    env = np.sqrt(np.maximum(_m, 0)).astype(np.float32) + 1e-6
    thr = 10 ** (-20 / 20)
    gain = np.where(env > thr, (thr / env) ** (1 - 1 / 3), 1.0)
    y = y * gain[:, None] * 1.6
    return y.astype(np.float32)


if __name__ == "__main__":
    import wave
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "sfx_biblioteca")
    out.mkdir(parents=True, exist_ok=True)
    for tp in ["whoosh", "whoosh_curto", "swoosh_texto", "pop", "click", "hit", "boom", "riser", "flash", "ding", "typing"]:
        x = gerar(tp)
        with wave.open(str(out / f"{tp}.wav"), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(48000)
            wf.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
        print("ok", tp)
