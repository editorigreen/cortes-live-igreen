"""Base comum dos scripts da skill cortes-live-igreen: caminhos, projeto.json e defaults do padrão iGreen."""
import copy
import json
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SKILL = SCRIPTS.parent
LIB = SCRIPTS / "lib"
VENDOR = LIB / "capcut_vendor"
for p in (str(VENDOR), str(LIB), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:  # console do Windows em cp1252 quebra acentos
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

DRAFTS = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CapCut/User Data/Projects/com.lveditor.draft"

# Padrão aprovado pelo cliente (cortes da live 14/11/2026, v3). Um projeto só sobrescreve o que mudar.
PADRAO = {
    "background": "@skill/assets/background_corte_live.png",
    "logo": "@skill/assets/logos/igreen_verde_claro.png",
    "eyebrow": "LIVE OFICIAL iGreen  ·  14/11",
    "end_sub": "LIVE OFICIAL  ·  14/11",
    "credito": {"nome": "THIAGO ALEXANDER", "cargo": "Presidente da iGreen"},
    # recorte da transmissão (StreamYard 1280x720 da live iGreen): área útil 16:9 sem plaquinha de nome e sem logo
    "layout_live": {"area_dividida": [68, 193, 516, 290], "area_cheia": [0, 0, 1120, 630],
                    "faixa_teste": [0, 170, 0, 1000], "limiar_dividida": 25},
    "musica": {"arquivo": "@skill/assets/musica/action_sport_motivational_rock.mp3", "inicio": 0,
               "volume_db": -22, "ducking_db": -12, "fade_out": 1.6,
               "_nome": "Action Sport Motivational Rock (biblioteca CapCut)"},
    "legenda_corrigir": {"intera": "inteira", "interar": "inteirar"},
    "nomes_proprios": {},
    "end_card": 1.8, "zoom_alt": 1.08, "max_palavras": 3,
    "whisper_modelo": "large-v3-turbo",
}


def resolver(caminho, proj=None):
    """'@skill/...' -> dentro da skill; relativo -> dentro do projeto; absoluto -> como está."""
    if caminho is None:
        return None
    c = str(caminho)
    if c.startswith("@skill/"):
        return SKILL / c[len("@skill/"):]
    p = Path(c)
    if not p.is_absolute() and proj is not None:
        return Path(proj) / p
    return p


def _mesclar(base, novo):
    out = copy.deepcopy(base)
    for k, v in (novo or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _mesclar(out[k], v)
        else:
            out[k] = v
    return out


def carregar_projeto(proj):
    proj = Path(proj).resolve()
    pj = proj / "projeto.json"
    if not pj.exists():
        sys.exit(f"projeto.json não encontrado em {proj} — crie com scripts/novo_projeto.py")
    P = _mesclar(PADRAO, json.load(open(pj, encoding="utf-8")))
    P["_dir"] = proj
    if not P.get("live"):
        sys.exit("projeto.json sem 'live' (caminho do vídeo completo da live)")
    P["_live"] = resolver(P["live"], proj)
    if not P["_live"].exists():
        sys.exit(f"vídeo da live não encontrado: {P['_live']}")
    return P


def capcut_aberto():
    """True se o CapCut estiver rodando (nunca gravar draft com ele aberto)."""
    import subprocess
    if os.environ.get("CORTES_LIVE_TESTE_SEM_CAPCUT") == "1":   # só para teste com pasta de drafts falsa
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq CapCut.exe"], capture_output=True, text=True).stdout
        return "CapCut.exe" in out
    except Exception:
        return False
