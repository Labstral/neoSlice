# -*- coding: utf-8 -*-
"""neoGen — pilote Oen : phrase française -> paramètres validés -> pièce 3D.

Architecture de fiabilité (validée 22/22 en batterie sur Qwen3 8B) :
  1. Oen (modèle local, prompt DÉDIÉ court) extrait UN JSON de paramètres —
     il ne calcule JAMAIS de géométrie, il remplit un formulaire.
  2. Le CODE valide : bornes min/max par paramètre, texte obligatoire vérifié,
     demande ambiguë/hors catalogue -> question (jamais d'invention).
  3. Les générateurs (core.neogen.*) produisent la pièce — déterministe,
     étanche, sans surplomb (unions manifold, pentes bornées par calcul).

Sorties : ~/.neoslice/neogen/ (l'utilisateur retrouve ses pièces).
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.request
from pathlib import Path

from core.assistant.engine import HOST, MODEL_NAME

DOSSIER_SORTIES = Path.home() / ".neoslice" / "neogen"

# ── Prompt d'extraction : petit, strict, avec exemples (le 8B excelle ainsi) ─
_SYSTEME = """Tu convertis une demande en français en UN objet JSON de parametres pour un generateur de pieces 3D. Tu ne reponds RIEN d'autre que le JSON, sans texte autour, sans markdown.

CATALOGUE (champ "objet" + parametres autorises, unites en mm sauf indication) :
- porte_cle : texte* (le texte en relief), longueur (defaut 50), trou (diametre, defaut 4.5), relief (hauteur texte, defaut 1.6), socle (epaisseur, defaut 3), grave (true si texte grave/creuse)
- badge : texte*, diametre (defaut 40), trou (true si accroche demandee), grave
- sousverre : texte*, diametre (defaut 90)
- plaque : texte* (| = saut de ligne), largeur (0=auto), vis (true si trous de vis), grave
- magnet : texte*, diametre (defaut 35), aimant_d (diametre logement, defaut 10.2), aimant_p (profondeur, defaut 2)
- logo : forme (badge/plaque/silhouette, defaut badge), largeur (taille du logo, defaut 40), diametre (si badge), couleurs (2-4, defaut 3) — UNIQUEMENT si une image est jointe
- vase : hauteur (defaut 100), diametre (defaut 60), ondulations (defaut 5)
- boite : diametre (defaut 50), hauteur (defaut 30), jeu (ajustement couvercle en mm : 0.2 normal, 0.15 serre, 0.3 lache)
- support : largeur (defaut 70) — support de telephone
- de : taille (arete du de, defaut 16)

REGLES :
1. Convertis les cm en mm (6 cm -> 60).
2. N'inclus QUE les parametres que l'utilisateur precise (les defauts sont geres ailleurs).
3. texte est OBLIGATOIRE pour porte_cle/badge/sousverre/plaque/magnet : s'il manque, ou si la demande est ambigue/hors catalogue, reponds {"question": "..."} avec UNE question courte en francais.
4. "qui ferme bien/serre" -> jeu 0.15 ; "couvercle facile/lache" -> jeu 0.3.
5. N'invente JAMAIS un texte, une taille ou un parametre non demande.

EXEMPLES :
"un porte-cle avec ecrit Lea, 5 cm" -> {"objet":"porte_cle","texte":"Lea","longueur":50}
"badge Merci de 4 cm avec un trou" -> {"objet":"badge","texte":"Merci","diametre":40,"trou":true}
"une plaque Bienvenue chez Lea avec des vis" -> {"objet":"plaque","texte":"Bienvenue|chez Lea","vis":true}
"un vase de 12 cm de haut bien ondule" -> {"objet":"vase","hauteur":120,"ondulations":7}
"une boite ronde de 6 cm qui ferme bien" -> {"objet":"boite","diametre":60,"jeu":0.15}
"un de a jouer de 2 cm" -> {"objet":"de","taille":20}
"mon logo en badge de 5 cm" (image jointe) -> {"objet":"logo","forme":"badge","diametre":50}
"fais-moi un truc sympa" -> {"question":"Quel objet veux-tu ? (porte-cle, badge, plaque, magnet, sous-verre, logo, vase, boite, support telephone, de...)"}
"""

# ── Validation CODE : bornes strictes (Oen ne peut rien casser) ──────────────
_BORNES = {
    "porte_cle": {"longueur": (25, 120, 50), "trou": (2, 12, 4.5), "relief": (0.4, 4, 1.6),
                  "socle": (1.5, 8, 3.0)},
    "badge":     {"diametre": (20, 120, 40)},
    "sousverre": {"diametre": (60, 140, 90)},
    "plaque":    {"largeur": (0, 300, 0)},
    "magnet":    {"diametre": (20, 80, 35), "aimant_d": (4, 25, 10.2), "aimant_p": (1, 5, 2.0)},
    "logo":      {"largeur": (15, 150, 40), "diametre": (0, 160, 0), "couleurs": (2, 4, 3)},
    "vase":      {"hauteur": (30, 250, 100), "diametre": (30, 150, 60), "ondulations": (0, 12, 5)},
    "boite":     {"diametre": (25, 150, 50), "hauteur": (12, 120, 30), "jeu": (0.1, 0.5, 0.2)},
    "support":   {"largeur": (40, 140, 70)},
    "de":        {"taille": (8, 40, 16)},
}
_TEXTE_REQUIS = {"porte_cle", "badge", "sousverre", "plaque", "magnet"}
_ALIAS = {"sous_verre": "sousverre", "portecle": "porte_cle", "porte_cles": "porte_cle",
          "des": "de", "dice": "de", "telephone": "support", "support_telephone": "support"}


def _preparer_moteur() -> None:
    """Démarre le serveur Ollama et l'alias modèle via l'infrastructure d'Oen
    (no-op quasi instantané si déjà en marche)."""
    from core.assistant.engine import AssistantEngine
    eng = AssistantEngine.instance()
    eng._ensure_server()
    if hasattr(eng, "_ensure_model"):
        eng._ensure_model()


def demander_oen(phrase: str, image_jointe: bool = False) -> dict:
    """Appelle le modèle local (prompt dédié court, num_ctx réduit = rapide)."""
    _preparer_moteur()
    contenu = phrase + (" (image jointe)" if image_jointe else "")
    corps = json.dumps({
        "model": MODEL_NAME,
        "messages": [{"role": "system", "content": _SYSTEME},
                     {"role": "user", "content": contenu}],
        "stream": False,
        "think": False,
        "options": {"num_ctx": 2048, "temperature": 0.1},
    }).encode("utf-8")
    req = urllib.request.Request(f"http://{HOST}/api/chat", data=corps,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        rep = json.loads(r.read().decode("utf-8"))
    txt = rep.get("message", {}).get("content", "")
    m = re.search(r"\{.*\}", txt, re.DOTALL)
    if not m:
        return {"question": "Je n'ai pas compris — peux-tu reformuler ?"}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {"question": "Je n'ai pas compris — peux-tu reformuler ?"}


def valider(d: dict, image: Path | None = None) -> tuple[str | None, dict, str | None]:
    """(objet, params bornés, question éventuelle). Le CODE a le dernier mot."""
    if "question" in d:
        return None, {}, str(d["question"])
    objet = str(d.get("objet", "")).strip().lower().replace("-", "_")
    objet = _ALIAS.get(objet, objet)
    if objet not in _BORNES:
        return None, {}, ("Quel objet veux-tu ? (porte-clé, badge, plaque, magnet, "
                          "sous-verre, logo, vase, boîte, support téléphone, dé)")
    if objet in _TEXTE_REQUIS and not str(d.get("texte", "")).strip():
        return None, {}, "Quel texte faut-il mettre sur la pièce ?"
    if objet == "logo" and image is None:
        return None, {}, "Joins d'abord l'image du logo (bouton « Joindre un logo »)."
    params: dict = {}
    if objet in _TEXTE_REQUIS:
        params["texte"] = str(d["texte"]).strip()[:40]
    for cle, (mini, maxi, _defaut) in _BORNES[objet].items():
        if cle in d and d[cle] is not None:
            try:
                params[cle] = min(maxi, max(mini, float(d[cle])))
            except (TypeError, ValueError):
                pass
    for flag in ("grave", "trou", "vis"):
        if isinstance(d.get(flag), bool):
            params[flag] = d[flag]
        elif d.get(flag) in (1, "true", "oui"):
            params[flag] = True
    if objet == "logo":
        params["image"] = str(image)
        f = str(d.get("forme", "badge")).strip().lower()
        params["forme"] = f if f in ("badge", "plaque", "silhouette") else "badge"
    return objet, params, None


def interpreter(phrase: str, image: Path | None = None) -> tuple[str | None, dict, str | None]:
    """Phrase française -> (objet, params, question). Point d'entrée principal."""
    return valider(demander_oen(phrase, image_jointe=image is not None), image=image)


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_") or "piece"


def generer(objet: str, p: dict) -> Path:
    """Appelle le générateur et exporte. Renvoie le chemin du fichier à charger
    (3MF de préférence — multi-corps pour les logos — sinon STL)."""
    import trimesh
    DOSSIER_SORTIES.mkdir(parents=True, exist_ok=True)
    scene = None
    if objet == "porte_cle":
        from core.neogen.texte import construire_porte_cle
        piece = construire_porte_cle(
            p["texte"], p.get("longueur", 50), ep_socle=p.get("socle", 3.0),
            ep_texte=p.get("relief", 1.6), d_trou=p.get("trou", 4.5),
            grave=p.get("grave", False))
        nom = f"porte_cle_{_slug(p['texte'])}"
    elif objet in ("badge", "sousverre", "plaque", "magnet"):
        from core.neogen import goodies
        if objet == "badge":
            piece = goodies.badge(p["texte"], p.get("diametre", 40),
                                  grave=p.get("grave", False),
                                  trou=4.5 if p.get("trou") else 0.0)
        elif objet == "sousverre":
            piece = goodies.sous_verre(p["texte"], p.get("diametre", 90))
        elif objet == "plaque":
            piece = goodies.plaque(p["texte"], p.get("largeur", 0),
                                   grave=p.get("grave", False), vis=p.get("vis", False))
        else:
            piece = goodies.magnet(p["texte"], p.get("diametre", 35),
                                   d_aimant=p.get("aimant_d", 10.2),
                                   prof_aimant=p.get("aimant_p", 2.0))
        nom = f"{objet}_{_slug(p['texte'])}"
    elif objet == "logo":
        from core.neogen import logo as _logo
        src = Path(p["image"])
        if src.suffix.lower() == ".svg":
            couches = _logo.charger_svg(str(src))
        else:
            couches = _logo.charger_png(str(src), int(p.get("couleurs", 3)))
        couches = _logo._normaliser(couches, p.get("largeur", 40))
        scene, piece = _logo.construire(couches, p.get("forme", "badge"),
                                        p.get("diametre", 0) or 0, 0, 3.0, 1.2)
        nom = f"logo_{_slug(src.stem)}_{p.get('forme', 'badge')}"
    else:
        from core.neogen import objets
        if objet == "vase":
            piece = objets.vase(p.get("hauteur", 100), p.get("diametre", 60),
                                ondulations=int(p.get("ondulations", 5)))
            nom = f"vase_{int(p.get('hauteur', 100))}mm"
        elif objet == "boite":
            scene = objets.boite(p.get("diametre", 50), p.get("hauteur", 30),
                                 jeu=p.get("jeu", 0.2))
            piece = trimesh.util.concatenate(list(scene.geometry.values()))
            nom = f"boite_{int(p.get('diametre', 50))}mm"
        elif objet == "support":
            piece = objets.support_tel(p.get("largeur", 70))
            nom = "support_telephone"
        else:
            piece = objets.de_a_jouer(p.get("taille", 16))
            nom = f"de_{int(p.get('taille', 16))}mm"

    base = DOSSIER_SORTIES / nom
    piece.export(base.with_suffix(".stl"))
    try:
        (scene or piece).export(base.with_suffix(".3mf"))
        return base.with_suffix(".3mf")
    except Exception:
        return base.with_suffix(".stl")


def resume_params(objet: str, p: dict) -> str:
    """Petit résumé lisible de ce qu'Oen a compris (affiché avant génération)."""
    noms = {"porte_cle": "porte-clé", "sousverre": "sous-verre", "de": "dé",
            "support": "support téléphone", "boite": "boîte"}
    morceaux = [noms.get(objet, objet)]
    if p.get("texte"):
        morceaux.append(f"« {p['texte']} »")
    for cle, unite in (("longueur", "mm"), ("diametre", "mm"), ("hauteur", "mm"),
                       ("largeur", "mm"), ("taille", "mm"), ("trou", "mm"),
                       ("jeu", "mm"), ("relief", "mm")):
        v = p.get(cle)
        if isinstance(v, (int, float)) and v:
            morceaux.append(f"{cle} {v:g} {unite}")
    for flag, lib in (("grave", "gravé"), ("vis", "trous de vis"), ("trou", "avec accroche")):
        if p.get(flag) is True:
            morceaux.append(lib)
    return " · ".join(morceaux)
