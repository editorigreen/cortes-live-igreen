"""
Confere se esta máquina reproduz os cortes de forma IDÊNTICA à máquina de referência.

Uso: python checar_ambiente.py
Verifica: Python 3.12, versões dos pacotes (requirements.txt), ffmpeg/ffprobe, assets da skill, pasta de drafts do
CapCut e importação do motor. Versões diferentes funcionam, mas podem mudar pixels/tempos — avisa como DIFERENTE.
"""
import importlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # acha _base.py mesmo com python -I
import _base
from _base import SKILL, DRAFTS

OK, AV, ER = "ok", "DIFERENTE", "FALTA"
problemas = 0


def linha(estado, item, detalhe=""):
    global problemas
    if estado == ER:
        problemas += 1
    print(f"[{estado:9}] {item:28} {detalhe}")


def main():
    v = sys.version_info
    linha(OK if (v.major, v.minor) == (3, 12) else AV, "python", sys.version.split()[0] + " (referência 3.12)")
    mods = {"numpy": "numpy", "opencv-python": "cv2", "pillow": "PIL", "scipy": "scipy", "faster-whisper": "faster_whisper",
            "imageio": "imageio"}
    req = {}
    for ln in open(SKILL / "requirements.txt", encoding="utf-8"):
        m = re.match(r"^([A-Za-z0-9_\-]+)==([\w.]+)", ln.strip())
        if m:
            req[m.group(1).lower()] = m.group(2)
    for pkg, mod in mods.items():
        try:
            x = importlib.import_module(mod)
            ver = getattr(x, "__version__", "?")
            alvo = req.get(pkg)
            igual = ver == alvo or (alvo or "").startswith(ver + ".")   # opencv: 5.0.0 x 5.0.0.93
            linha(OK if igual else AV, pkg, f"{ver} (referência {alvo})")
        except Exception as e:
            linha(ER, pkg, f"não instalado — pip install -r requirements.txt ({type(e).__name__})")
    for exe in ("ffmpeg", "ffprobe"):
        p = shutil.which(exe)
        if not p:
            linha(ER, exe, "não encontrado no PATH — instale o FFmpeg (gyan.dev full) e reabra o terminal")
            continue
        ver = subprocess.run([exe, "-version"], capture_output=True, text=True).stdout.split("\n")[0]
        linha(OK if " 9." in ver or "version 9" in ver else AV, exe, ver[:70] + " (referência 9.0.2 gyan full)")
    for rel in ("assets/background_corte_live.png", "assets/logos/igreen_verde_claro.png", "assets/fontes/Anton-Regular.ttf",
                "assets/fontes/Montserrat[wght].ttf", "assets/musica/action_sport_motivational_rock.mp3",
                "scripts/lib/capcut_vendor/template_capcut9.zip"):
        dica = ("só no pacote interno do time (ou defina projeto.json['musica'])" if rel.endswith(".mp3")
                else str(SKILL / rel))
        linha(OK if (SKILL / rel).exists() else ER, rel.split("/")[-1][:28], "" if (SKILL / rel).exists() else dica)
    linha(OK if DRAFTS.exists() else AV, "pasta de drafts CapCut",
          str(DRAFTS) + ("" if DRAFTS.exists() else " — abra o CapCut uma vez para criá-la"))
    try:
        import corte_live  # noqa: F401
        import capcut_comum  # noqa: F401
        linha(OK, "motor + ponte CapCut", "importam sem erro")
    except Exception as e:
        linha(ER, "motor + ponte CapCut", repr(e))
    try:
        from huggingface_hub import scan_cache_dir
        tem = any("whisper-large-v3-turbo" in r.repo_id for r in scan_cache_dir().repos)
        linha(OK if tem else AV, "modelo Whisper", "em cache" if tem else "será baixado na 1ª transcrição (~1,6 GB)")
    except Exception:
        linha(AV, "modelo Whisper", "não deu para verificar o cache")
    print("\nRESULTADO:", "pronto" if problemas == 0 else f"{problemas} item(ns) faltando")
    sys.exit(1 if problemas else 0)


if __name__ == "__main__":
    main()
