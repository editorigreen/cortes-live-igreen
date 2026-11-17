"""
Gera o mapa de cortes de respiro (jump cuts) a partir da transcrição por palavra + energia do áudio.

Uso:
  python ferramentas/cortar_respiros.py <transcricao.json> <video_ou_audio> <saida_cortes.json>
         [--gap 0.30] [--pre 0.07] [--pos 0.10] [--remover "né,ahn,é..."] [--fim <seg>]

Regras de editor sênior (padrão do cérebro, ver cerebro/regras.md):
  * Silêncio entre palavras > gap  -> corta. Mantém 'pre' s antes da próxima palavra e 'pos' s depois da última.
  * O ponto exato do corte é puxado para o mínimo de energia (RMS) da janela, evitando cortar sílaba.
  * Vícios ("né", "ahn", "tipo", "é...") isolados entre pausas são removidos.
  * Tudo depois de --fim (ex.: conversa fora do take) é descartado.
Saída: lista de segmentos [ini, fim] no tempo da fonte + palavras remapeadas para a timeline final.
"""
import argparse
import json
import subprocess

import numpy as np

FILLERS_PADRAO = {"né", "né?", "ahn", "hã", "éé", "tipo", "assim,"}


def rms_env(src, sr=16000, hop=0.01):
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    y = np.frombuffer(pcm, dtype=np.float32)
    h = int(sr * hop)
    n = len(y) // h
    env = np.sqrt((y[: n * h].reshape(n, h) ** 2).mean(axis=1) + 1e-12)
    return env, hop


def quietest(env, hop, a, b):
    ia, ib = int(a / hop), max(int(a / hop) + 1, int(b / hop))
    ia, ib = max(0, ia), min(len(env), ib)
    if ib <= ia:
        return a
    return (ia + int(np.argmin(env[ia:ib]))) * hop


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcricao")
    ap.add_argument("midia")
    ap.add_argument("saida")
    ap.add_argument("--gap", type=float, default=0.30)
    ap.add_argument("--pre", type=float, default=0.07)
    ap.add_argument("--pos", type=float, default=0.10)
    ap.add_argument("--remover", default="")
    ap.add_argument("--fim", type=float, default=None)
    ap.add_argument("--inicio", type=float, default=0.0)
    ap.add_argument("--trechos", default="", help="faixas da fonte a manter, ex: 0.8-7.9,20.9-26.9")
    a = ap.parse_args()

    tr = json.load(open(a.transcricao, encoding="utf-8"))
    words = [w for s in tr["segmentos"] for w in s["palavras"]]
    words = [w for w in words if w["i"] >= a.inicio and (a.fim is None or w["f"] <= a.fim)]
    if a.trechos:  # corte editorial: só palavras dentro dos trechos escolhidos ("8.1-11.2,20.9-26.8")
        rng = [tuple(float(x) for x in r.split("-")) for r in a.trechos.split(",")]
        words = [w for w in words if any(r0 - 0.02 <= w["i"] and w["f"] <= r1 + 0.02 for r0, r1 in rng)]
    fillers = FILLERS_PADRAO | {x.strip().lower() for x in a.remover.split(",") if x.strip()}

    # remove vícios isolados (pausa antes e depois)
    kept = []
    for i, w in enumerate(words):
        t = w["p"].lower().strip()
        prev_gap = w["i"] - words[i - 1]["f"] if i else 1
        next_gap = words[i + 1]["i"] - w["f"] if i + 1 < len(words) else 1
        if t in fillers and prev_gap > 0.15 and next_gap > 0.15:
            continue
        kept.append(w)

    env, hop = rms_env(a.midia)
    segs = []
    cur_start = max(0.0, kept[0]["i"] - a.pre)
    for w0, w1 in zip(kept[:-1], kept[1:]):
        gap = w1["i"] - w0["f"]
        if gap > a.gap:
            cut_out = quietest(env, hop, w0["f"], min(w0["f"] + a.pos + 0.08, w1["i"]))
            cut_out = max(cut_out, w0["f"] + 0.04)
            cut_in = quietest(env, hop, max(w0["f"], w1["i"] - a.pre - 0.08), w1["i"])
            cut_in = min(cut_in, w1["i"] - 0.02)
            segs.append([round(cur_start, 3), round(cut_out, 3)])
            cur_start = cut_in
    segs.append([round(cur_start, 3), round(kept[-1]["f"] + a.pos + 0.15, 3)])

    # remapeia palavras para a timeline de saída
    out_words, offset_map, t_out = [], [], 0.0
    for s0, s1 in segs:
        offset_map.append((s0, s1, t_out))
        t_out += s1 - s0
    for w in kept:
        for s0, s1, base in offset_map:
            if s0 - 0.05 <= w["i"] <= s1:
                out_words.append({"p": w["p"], "i": round(base + max(0, w["i"] - s0), 3),
                                  "f": round(base + min(w["f"], s1) - s0, 3), "src_i": w["i"]})
                break

    total_src = (a.fim or tr["duracao"]) - a.inicio
    res = {"segmentos": segs, "duracao_final": round(t_out, 3), "duracao_fonte": round(total_src, 3),
           "removido_s": round(total_src - t_out, 3), "n_cortes": len(segs) - 1, "palavras": out_words,
           "params": vars(a)}
    json.dump(res, open(a.saida, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(segs)} segmentos | {total_src:.1f}s -> {t_out:.1f}s (-{total_src - t_out:.1f}s) | {len(segs) - 1} jump cuts")


if __name__ == "__main__":
    main()
