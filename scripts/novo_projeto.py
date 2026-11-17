"""
Cria a pasta de um projeto de cortes de live (uma pasta por dia-hora) com projeto.json pronto para preencher.

Uso: python novo_projeto.py --nome cortes-live-natal --live "C:/.../LIVE.mp4" [--destino PASTA] [--data 14/11]
Saída: <destino>/AAAA-MM-DD_HHhMM_<nome>/ com 03_analise/ 05_render/ 06_capcut/ cortes/ e projeto.json
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # acha _base.py mesmo com python -I
import _base  # noqa: F401


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nome", required=True)
    ap.add_argument("--live", required=True, help="vídeo completo da live (16:9)")
    ap.add_argument("--destino", default=".", help="pasta onde criar o projeto (ex.: PROJETOS/)")
    ap.add_argument("--data", default=None, help="data da live para o eyebrow/end card, ex.: 14/11")
    a = ap.parse_args()
    slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in a.nome.lower()).strip("-")
    proj = Path(a.destino).resolve() / f"{datetime.now():%Y-%m-%d_%Hh%M}_{slug}"
    for d in ("03_analise", "05_render", "06_capcut", "cortes"):
        (proj / d).mkdir(parents=True, exist_ok=True)
    data = a.data or "DD/MM"
    pj = {
        "nome": slug,
        "live": str(Path(a.live).resolve()).replace("\\", "/"),
        "eyebrow": f"LIVE OFICIAL iGreen  ·  {data}",
        "end_sub": f"LIVE OFICIAL  ·  {data}",
        "credito": {"nome": "THIAGO ALEXANDER", "cargo": "Presidente da iGreen"},
        "_comentario": "Campos omitidos usam o padrão iGreen da skill (background, logo, layout_live, música, "
                       "estilos). Preencha 'cortes' e rode scripts/preparar_cortes.py.",
        "cortes": [
            {"nome": "corte1_tema-curto", "titulo": [["LINHA 1", "branco"], ["LINHA 2", "branco"], ["LINHA 3.", "verde"]],
             "trechos": [[0.0, 30.0]], "destaques": [], "punch_palavras": []}
        ],
    }
    json.dump(pj, open(proj / "projeto.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(proj)


if __name__ == "__main__":
    main()
