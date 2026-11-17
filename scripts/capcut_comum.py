"""Gravação de draft no CapCut Desktop 9.x + registro na lista de projetos (com backup do root_meta_info.json)."""
import json
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # acha _base.py mesmo com python -I
import _base
from _base import DRAFTS, VENDOR

import pyJianYingDraft as draft  # noqa: F401
from draft_profiles import get_draft_profile, write_profile_content

SEC = 1_000_000
FONTES = _base.SKILL / "assets" / "fontes"
FONTE_ESTATICA = {  # CapCut não escolhe peso de fonte variável -> instâncias estáticas
    ("Montserrat[wght].ttf", 600): "Montserrat-SemiBold.ttf",
    ("Montserrat[wght].ttf", 700): "Montserrat-Bold.ttf",
    ("Montserrat[wght].ttf", 800): "Montserrat-ExtraBold.ttf",
    ("Montserrat[wght].ttf", 900): "Montserrat-Black.ttf",
}


def us(x):
    return int(round(x * SEC))


def hex_rgb01(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def fonte_path(est):
    nome = est.get("fonte", "Montserrat[wght].ttf")
    nome = FONTE_ESTATICA.get((nome, est.get("peso", 800)), nome)
    return str((FONTES / nome).resolve()).replace("\\", "/")


def _longo(p):
    """Caminho estendido do Windows (prefixo de caminho longo) — evita o limite de 260 caracteres."""
    import os
    p = str(Path(p).resolve())
    prefixo = "\\\\?\\"
    return prefixo + p if os.name == "nt" and not p.startswith(prefixo) else p


def exigir_capcut_fechado():
    if _base.capcut_aberto():
        sys.exit("O CapCut está aberto. Feche o CapCut (todas as janelas) antes de gravar drafts — ele sobrescreve "
                 "a lista de projetos ao fechar e o draft some.")


def salvar_draft(script, nome, total, proj, capa_mp4=None, fontes_por_texto=None):
    """Grava o draft em com.lveditor.draft/<nome>, registra na lista do CapCut e copia o JSON para 06_capcut/."""
    exigir_capcut_fechado()
    proj = Path(proj)
    bkdir = proj / "06_capcut" / "backups"
    bkdir.mkdir(parents=True, exist_ok=True)
    profile = get_draft_profile("capcut_9")
    content = json.loads(script.dumps(profile))
    if fontes_por_texto is not None:
        for m in content["materials"].get("texts", []):
            try:
                c = json.loads(m["content"])
                fp = fontes_por_texto.get(c.get("text", ""), fonte_path({}))
                for st in c.get("styles", []):
                    st["font"] = {"id": "", "path": fp}
                m["content"] = json.dumps(c, ensure_ascii=False)
                m["font_path"] = fp
            except Exception:
                pass
    content["name"] = ""
    DRAFTS.mkdir(parents=True, exist_ok=True)
    # limite de 260 caracteres do Windows: raiz + nome + arquivo mais fundo do template (~95) + folga p/ o CapCut
    cabe = 250 - 100 - len(str(DRAFTS)) - 1
    if len(nome) > cabe:
        print(f"aviso: nome do draft encurtado para caber no limite de caminho do Windows ({len(nome)} -> {cabe})")
        nome = nome[:cabe].rstrip("_-")
    dest = DRAFTS / nome
    if dest.exists():
        shutil.move(_longo(dest), _longo(bkdir / f"{nome}__bak_{time.strftime('%Y%m%d_%H%M%S')}"))
    # template do CapCut 9 vai zipado na skill (tem subpastas fundas que estouram o limite de 260 caracteres do
    # Windows ao descompactar/copiar a skill); é extraído direto no destino com caminho longo
    import zipfile
    with zipfile.ZipFile(VENDOR / "template_capcut9.zip") as zt:
        zt.extractall(_longo(dest))
    write_profile_content(profile, dest, json.dumps(content, ensure_ascii=False))
    now_us = int(time.time() * 1e6)
    meta_path = dest / "draft_meta_info.json"
    meta = json.load(open(meta_path, encoding="utf-8")) if meta_path.exists() else {}
    draft_uuid = str(uuid.uuid4()).upper()
    meta.update({"draft_name": nome, "draft_id": draft_uuid, "draft_fold_path": str(dest).replace("\\", "/"),
                 "draft_root_path": str(DRAFTS), "tm_duration": us(total), "tm_draft_create": now_us,
                 "tm_draft_modified": now_us, "draft_cover": "draft_cover.jpg"})
    json.dump(meta, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False)
    if capa_mp4 and Path(capa_mp4).exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "2.5", "-i", str(capa_mp4), "-frames:v", "1",
                        "-vf", "scale=540:-1", str(dest / "draft_cover.jpg")])
    rm_path = DRAFTS / "root_meta_info.json"
    if rm_path.exists():
        shutil.copy(rm_path, bkdir / f"root_meta_info_{time.strftime('%Y%m%d_%H%M%S')}.json")
        rm = json.load(open(rm_path, encoding="utf-8"))
    else:
        rm = {"all_draft_store": [], "draft_ids": 0, "root_path": str(DRAFTS)}
    store = [x for x in rm.get("all_draft_store", []) if x.get("draft_name") != nome]
    entry = dict(store[0]) if store else {}
    entry.update({"draft_name": nome, "draft_id": draft_uuid, "draft_fold_path": str(dest).replace("\\", "/"),
                  "draft_json_file": str(dest / "draft_content.json"), "draft_cover": str(dest / "draft_cover.jpg"),
                  "draft_root_path": str(DRAFTS), "tm_duration": us(total), "tm_draft_create": now_us,
                  "tm_draft_modified": now_us, "tm_draft_removed": 0, "draft_is_invisible": False,
                  "cloud_draft_sync": False, "draft_cloud_last_action_download": False})
    store.insert(0, entry)
    rm["all_draft_store"] = store
    json.dump(rm, open(rm_path, "w", encoding="utf-8"), ensure_ascii=False)
    shutil.copy(dest / "draft_content.json", proj / "06_capcut" / f"{nome}_draft_content.json")
    return dest
