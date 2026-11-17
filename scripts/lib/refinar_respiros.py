"""
2º passe de corte de respiro pela ENERGIA do áudio (padrão REF11): o Whisper às vezes estica uma palavra por cima
de uma pausa; aqui toda pausa interna >= --min s (abaixo de p95 - --db dB) é removida, deixando --ar s de respiro
(metade de cada lado). Pausas na borda do segmento são aparadas. Remapeia as palavras para a timeline final.

Uso: python ferramentas/refinar_respiros.py <cortes.json> <midia> <saida.json> [--min 0.28] [--ar 0.14] [--db 28] [--fim_ultimo X]
"""
import argparse, json, subprocess
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("cortes"); ap.add_argument("midia"); ap.add_argument("saida")
ap.add_argument("--min", type=float, default=0.28); ap.add_argument("--ar", type=float, default=0.14)
ap.add_argument("--db", type=float, default=28); ap.add_argument("--fim_ultimo", type=float, default=None)
ap.add_argument("--min_dentro", type=float, default=0.40,
                help="pausa DENTRO de uma palavra (pela transcrição) só sai se for >= isto (R-022: s/f/ch fracos não são silêncio)")
a = ap.parse_args()
sr = 16000
y = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", a.midia, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                                 capture_output=True, check=True).stdout, np.float32)
h = sr // 100; n = len(y) // h
db = 20 * np.log10(np.sqrt((y[:n * h].reshape(n, h) ** 2).mean(1)) + 1e-9)
lim = np.percentile(db, 95) - a.db
C = json.load(open(a.cortes, encoding="utf-8"))
segs = [list(s) for s in C["segmentos"]]
if a.fim_ultimo:
    segs[-1][1] = a.fim_ultimo
# palavras na fonte (para não cortar fonema fraco — "transformada" perdeu 0,18 s no v2, feedback do cliente)
pal_src = [(w["src_i"], w["src_i"] + (w["f"] - w["i"])) for w in C["palavras"]]


def dentro_de_palavra(q0, q1):
    """True se a pausa [q0,q1] cai no interior de uma palavra (não toca uma fronteira entre palavras)."""
    return any(wi + 0.03 < q0 and q1 < wf - 0.03 or (wi + 0.03 < q1 and q0 < wf - 0.03 and (q1 - q0) < (wf - wi) * 0.9
               and wi < q0 and q1 < wf) for wi, wf in pal_src)


protegidas = []
novos = []
for s0, s1 in segs:
    low = db[int(s0 * 100):int(s1 * 100)] < lim
    cur = s0; st = None
    for i, v in enumerate(np.append(low, False)):
        if v and st is None: st = i
        if not v and st is not None:
            q0, q1 = s0 + st / 100, s0 + i / 100
            if q1 - q0 >= a.min and dentro_de_palavra(q0, q1) and q1 - q0 < a.min_dentro:
                protegidas.append((round(q0, 2), round(q1, 2)))
            elif q1 - q0 >= a.min:
                if st == 0:                          # pausa na borda inicial
                    cur = q1 - a.ar / 2
                elif i >= len(low):                  # pausa na borda final
                    s1 = q0 + a.ar / 2
                else:
                    novos.append([round(cur, 3), round(q0 + a.ar / 2, 3)]); cur = q1 - a.ar / 2
            st = None
    novos.append([round(cur, 3), round(s1, 3)])
# remapeia palavras (pela posição na fonte)
fonte_words = []
for w in C["palavras"]:
    dur = w["f"] - w["i"]
    fonte_words.append((w, w["src_i"], w["src_i"] + dur))
mapa, t = [], 0.0
for s0, s1 in novos:
    mapa.append((s0, s1, t)); t += s1 - s0
out = []
for w, si, sf in fonte_words:
    for s0, s1, base in mapa:      # 1º segmento que termina depois do início da palavra (se caiu no micro-corte, encaixa no início dele)
        if si <= s1 and sf > s0 - 0.3:
            i0 = base + max(0.0, si - s0)
            out.append({"p": w["p"], "i": round(i0, 3), "f": round(max(i0 + 0.08, base + min(sf, s1) - s0), 3), "src_i": si})
            break
C.update({"segmentos": novos, "palavras": out, "duracao_final": round(t, 3), "n_cortes": len(novos) - 1,
          "refino": vars(a)})
json.dump(C, open(a.saida, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{len(segs)} -> {len(novos)} segmentos | duração final {t:.2f}s | {len(out)} palavras | "
      f"{len(protegidas)} pausas curtas DENTRO de palavra preservadas (R-022): {protegidas}")
