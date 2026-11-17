"""
Renderiza TODOS os cortes do projeto (em paralelo) e grava os dois drafts de cada um no CapCut.

Uso: python renderizar.py --projeto P --versao v1 [--so corte1_x,corte2_y] [--paralelo 4]
     [--sem_drafts]   renderiza tudo (MP4 + camadas do draft FIEL) sem tocar no CapCut (pode estar aberto)
     [--so_drafts]    só grava os drafts a partir do que já foi renderizado (CapCut fechado)
     [--sem_capcut]   só MP4, sem camadas nem drafts (mais rápido)
  * MP4 final em 05_render/<nome>.mp4 (versões anteriores vão para 05_render/<versao_anterior>/ se existirem)
  * draft FIEL  "<data>_<nome_do_corte>_<versao>"        (igual ao MP4)
  * draft NATIVO "<data>_<nome_do_corte>_<versao>_nativo" (editável)
  (nome do corte curto, até ~35 caracteres: o Windows limita caminhos a 260)
  * QA: trava de borda R-024 (no render), loudness de cada MP4 e folha de quadros 05_render/folha_<versao>.jpg
O CapCut precisa estar FECHADO para gravar os drafts (o script confere e para se estiver aberto).
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # acha _base.py mesmo com python -I
import _base
from _base import SCRIPTS, carregar_projeto


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--projeto", required=True)
    ap.add_argument("--versao", required=True)
    ap.add_argument("--so", default=None)
    ap.add_argument("--sem_capcut", action="store_true")
    ap.add_argument("--sem_drafts", action="store_true")
    ap.add_argument("--so_drafts", action="store_true")
    ap.add_argument("--paralelo", type=int, default=4)
    a = ap.parse_args()
    P = carregar_projeto(a.projeto)
    proj = P["_dir"]
    cortes = sorted((proj / "cortes").glob("*.json"))
    if a.so:
        quero = set(a.so.split(","))
        cortes = [c for c in cortes if json.load(open(c, encoding="utf-8"))["nome"] in quero or c.stem in quero]
    if not cortes:
        sys.exit("nenhum cortes/*.json — rode preparar_cortes.py antes")
    grava = not (a.sem_capcut or a.sem_drafts)
    if grava and _base.capcut_aberto():
        sys.exit("Feche o CapCut antes (os drafts são gravados no fim do render) — ou use --sem_drafts agora e "
                 "--so_drafts depois.")
    logs = proj / "05_render" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    nomes = [json.load(open(c, encoding="utf-8"))["nome"] for c in cortes]
    # render em paralelo (lotes de --paralelo)
    for i in (range(0, len(cortes), a.paralelo) if not a.so_drafts else []):
        procs = []
        for c, n in zip(cortes[i:i + a.paralelo], nomes[i:i + a.paralelo]):
            lg = open(logs / f"render_{n}.txt", "w", encoding="utf-8")
            cmd = [sys.executable, str(SCRIPTS / "corte_live.py"), "--projeto", str(proj), str(c)]
            if a.sem_capcut:
                cmd.append("--sem_capcut")
            procs.append((n, subprocess.Popen(cmd, stdout=lg, stderr=subprocess.STDOUT), lg))
            print("render:", n, flush=True)
        for n, p, lg in procs:
            p.wait()
            lg.close()
            txt = open(logs / f"render_{n}.txt", encoding="utf-8", errors="replace").read()
            ok = "QA borda (R-024): ok" in txt and "\nOK " in txt
            print(f"  {n}: {'ok' if ok else 'FALHOU — veja ' + str(logs / ('render_' + n + '.txt'))}")
            if not ok:
                sys.exit(1)
    # drafts
    data = datetime.now().strftime("%Y-%m-%d")
    if grava:
        for c, n in zip(cortes, nomes):
            base = f"{data}_{n}_{a.versao}"      # curto: caminho do CapCut tem limite de 260 caracteres
            for cmd in ([sys.executable, str(SCRIPTS / "capcut_fiel.py"), "--projeto", str(proj), "--corte", n, "--nome", base],
                        [sys.executable, str(SCRIPTS / "capcut_nativo.py"), "--projeto", str(proj), str(c), "--nome",
                         base + "_nativo"]):
                r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
                linhas = [ln for ln in r.stdout.splitlines() if ln.startswith("OK")]
                print("  " + (linhas[-1] if linhas else "ERRO: " + (r.stderr.strip().splitlines() or ["?"])[-1]))
    # QA final: loudness + folha de quadros
    tiles = []
    for n in nomes:
        mp4 = proj / "05_render" / f"{n}.mp4"
        rel = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(mp4), "-af", "ebur128=peak=true", "-f", "null",
                              "-"], capture_output=True, text=True, errors="replace").stderr
        m = re.findall(r"I:\s+(-?[\d.]+) LUFS", rel)
        print(f"  {n}: {m[-1] if m else '?'} LUFS (alvo -14)")
        png = proj / "05_render" / f"_folha_{n}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp4), "-vf", "fps=1/3,scale=180:-1,tile=12x1",
                        "-frames:v", "1", str(png)])
        tiles.append(png)
    if tiles:
        folha = proj / "05_render" / f"folha_{a.versao}.jpg"
        args = ["ffmpeg", "-v", "error", "-y"]
        for t in tiles:
            args += ["-i", str(t)]
        args += ["-filter_complex", f"vstack={len(tiles)}" if len(tiles) > 1 else "null", str(folha)]
        subprocess.run(args)
        for t in tiles:
            t.unlink(missing_ok=True)
        print("folha de QA:", folha)


if __name__ == "__main__":
    main()
