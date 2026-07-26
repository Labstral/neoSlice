# -*- coding: utf-8 -*-
"""neoGen — CATALOGUE : registre des objets pré-construits et de leurs schémas.

Chaque entrée décrit un objet générable : nom FR/EN, domaine, paramètres
(bornes/défauts), options booléennes, choix (forme...), texte
(aucun/optionnel/requis) et la fonction de construction. Le menu
« Bibliothèque » de neoGen construit son formulaire AUTOMATIQUEMENT depuis
ces schémas — ajouter un objet ici = il apparaît dans l'app.

Structure d'une entrée :
    id, fr, en, domaine,
    texte: "aucun"|"optionnel"|"requis",
    image: bool (l'objet demande un fichier logo),
    params: [(id, fr, en, min, max, defaut, pas)],
    flags:  [(id, fr, en, defaut)],
    choix:  [(id, fr, en, [(valeur, fr, en), ...], defaut)],
    couleurs: [(id, fr, en, hex_defaut)]  -> sélecteurs de couleur (objet, texte…) ;
              le builder reçoit couleur_<id> et renvoie une Scene à corps colorés,
    construire: fonction(params: dict) -> Trimesh | Scene
"""
from __future__ import annotations

# Domaines (ordre d'affichage dans le menu)
DOMAINES = [
    ("perso",   "Accessoires & cadeaux", "Accessories & gifts"),
    ("maison",  "Maison & rangement", "Home & storage"),
    ("cuisine", "Cuisine", "Kitchen"),
    ("bureau",  "Bureau & tech", "Desk & tech"),
    ("sdb",     "Salle de bain & jardin", "Bathroom & garden"),
    ("deco",    "Décoration", "Decoration"),
    ("jeux",    "Jeux & loisirs", "Games & hobbies"),
    ("atelier", "Atelier & fixation", "Workshop & fixing"),
    ("resto",   "Restauration", "Restaurant"),
    ("mariage", "Mariage & événementiel", "Wedding & events"),
    ("commerce", "Boutique & bureau pro", "Shop & pro office"),
    ("calibration", "Calibration & tests", "Calibration & tests"),
]


def _e(id, fr, en, domaine, construire, texte="aucun", image=False,
       params=(), flags=(), choix=(), couleurs=()):
    return {"id": id, "fr": fr, "en": en, "domaine": domaine, "texte": texte,
            "image": image, "params": list(params), "flags": list(flags),
            "choix": list(choix), "couleurs": list(couleurs), "construire": construire}


# ── Constructeurs (imports paresseux : le catalogue se charge instantanément) ─
def _b_porte_cle(p):
    from core.neogen.texte import construire_porte_cle
    return construire_porte_cle(p.get("texte", ""), p.get("longueur", 50),
                                ep_socle=p.get("socle", 3.0), ep_texte=p.get("relief", 1.6),
                                d_trou=p.get("trou", 4.5),
                                style=p.get("style"), grave=p.get("grave", False),
                                forme=p.get("forme", "contour"),
                                police=p.get("police"),
                                couleur_objet=p.get("couleur_objet"),
                                couleur_texte=p.get("couleur_texte"))

def _bicol(p):
    """Kwargs bicolore/style communs (menu relief/gravé/lisse + 2 couleurs)."""
    return dict(style=p.get("style"),
                couleur_objet=p.get("couleur_objet"),
                couleur_texte=p.get("couleur_texte"))

def _b_badge(p):
    from core.neogen.goodies import badge
    return badge(p.get("texte", ""), p.get("diametre", 40), grave=p.get("grave", False),
                 trou=4.5 if p.get("accroche") else 0.0, police=p.get("police"), **_bicol(p))

def _b_sousverre(p):
    from core.neogen.goodies import sous_verre
    return sous_verre(p.get("texte", ""), p.get("diametre", 90), police=p.get("police"),
                      couleur_objet=p.get("couleur_objet"),
                      couleur_texte=p.get("couleur_texte"))

def _b_plaque(p):
    from core.neogen.goodies import plaque
    return plaque(p.get("texte", ""), p.get("largeur", 0), grave=p.get("grave", False),
                  vis=p.get("vis", False), police=p.get("police"), **_bicol(p))

def _b_magnet(p):
    from core.neogen.goodies import magnet
    return magnet(p.get("texte", ""), p.get("diametre", 35),
                  d_aimant=p.get("aimant_d", 10.2), prof_aimant=p.get("aimant_p", 2.0),
                  police=p.get("police"), **_bicol(p))

def _b_vase(p):
    from core.neogen.objets import vase
    return vase(p.get("hauteur", 100), p.get("diametre", 60),
                ondulations=int(p.get("ondulations", 5)))

def _b_boite(p):
    from core.neogen.objets import boite
    return boite(p.get("taille", 50), p.get("hauteur", 30), jeu=p.get("jeu", 0.2),
                 forme=p.get("forme", "ronde"), cote=p.get("taille", 50),
                 longueur=p.get("longueur", 90), largeur=p.get("largeur", 60))

def _b_support_tel(p):
    from core.neogen.objets import support_tel
    return support_tel(p.get("largeur", 70), hauteur=p.get("hauteur", 92))

def _b_de(p):
    from core.neogen.objets import de_a_jouer
    return de_a_jouer(p.get("taille", 16))

def _b_logo(p):
    from core.neogen import logo as L
    from core.neogen.bicolore import _hex_rgba
    from pathlib import Path
    src = Path(p["image"])
    # 1 seule couche = SILHOUETTE du logo → objet bicolore simple (socle + logo),
    # bien plus clair que « quantifier l'image en N couleurs ».
    couches = (L.charger_svg(str(src)) if src.suffix.lower() == ".svg"
               else L.charger_png(str(src), 1))
    couches = L._normaliser(couches, p.get("largeur", 40))
    scene, _f = L.construire(couches, p.get("forme", "badge"),
                             p.get("diametre", 0) or 0, 0, 3.0, 1.2)
    # Couleurs choisies : socle = couleur objet, logo = couleur logo.
    c_obj = _hex_rgba(p.get("couleur_objet", "#3B82F6"))
    c_logo = _hex_rgba(p.get("couleur_logo", "#111111"))
    for nom, g in scene.geometry.items():
        g.visual.face_colors = c_obj if nom == "socle" else c_logo
    return scene


def _b_vis(p):
    from core.neogen import formes3
    taille = str(p.get("taille", "M6")).upper()
    if p.get("ecrou"):
        return formes3.boulon(taille, p.get("longueur", 30))
    return formes3.vis_hex(taille, p.get("longueur", 30))


def _b_qrcode(p):
    from core.neogen.qrcode_3d import qr_3d
    return qr_3d(p.get("texte", ""), taille=p.get("taille", 70),
                 variante=p.get("variante", "plat_trous"),
                 epaisseur=p.get("epaisseur", 2.0),
                 style=p.get("style", "relief"),
                 couleur_fond=p.get("couleur_fond", "#F2F2F2"),
                 couleur_module=p.get("couleur_modules", "#111111"))


def _f(mod, nom):
    """Renvoie un constructeur paresseux appelant formes/formes2.nom(**params)."""
    def _build(p):
        import importlib
        m = importlib.import_module(f"core.neogen.{mod}")
        import inspect
        fn = getattr(m, nom)
        args = {k: v for k, v in p.items() if k in inspect.signature(fn).parameters}
        return fn(**args)
    return _build


# ═════════════════════════════════ CATALOGUE ════════════════════════════════
# Élargissement CENTRAL des plages de mesures : on donne plus de marge (plus
# petit ET plus grand) sur les DIMENSIONS et les ÉPAISSEURS de chaque objet,
# sans toucher aux comptages, aux jeux/ajustements, aux angles/positions ni aux
# paires Ø intérieur/extérieur (qui deviennent incohérentes si on les élargit à
# l'aveugle). Le défaut reste toujours dans les bornes.
_DIM_NAMES = {
    "longueur", "largeur", "hauteur", "taille", "diametre", "profondeur",
    "base", "saillie", "entraxe", "hauteur_photo", "largeur_photo",
    "d_cable", "d_trou_panneau", "ep_panneau",
}
_THICK_NAMES = {"epaisseur", "ep", "section", "socle", "rebord", "bord"}


def _arrondi(v):
    v = float(v)
    if v >= 20:
        return round(v / 5.0) * 5
    if v >= 5:
        return float(round(v))
    return round(v, 1)


def _P(pid, fr, en, mn, mx, default, pas, mnf=8):   # (id, fr, en, min, max, defaut, pas)
    # mnf = plancher du mini après élargissement (relevé pour les objets qui ont
    # un mini géométrique dur, ex. porte-clé : < ~22 mm impossible avec le trou).
    if pid in _DIM_NAMES:
        # On va surtout plus GRAND (×1.8) ; on descend un peu (×0.7) sans casser
        # les petits objets à texte (porte-clé, tirette…).
        mn = min(mn, max(_arrondi(mn * 0.7), mnf))
        mx = max(mx, _arrondi(mx * 1.8))
    elif pid in _THICK_NAMES:
        # Épaisseurs : on n'abaisse PAS le mini (paroi trop fine / socle < 1.2 mm
        # = pièce fragile refusée par les builders) ; on relève juste le maxi.
        mx = max(mx, _arrondi(mx * 1.6))
    # Le défaut doit rester valide dans les nouvelles bornes.
    mn = min(mn, default)
    mx = max(mx, default)
    return (pid, fr, en, mn, mx, default, pas)
_FORMES3 = [("rond", "Rond", "Round"), ("carre", "Carré", "Square"),
            ("hexagone", "Hexagonal", "Hexagonal")]

CATALOGUE = [
    # ── Personnalisation ──
    _e("qrcode", "QR code (menu, lien…)", "QR code (menu, link…)", "perso", _b_qrcode,
       texte="lien",
       params=[_P("taille", "Taille (carré)", "Size (square)", 50, 150, 70, 5),
               _P("epaisseur", "Épaisseur", "Thickness", 1.5, 6.0, 2.0, 0.5)],
       choix=[("variante", "Format", "Format",
               [("plat_trous", "À plat + trous à visser", "Flat + screw holes"),
                ("plat", "À plat sans trous", "Flat, no holes"),
                ("presentoir", "Présentoir incliné", "Tilted stand"),
                ("porte_cle", "Porte-clé", "Keychain")], "plat_trous"),
              ("style", "Modules", "Modules",
               [("relief", "En relief", "Raised"),
                ("creuse", "Creusés", "Engraved"),
                ("lisse", "Lisses", "Flush")], "relief")],
       couleurs=[("fond", "Couleur plaque", "Plate color", "#F2F2F2"),
                 ("modules", "Couleur modules", "Modules color", "#111111")]),
    _e("porte_cle", "Porte-clé", "Keychain", "perso", _b_porte_cle, texte="optionnel",
       params=[_P("longueur", "Longueur", "Length", 25, 120, 50, 1, mnf=25),
               _P("trou", "Trou (ø)", "Hole (ø)", 2, 12, 4.5, 0.5),
               _P("relief", "Hauteur texte", "Text height", 0.4, 4, 1.6, 0.2),
               _P("socle", "Épaisseur socle", "Base thickness", 1.5, 8, 3, 0.5)],
       choix=[("forme", "Forme", "Shape",
               [("contour", "Suit les lettres", "Follows the letters"),
                ("rectangle", "Rectangle", "Rectangle"),
                ("ovale", "Ovale", "Oval"),
                ("rond", "Rond", "Round"),
                ("etiquette", "Étiquette", "Tag")], "contour"),
              ("style", "Texte", "Text",
               [("relief", "En relief", "Raised"),
                ("grave", "Gravé", "Engraved"),
                ("lisse", "Lisse", "Flush")], "relief")],
       couleurs=[("objet", "Couleur objet", "Object color", "#3B82F6"),
                 ("texte", "Couleur texte", "Text color", "#FFFFFF")]),
    _e("badge", "Badge", "Badge", "perso", _b_badge, texte="optionnel",
       params=[_P("diametre", "Diamètre", "Diameter", 20, 120, 40, 1)],
       flags=[("grave", "Texte gravé", "Engraved text", False),
              ("accroche", "Trou d'accroche", "Hanging hole", False)]),
    _e("plaque", "Plaque (multi-lignes)", "Plate (multi-line)", "perso", _b_plaque,
       texte="optionnel",
       params=[_P("largeur", "Largeur (0=auto)", "Width (0=auto)", 0, 300, 0, 5)],
       flags=[("grave", "Texte gravé", "Engraved text", False),
              ("vis", "Trous de vis", "Screw holes", False)]),
    _e("magnet", "Magnet frigo", "Fridge magnet", "perso", _b_magnet, texte="optionnel",
       params=[_P("diametre", "Diamètre", "Diameter", 20, 80, 35, 1),
               _P("aimant_d", "Aimant (ø)", "Magnet (ø)", 4, 25, 10.2, 0.1),
               _P("aimant_p", "Aimant (prof.)", "Magnet (depth)", 1, 5, 2, 0.5)]),
    _e("sousverre", "Sous-verre", "Coaster", "perso", _b_sousverre, texte="optionnel",
       params=[_P("diametre", "Diamètre", "Diameter", 60, 140, 90, 5)]),
    _e("photo_relief", "Photo en relief / lithophanie", "Photo relief / lithophane",
       "perso", _f("relief_photo", "photo_en_relief"), image=True,
       params=[_P("largeur", "Largeur", "Width", 40, 200, 100, 5),
               _P("ep_min", "Épaisseur mini", "Min thickness", 0.4, 2, 0.8, 0.2),
               _P("ep_max", "Épaisseur maxi", "Max thickness", 1.6, 6, 3.2, 0.2)],
       flags=[("cadre", "Cadre rigide", "Rigid frame", True),
              ("debout", "Debout (qualité lithophanie)", "Standing (lithophane quality)", True)],
       choix=[("mode", "Mode", "Mode",
               [("lithophanie", "Lithophanie (rétro-éclairée)", "Lithophane (backlit)"),
                ("relief", "Relief décoratif", "Decorative relief")], "lithophanie")]),
    _e("logo", "Logo 3D (image)", "3D logo (image)", "perso", _b_logo, image=True,
       params=[_P("largeur", "Taille du logo", "Logo size", 15, 150, 40, 5)],
       choix=[("forme", "Support", "Base",
               [("badge", "Badge rond", "Round badge"),
                ("plaque", "Plaque", "Plate"),
                ("silhouette", "Silhouette", "Outline")], "badge")],
       couleurs=[("objet", "Couleur objet", "Object color", "#3B82F6"),
                 ("logo", "Couleur logo", "Logo color", "#111111")]),
    _e("marque_page", "Marque-page", "Bookmark", "perso", _f("formes", "marque_page"),
       texte="optionnel",
       params=[_P("longueur", "Longueur", "Length", 80, 220, 140, 5),
               _P("largeur", "Largeur", "Width", 20, 60, 35, 1),
               _P("ep", "Épaisseur", "Thickness", 0.8, 3.2, 1.6, 0.2),
               _P("pos_x", "Position texte X", "Text position X", -60, 60, 0, 1),
               _P("pos_y", "Position texte Y", "Text position Y", -100, 100, 0, 1)],
       choix=[("orientation", "Sens du texte", "Text direction",
               [("perpendiculaire", "Perpendiculaire", "Perpendicular"),
                ("parallele", "Parallèle", "Parallel")], "perpendiculaire")]),
    _e("tire_fermeture", "Tirette de zip", "Zipper pull", "perso",
       _f("formes2", "tire_fermeture"), texte="optionnel",
       params=[_P("longueur", "Longueur", "Length", 20, 60, 30, 1)]),

    # ── Maison & rangement ──
    _e("boite", "Boîte + couvercle", "Box + lid", "maison", _b_boite,
       params=[_P("taille", "Diamètre / côté", "Diameter / side", 25, 150, 50, 1),
               _P("longueur", "Longueur", "Length", 40, 220, 90, 1),
               _P("largeur", "Largeur", "Width", 30, 160, 60, 1),
               _P("hauteur", "Hauteur", "Height", 12, 120, 30, 1),
               _P("jeu", "Jeu couvercle", "Lid clearance", 0.1, 0.5, 0.2, 0.05)],
       choix=[("forme", "Forme", "Shape",
               [("ronde", "Ronde", "Round"), ("carree", "Carrée", "Square"),
                ("rectangulaire", "Rectangulaire", "Rectangular")], "ronde")]),
    _e("bac_compartiments", "Organiseur à cases", "Compartment tray", "maison",
       _f("formes", "bac_compartiments"),
       params=[_P("longueur", "Longueur", "Length", 60, 260, 140, 5),
               _P("largeur", "Largeur", "Width", 40, 200, 90, 5),
               _P("hauteur", "Hauteur", "Height", 15, 80, 35, 1),
               _P("cases_x", "Cases (long.)", "Cells (length)", 1, 6, 3, 1),
               _P("cases_y", "Cases (larg.)", "Cells (width)", 1, 5, 2, 1)]),
    _e("bac_empilable", "Bac empilable", "Stackable bin", "maison",
       _f("formes", "bac_empilable"),
       params=[_P("longueur", "Longueur", "Length", 60, 220, 120, 5),
               _P("largeur", "Largeur", "Width", 50, 180, 90, 5),
               _P("hauteur", "Hauteur", "Height", 25, 100, 50, 5)]),
    _e("plateau", "Plateau vide-poche", "Catch-all tray", "maison",
       _f("formes", "plateau"),
       params=[_P("longueur", "Longueur", "Length", 100, 300, 200, 5),
               _P("largeur", "Largeur", "Width", 80, 220, 140, 5),
               _P("rebord", "Rebord", "Rim", 6, 30, 12, 1)]),
    _e("crochet_mural", "Crochet mural", "Wall hook", "maison",
       _f("formes", "crochet_mural"),
       params=[_P("hauteur", "Hauteur", "Height", 35, 120, 60, 5),
               _P("profondeur", "Profondeur", "Depth", 20, 70, 35, 1),
               _P("largeur", "Largeur", "Width", 12, 40, 20, 1)],
       flags=[("vis", "Trous de vis", "Screw holes", True)]),
    _e("poignee_meuble", "Poignée de meuble", "Furniture handle", "maison",
       _f("formes", "poignee_meuble"),
       params=[_P("entraxe", "Entraxe", "Hole spacing", 64, 160, 96, 16),
               _P("saillie", "Saillie", "Projection", 18, 45, 28, 1),
               _P("section", "Section", "Section", 8, 16, 10, 1)]),
    _e("butee_porte", "Butée de porte", "Door stopper", "maison",
       _f("formes", "butee_porte"),
       params=[_P("diametre", "Diamètre", "Diameter", 25, 70, 40, 1),
               _P("hauteur", "Hauteur", "Height", 15, 45, 25, 1)]),
    _e("cale_porte", "Cale de porte", "Door wedge", "maison",
       _f("formes2", "cale_porte"),
       params=[_P("longueur", "Longueur", "Length", 60, 140, 90, 5),
               _P("hauteur", "Hauteur", "Height", 20, 45, 30, 1)]),
    _e("pied_meuble", "Pied de meuble", "Furniture foot", "maison",
       _f("formes", "pied_meuble"),
       params=[_P("d_bas", "Ø / côté base", "Base ø / side", 25, 80, 45, 1),
               _P("d_haut", "Ø sommet (conique)", "Top ø (cone)", 15, 60, 30, 1),
               _P("hauteur", "Hauteur", "Height", 15, 120, 40, 1),
               _P("trou_d", "Ø trou sommet", "Top hole ø", 0, 30, 0, 0.5),
               _P("trou_prof", "Profondeur trou", "Hole depth", 0, 60, 0, 1)],
       choix=[("forme", "Forme", "Shape",
               [("conique", "Conique", "Tapered"),
                ("cylindrique", "Cylindrique", "Cylindrical"),
                ("carre", "Carré", "Square")], "conique")]),
    _e("separateur_tiroir", "Séparateur de tiroir", "Drawer divider", "maison",
       _f("formes", "separateur_tiroir"),
       params=[_P("longueur", "Longueur", "Length", 80, 300, 150, 5),
               _P("hauteur", "Hauteur", "Height", 30, 100, 60, 5)]),
    _e("cadre_photo", "Cadre photo", "Photo frame", "maison",
       _f("formes", "cadre_photo"), texte="optionnel",
       params=[_P("largeur_photo", "Largeur photo", "Photo width", 60, 210, 100, 1),
               _P("hauteur_photo", "Hauteur photo", "Photo height", 60, 300, 150, 1),
               _P("bord", "Largeur du cadre", "Frame border", 8, 30, 12, 1),
               _P("relief", "Hauteur du texte", "Text height", 0.4, 2.0, 0.8, 0.1)],
       choix=[("style", "Texte", "Text",
               [("relief", "En relief", "Raised"),
                ("grave", "Gravé", "Engraved"),
                ("lisse", "Lisse", "Flush")], "grave")],
       couleurs=[("cadre", "Couleur cadre", "Frame color", "#EDEDED"),
                 ("fond", "Couleur fond", "Back color", "#3B82F6"),
                 ("texte", "Couleur texte", "Text color", "#111111")]),
    _e("protege_coin", "Protège-coin", "Corner protector", "maison",
       _f("formes", "protege_coin"),
       params=[_P("taille", "Taille", "Size", 25, 70, 40, 1),
               _P("ep", "Épaisseur", "Thickness", 2, 6, 3, 0.5)]),

    # ── Cuisine ──
    _e("dessous_de_plat", "Dessous-de-plat", "Trivet", "cuisine",
       _f("formes", "dessous_de_plat"),
       params=[_P("taille", "Taille", "Size", 100, 240, 160, 5)],
       choix=[("forme", "Forme", "Shape", _FORMES3, "rond"),
              ("motif", "Motif", "Pattern",
               [("nid_abeille", "Nid d'abeille", "Honeycomb"),
                ("rond", "Trous ronds", "Round holes"),
                ("plein", "Plein", "Solid")], "nid_abeille")]),
    _e("repose_cuillere", "Repose-cuillère", "Spoon rest", "cuisine",
       _f("formes", "repose_cuillere"),
       params=[_P("longueur", "Longueur", "Length", 150, 280, 220, 5),
               _P("largeur", "Largeur", "Width", 60, 120, 90, 5)]),
    _e("rond_serviette", "Rond de serviette", "Napkin ring", "cuisine",
       _f("formes", "rond_serviette"), texte="optionnel",
       params=[_P("diametre", "Diamètre", "Diameter", 35, 60, 45, 1),
               _P("largeur", "Largeur", "Width", 20, 45, 30, 1),
               _P("pos_z", "Hauteur du texte", "Text height pos", -15, 15, 0, 1),
               _P("angle", "Rotation du texte", "Text rotation", -180, 180, 0, 5)]),
    _e("coquetier", "Coquetier", "Egg cup", "cuisine",
       _f("formes", "coquetier"),
       params=[_P("hauteur", "Hauteur", "Height", 35, 65, 45, 1)]),
    _e("gobelet", "Gobelet / pot droit", "Cup / straight pot", "cuisine",
       _f("formes", "gobelet"), texte="optionnel",
       params=[_P("diametre", "Diamètre", "Diameter", 50, 110, 70, 5),
               _P("hauteur", "Hauteur", "Height", 50, 150, 90, 5),
               _P("pos_z", "Hauteur du texte", "Text height pos", -60, 60, 0, 2),
               _P("angle", "Rotation du texte", "Text rotation", -180, 180, 0, 5)]),
    _e("entonnoir", "Entonnoir", "Funnel", "cuisine",
       _f("formes", "entonnoir"),
       params=[_P("d_haut", "Ø entrée", "Inlet ø", 40, 140, 80, 5),
               _P("d_bas", "Ø sortie", "Outlet ø", 6, 30, 12, 1),
               _P("hauteur", "Hauteur", "Height", 40, 140, 70, 5)]),
    _e("emporte_piece", "Emporte-pièce", "Cookie cutter", "cuisine",
       _f("formes2", "emporte_piece"),
       params=[_P("taille", "Taille", "Size", 40, 110, 70, 5)],
       choix=[("forme", "Forme", "Shape",
               [("coeur", "Cœur", "Heart"), ("etoile", "Étoile", "Star"),
                ("rond", "Rond", "Round"), ("carre", "Carré", "Square")], "coeur")]),
    _e("oeuf_pied", "Coupe", "Footed cup", "cuisine",
       _f("formes2", "oeuf_pied"),
       params=[_P("hauteur", "Hauteur", "Height", 40, 90, 55, 1)]),

    # ── Bureau & tech ──
    _e("pot_crayons", "Pot à crayons", "Pencil holder", "bureau",
       _f("formes", "pot_crayons"),
       params=[_P("diametre", "Taille", "Size", 55, 120, 80, 5),
               _P("hauteur", "Hauteur", "Height", 60, 140, 100, 5)],
       flags=[("compartiments", "Séparateur en croix", "Cross divider", False)],
       choix=[("forme", "Forme", "Shape", _FORMES3, "hexagone")]),
    _e("support_tel", "Support téléphone / tablette", "Phone / tablet stand", "bureau", _b_support_tel,
       params=[_P("largeur", "Largeur", "Width", 40, 220, 70, 5),
               _P("hauteur", "Hauteur dossier", "Back height", 60, 180, 92, 5)]),
    _e("porte_cartes", "Porte-cartes de visite", "Business card holder", "bureau",
       _f("formes", "porte_cartes"),
       params=[_P("largeur", "Largeur", "Width", 70, 140, 100, 5),
               _P("fente", "Largeur de la fente", "Slot width", 1.4, 6, 2.5, 0.1)]),
    _e("clip_cable", "Clip de câble", "Cable clip", "bureau",
       _f("formes", "clip_cable"),
       params=[_P("d_cable", "Ø câble", "Cable ø", 3, 12, 5, 0.5)],
       flags=[("vis", "Trou de vis", "Screw hole", True)]),
    _e("passe_cable", "Passe-câble bureau", "Desk grommet", "bureau",
       _f("formes", "passe_cable"),
       params=[_P("d_trou_panneau", "Ø trou du bureau", "Desk hole ø", 35, 90, 60, 1),
               _P("ep_panneau", "Épaisseur plateau", "Desktop thickness", 10, 45, 18, 1)]),
    _e("range_cable", "Range-câble (bobine)", "Cable spool", "bureau",
       _f("formes2", "range_cable"),
       params=[_P("diametre", "Diamètre", "Diameter", 45, 110, 70, 5),
               _P("largeur", "Largeur", "Width", 18, 60, 30, 1)]),
    _e("regle", "Règle graduée", "Ruler", "bureau",
       _f("formes2", "regle"),
       params=[_P("longueur", "Longueur", "Length", 100, 300, 150, 10),
               _P("largeur", "Largeur", "Width", 18, 40, 25, 1)]),

    # ── Salle de bain & jardin ──
    _e("porte_savon", "Porte-savon", "Soap dish", "sdb",
       _f("formes", "porte_savon"),
       params=[_P("longueur", "Longueur", "Length", 80, 140, 105, 5),
               _P("largeur", "Largeur", "Width", 55, 110, 75, 5),
               _P("hauteur", "Hauteur", "Height", 15, 35, 22, 1)]),
    _e("pot_fleur", "Pot de fleurs", "Flower pot", "sdb",
       _f("formes", "pot_fleur"),
       params=[_P("diametre", "Diamètre", "Diameter", 60, 200, 110, 5),
               _P("hauteur", "Hauteur", "Height", 50, 200, 100, 5)],
       flags=[("drainage", "Trous de drainage", "Drainage holes", True),
              ("soucoupe", "Générer la soucoupe", "Generate the saucer", False)]),
    _e("etiquette_plante", "Étiquette de plantation", "Plant label", "sdb",
       _f("formes", "etiquette_plante"), texte="optionnel",
       params=[_P("longueur", "Longueur", "Length", 80, 200, 120, 5),
               _P("largeur", "Largeur", "Width", 15, 35, 22, 1),
               _P("pos_x", "Position texte X", "Text position X", -30, 30, 0, 1),
               _P("pos_y", "Position texte Y", "Text position Y", -50, 50, 0, 1)]),
    _e("gobelet_sdb", "Gobelet brosses à dents", "Toothbrush cup", "sdb",
       _f("formes", "gobelet"),
       params=[_P("diametre", "Diamètre", "Diameter", 55, 100, 75, 5),
               _P("hauteur", "Hauteur", "Height", 70, 130, 100, 5)]),

    # ── Décoration ──
    _e("vase", "Vase ondulé", "Wavy vase", "deco", _b_vase,
       params=[_P("hauteur", "Hauteur", "Height", 30, 250, 100, 5),
               _P("diametre", "Diamètre", "Diameter", 30, 150, 60, 5),
               _P("ondulations", "Ondulations", "Waves", 0, 12, 5, 1)]),
    _e("ornement_etoile", "Étoile déco", "Star ornament", "deco",
       _f("formes2", "ornement_etoile"), texte="optionnel",
       params=[_P("diametre", "Diamètre", "Diameter", 40, 160, 80, 5),
               _P("branches", "Branches", "Points", 4, 8, 5, 1),
               _P("ep", "Épaisseur", "Thickness", 2, 10, 4, 0.5)],
       flags=[("suspension", "Trou de suspension", "Hanging hole", True)]),
    _e("coeur_deco", "Cœur déco", "Heart ornament", "deco",
       _f("formes2", "coeur_deco"), texte="optionnel",
       params=[_P("taille", "Taille", "Size", 35, 150, 70, 5),
               _P("ep", "Épaisseur", "Thickness", 2, 12, 5, 0.5)],
       flags=[("suspension", "Trou de suspension", "Hanging hole", False)]),
    _e("lettre_3d", "Lettre / initiale 3D", "3D letter / initial", "deco",
       _f("formes2", "lettre_3d"), texte="requis",
       params=[_P("hauteur", "Hauteur", "Height", 40, 250, 100, 10),
               _P("ep", "Épaisseur", "Thickness", 6, 40, 15, 1)]),
    _e("numero_maison", "Numéro de maison", "House number", "deco",
       _f("formes2", "numero_maison"), texte="requis",
       params=[_P("hauteur", "Hauteur", "Height", 60, 220, 120, 10)]),
    _e("trophee", "Trophée", "Trophy", "deco",
       _f("formes2", "trophee"), texte="optionnel",
       params=[_P("hauteur", "Hauteur", "Height", 70, 220, 120, 10)]),

    # ── Jeux & loisirs ──
    _e("de", "Dé à jouer", "Playing die", "jeux", _b_de,
       params=[_P("taille", "Taille", "Size", 8, 40, 16, 1)]),
    _e("jeton", "Jeton (poker, caddie)", "Token (poker, cart)", "jeux",
       _f("formes2", "jeton"), texte="optionnel",
       params=[_P("diametre", "Diamètre", "Diameter", 25, 60, 40, 1),
               _P("ep", "Épaisseur", "Thickness", 2, 6, 3.6, 0.2)]),
    _e("socle_figurine", "Socle de figurine", "Figure base", "jeux",
       _f("formes2", "socle_figurine"), texte="optionnel",
       params=[_P("diametre", "Taille", "Size", 25, 150, 60, 5),
               _P("hauteur", "Hauteur", "Height", 5, 20, 8, 1)],
       choix=[("forme", "Forme", "Shape", _FORMES3, "rond")]),
    _e("pion_jeu", "Pion de jeu", "Game pawn", "jeux",
       _f("formes2", "pion_jeu"),
       params=[_P("hauteur", "Hauteur", "Height", 25, 70, 40, 1)]),
    _e("porte_cartes_jeu", "Support cartes à jouer", "Card holder", "jeux",
       _f("formes2", "porte_cartes_jeu"),
       params=[_P("largeur", "Largeur", "Width", 120, 400, 250, 10),
               _P("rangees", "Rangées", "Rows", 2, 5, 3, 1)]),

    # ── Atelier & fixation ──
    _e("equerre", "Équerre de fixation", "Mounting bracket", "atelier",
       _f("formes", "equerre"),
       params=[_P("taille", "Taille", "Size", 40, 150, 80, 5),
               _P("ep", "Épaisseur", "Thickness", 3, 8, 4, 0.5)],
       flags=[("vis", "Trous de vis", "Screw holes", True)]),
    _e("rondelle", "Rondelle", "Washer", "atelier",
       _f("formes", "rondelle"),
       params=[_P("d_ext", "Ø extérieur", "Outer ø", 8, 60, 24, 1),
               _P("d_int", "Ø intérieur", "Inner ø", 2, 40, 8, 0.5),
               _P("ep", "Épaisseur", "Thickness", 1, 10, 3, 0.5)]),
    _e("entretoise", "Entretoise", "Spacer", "atelier",
       _f("formes", "entretoise"),
       params=[_P("d_ext", "Ø extérieur", "Outer ø", 6, 30, 12, 1),
               _P("d_int", "Ø intérieur", "Inner ø", 2, 20, 5, 0.5),
               _P("hauteur", "Hauteur", "Height", 3, 60, 15, 1)],
       choix=[("forme", "Forme", "Shape",
               [("rond", "Ronde", "Round"),
                ("hexagonal", "Hexagonale", "Hex")], "rond")]),
    _e("organiseur_forets", "Bloc porte-forets", "Drill bit block", "atelier",
       _f("formes", "organiseur_forets"),
       params=[_P("rangees", "Rangées", "Rows", 2, 5, 3, 1),
               _P("colonnes", "Colonnes", "Columns", 4, 14, 8, 1)]),
    _e("joint", "Joint (plat / torique)", "Gasket (flat / O-ring)", "atelier",
       _f("formes", "joint"),
       params=[_P("d_ext", "Ø extérieur", "Outer ø", 6, 120, 30, 1),
               _P("d_int", "Ø intérieur", "Inner ø", 3, 110, 20, 1),
               _P("epaisseur", "Épaisseur", "Thickness", 1, 20, 3, 0.5)],
       choix=[("type_joint", "Type", "Type",
               [("plat", "Joint plat", "Flat gasket"),
                ("torique", "Joint torique", "O-ring")], "plat")]),
    # Visserie : filetage ISO généré en maillage (M6+ uniquement — en dessous,
    # le filetage FDM buse 0.4 n'est pas fiable : on ne le propose pas).
    _e("vis", "Vis à tête hex (M6–M12)", "Hex bolt (M6–M12)", "atelier", _b_vis,
       params=[_P("longueur", "Longueur filetée", "Thread length", 12, 80, 30, 2)],
       flags=[("ecrou", "Avec son écrou (à côté)", "With its nut (beside)", True)],
       choix=[("taille", "Taille", "Size",
               [("M6", "M6", "M6"), ("M8", "M8", "M8"),
                ("M10", "M10", "M10"), ("M12", "M12", "M12")], "M8")]),
    _e("ecrou", "Écrou hex (M6–M12)", "Hex nut (M6–M12)", "atelier",
       _f("formes3", "ecrou_hex"),
       choix=[("taille", "Taille", "Size",
               [("M6", "M6", "M6"), ("M8", "M8", "M8"),
                ("M10", "M10", "M10"), ("M12", "M12", "M12")], "M8")]),

    # ── Restauration ──
    _e("numero_table", "Numéro de table", "Table number", "resto",
       _f("pro_resto", "numero_table"), texte="requis",
       params=[_P("hauteur", "Hauteur chiffres", "Digit height", 40, 140, 80, 5),
               _P("ep", "Épaisseur", "Thickness", 6, 16, 10, 1)]),
    _e("chevalet", "Chevalet « Réservé »", "“Reserved” sign", "resto",
       _f("pro_resto", "chevalet"), texte="optionnel",
       params=[_P("largeur", "Largeur", "Width", 60, 140, 95, 5),
               _P("hauteur", "Hauteur", "Height", 35, 90, 55, 5),
               _P("taille_police", "Taille du texte (0 = auto)", "Text size (0 = auto)", 0, 40, 0, 1)]),
    _e("porte_menu", "Porte-menu (fente)", "Menu holder (slot)", "resto",
       _f("pro_resto", "porte_menu"),
       params=[_P("largeur", "Largeur", "Width", 70, 160, 100, 5),
               _P("hauteur", "Hauteur", "Height", 30, 70, 45, 5),
               _P("epaisseur_fente", "Largeur de la fente", "Slot width", 3, 14, 6, 0.5)]),
    _e("porte_addition", "Porte-addition (plateau)", "Bill tray", "resto",
       _f("pro_resto", "porte_addition"),
       params=[_P("largeur", "Largeur", "Width", 90, 200, 130, 5),
               _P("hauteur", "Longueur", "Length", 60, 160, 90, 5),
               _P("rebord", "Rebord", "Rim", 3, 15, 6, 1)]),
    _e("porte_couverts", "Bac à couverts", "Cutlery caddy", "resto",
       _f("pro_resto", "porte_couverts"),
       params=[_P("longueur", "Longueur", "Length", 120, 250, 180, 10),
               _P("largeur", "Largeur", "Width", 40, 120, 55, 5),
               _P("hauteur", "Hauteur", "Height", 30, 70, 45, 5),
               _P("colonnes", "Cases en longueur", "Columns", 1, 8, 2, 1),
               _P("rangees", "Cases en largeur", "Rows", 1, 4, 1, 1)]),

    # ── Mariage & événementiel ──
    _e("porte_alliances", "Porte-alliances (cœur)", "Ring holder (heart)", "mariage",
       _f("pro_mariage", "porte_alliances"),
       params=[_P("taille", "Taille", "Size", 55, 120, 80, 5),
               _P("ep", "Épaisseur socle", "Base thickness", 5, 12, 7, 1)]),
    _e("panneau_bienvenue", "Panneau bienvenue", "Welcome sign", "mariage",
       _f("pro_mariage", "panneau_bienvenue"), texte="optionnel",
       params=[_P("largeur", "Largeur", "Width", 90, 200, 130, 5),
               _P("hauteur", "Hauteur", "Height", 45, 110, 75, 5)],
       flags=[("grave", "Texte gravé", "Engraved text", False)]),
    _e("cone_petales", "Cornet à pétales", "Petal cone", "mariage",
       _f("pro_mariage", "cone_petales"),
       params=[_P("d_haut", "Ø haut", "Top ø", 50, 100, 70, 5),
               _P("d_bas", "Ø bas", "Bottom ø", 15, 35, 22, 1),
               _P("hauteur", "Hauteur", "Height", 70, 140, 95, 5)]),
    _e("coeur_marque_place", "Marque-place cœur", "Heart place card", "mariage",
       _f("pro_mariage", "coeur_marque_place"), texte="optionnel",
       params=[_P("taille", "Taille", "Size", 40, 90, 55, 5)],
       flags=[("grave", "Texte gravé", "Engraved text", False)]),
    _e("support_plan_table", "Support plan de table", "Seating chart holder",
       "mariage", _f("pro_mariage", "support_plan_table"),
       params=[_P("largeur", "Largeur", "Width", 100, 220, 150, 10),
               _P("hauteur", "Hauteur", "Height", 40, 80, 55, 5),
               _P("ep_fente", "Largeur fente", "Slot width", 4, 12, 7, 1)]),

    # ── Boutique & bureau pro ──
    _e("presentoir_gradins", "Présentoir à gradins", "Stepped display", "commerce",
       _f("pro_boutique", "presentoir_gradins"),
       params=[_P("largeur", "Largeur", "Width", 90, 220, 140, 10),
               _P("marches", "Marches", "Steps", 2, 5, 3, 1),
               _P("prof_marche", "Profondeur marche", "Step depth", 30, 60, 42, 2),
               _P("h_marche", "Hauteur marche", "Step height", 20, 45, 30, 2)]),
    _e("serre_livres", "Serre-livres", "Bookend", "commerce",
       _f("pro_boutique", "serre_livres"),
       params=[_P("hauteur", "Hauteur", "Height", 90, 200, 140, 10),
               _P("base", "Longueur semelle", "Base length", 80, 160, 120, 5),
               _P("largeur", "Largeur", "Width", 70, 140, 100, 5)]),
    _e("presentoir_bijoux", "Présentoir à bijoux", "Jewelry stand", "commerce",
       _f("pro_boutique", "presentoir_bijoux"),
       params=[_P("largeur", "Largeur", "Width", 80, 180, 120, 10),
               _P("hauteur", "Hauteur", "Height", 90, 180, 130, 10),
               _P("section", "Section barre", "Bar section", 8, 20, 12, 1)]),
    _e("organiseur_bureau", "Organiseur de bureau", "Desk organizer", "commerce",
       _f("pro_boutique", "organiseur_bureau"),
       params=[_P("longueur", "Longueur", "Length", 120, 240, 170, 10),
               _P("largeur", "Largeur", "Width", 60, 130, 90, 5),
               _P("hauteur", "Hauteur", "Height", 40, 80, 55, 5)]),
]

# ── Cohérence du TEXTE sur les objets (AUTO-injecté) ────────────────────────
# Objets dont le texte EST l'objet lui-même (chiffres / lettres 3D dressés) :
# ni « hauteur du texte » ni menu relief/gravé/lisse n'ont de sens → on les
# purge de tout réglage de texte stylisé.
_TEXTE_EST_OBJET = {"numero_table", "lettre_3d", "numero_maison"}
# Objets à texte-SUR-SURFACE convertis au bicolore + menu relief/gravé/lisse.
# (cadre_photo = 2 corps mécaniques, coeur_marque_place = post-fusion, sous_verre =
#  gravé fonctionnel pour la pose du verre → restent hors menu pour l'instant.)
_BICOLORE_STYLE = {
    "porte_cle", "badge", "plaque", "magnet", "chevalet", "etiquette_plante",
    "marque_page", "ornement_etoile", "coeur_deco", "trophee", "jeton",
    "socle_figurine", "tire_fermeture", "panneau_bienvenue",
    "coeur_marque_place",
}
_STYLE_CHOIX = ("style", "Texte", "Text",
                [("relief", "En relief", "Raised"),
                 ("grave", "Gravé", "Engraved"),
                 ("lisse", "Lisse", "Flush")], "relief")
_COULEURS_TEXTE = [("objet", "Couleur objet", "Object color", "#3B82F6"),
                   ("texte", "Couleur texte", "Text color", "#FFFFFF")]
# Bicolore SANS menu de style (le style est imposé par la fonction : sous-verre =
# toujours gravé pour garder une surface plane sous le verre).
_BICOLORE_COULEUR_SEULE = {"sousverre", "rond_serviette", "gobelet"}
for _e_txt in CATALOGUE:
    if _e_txt["texte"] in ("aucun", "lien"):
        continue
    if _e_txt["id"] in _TEXTE_EST_OBJET:
        # purge : pas de hauteur de relief, pas de flag gravé (le chiffre EST l'objet)
        _e_txt["params"] = [pp for pp in _e_txt["params"]
                            if pp[0] not in ("relief", "ep_texte")]
        _e_txt["flags"] = [f for f in _e_txt["flags"] if f[0] != "grave"]
        continue
    # « Hauteur du texte » (relief) OU « Profondeur » (gravé) — le libellé exact est
    # piloté par le menu de style dans le formulaire ; un SEUL paramètre, un seul nom.
    if not any(pp[0] in ("relief", "ep_texte") for pp in _e_txt["params"]):
        _e_txt["params"].append(
            _P("relief", "Hauteur du texte", "Text height", 0.3, 4.0, 1.2, 0.1))
    if _e_txt["id"] in _BICOLORE_STYLE:
        # menu relief/gravé/lisse + 2 couleurs ; retire la case « gravé » (doublon)
        _e_txt["flags"] = [f for f in _e_txt["flags"] if f[0] != "grave"]
        if not any(c[0] == "style" for c in _e_txt["choix"]):
            _e_txt["choix"].append(_STYLE_CHOIX)
        if not _e_txt["couleurs"]:
            _e_txt["couleurs"] = list(_COULEURS_TEXTE)
    elif _e_txt["id"] in _BICOLORE_COULEUR_SEULE:
        # 2 couleurs sans menu de style (style imposé par la fonction)
        _e_txt["flags"] = [f for f in _e_txt["flags"] if f[0] != "grave"]
        if not _e_txt["couleurs"]:
            _e_txt["couleurs"] = list(_COULEURS_TEXTE)

# ── Objets AJOUTÉS/CORRIGÉS PAR MISE À JOUR (sans rebuild) ──────────────────
# Chargés depuis la base téléchargeable ~/.neoslice/neogen/objets_extra.json
# (voir objets_module.py + maj.py). Un objet de même id REMPLACE le natif ;
# sinon il s'ajoute. On garde une PHOTO des objets natifs pour pouvoir recharger
# à chaud après « Mettre à jour la base », sans redémarrer.
_CATALOGUE_NATIF = list(CATALOGUE)
_SYNO_MODULE: dict[str, str] = {}


def _fusionner_objets_module() -> None:
    """(Re)fusionne les objets de la base téléchargeable sur les objets natifs."""
    _SYNO_MODULE.clear()
    CATALOGUE[:] = list(_CATALOGUE_NATIF)
    try:
        from core.neogen.objets_module import entrees_catalogue as _dl
        objs = _dl()
    except Exception:
        objs = []
    for _obj in objs:
        _idx = next((k for k, e in enumerate(CATALOGUE) if e["id"] == _obj["id"]), None)
        if _idx is not None:
            CATALOGUE[_idx] = _obj                 # corrige un objet natif
        else:
            CATALOGUE.append(_obj)                 # nouvel objet
        if _obj.get("_synonymes"):
            _SYNO_MODULE[_obj["id"]] = _obj["_synonymes"]


_fusionner_objets_module()

# Index rapide par id
PAR_ID = {e["id"]: e for e in CATALOGUE}


# ═════════════════ Recherche en langage naturel -> objet biblio ═════════════
# Mots-clés supplémentaires (synonymes, usages) par id : une demande libre
# tombe ainsi sur l'objet le plus proche de la BIBLIOTHÈQUE (l'intelligence est
# ici, dans des objets validés, pas dans un modèle qui génère du code).
_SYNONYMES: dict[str, str] = {
    "qrcode": "qr code flashcode flash lien url site menu restaurant carte wifi "
              "scanner scan contact vcard adresse",
    "porte_cle": "porteclef breloque trousseau cles initiale prenom",
    "badge": "medaille pin pins insigne broche",
    "plaque": "panneau ecriteau enseigne pancarte porte nom",
    "magnet": "aimant frigo frigidaire souvenir",
    "sousverre": "dessous verre tasse mug rond bol boisson",
    "logo": "logotype marque embleme image dessin",
    "photo_relief": "photo lithophanie litho image relief portrait cadre lumineux",
    "vase": "fleurs bouquet soliflore",
    "boite": "rangement boitier coffret couvercle contenant",
    "support": "telephone smartphone portable chevalet stand dock",
    "de": "des jouer jeu societe",
    "marque_page": "marquepage livre lecture signet",
    "tire_fermeture": "tirette zip fermeture eclair curseur",
    "coquetier": "oeuf coque petit dejeuner",
    "gobelet": "verre tasse pot brosses dents",
    "entonnoir": "verser transvaser liquide",
    "pot_crayons": "crayons stylos pot gobelet",
    "pot_fleur": "plante fleur jardiniere cache pot",
    "lettre_3d": "lettre initiale alphabet caractere",
    "numero_maison": "numero maison porte adresse rue boite lettres",
    "vis": "visserie boulon filetage fixation",
    "ecrou": "visserie boulon filetage",
    "crochet_mural": "crochet accroche mur porte manteau patere",
    "poignee_meuble": "poignee meuble tiroir placard porte",
    "equerre": "equerre fixation angle support etagere",
    "joint": "joint etancheite plat torique oring o-ring rondelle caoutchouc bague",
    "cadre_photo": "cadre photo portrait souvenir",
    "porte_savon": "savon salle bain douche",
    "dessous_de_plat": "dessous plat chaud cuisine table",
    "bac_empilable": "bac empilable rangement caisse bin",
    "passe_cable": "passe cable bureau trou gestion cables",
    "etiquette_plante": "etiquette plante jardin semis potager nom",
    "ornement_etoile": "etoile noel sapin decoration suspension",
    "coeur_deco": "coeur amour saint valentin decoration cadeau",
    "trophee": "trophee coupe recompense champion prix",
    "regle": "regle graduation mesure centimetre",
    "rond_serviette": "rond serviette table anneau",
    "repose_cuillere": "repose cuillere cuisine louche",
    "range_cable": "range cable bobine enrouleur",
    # restauration
    "numero_table": "numero table restaurant chiffre pied",
    "chevalet": "chevalet reserve reserved tente pancarte panneau menu jour ardoise",
    "porte_menu": "porte menu carte support fente restaurant",
    "porte_addition": "porte addition note ticket presentoir cheque paiement restaurant",
    "porte_couverts": "bac couverts serviettes caisson compartiment restaurant table",
    # mariage & événementiel
    "porte_alliances": "porte alliances bagues anneaux mariage coussin coeur ceremonie",
    "panneau_bienvenue": "panneau bienvenue welcome accueil entree mariage evenement pancarte",
    "cone_petales": "cornet cone petales riz confettis mariage sortie eglise",
    "coeur_marque_place": "marque place coeur nom invite mariage etiquette cadeau merci",
    "support_plan_table": "plan table seating chart support panneau ardoise mariage menu",
    # boutique & bureau pro
    "presentoir_gradins": "presentoir gradins escalier marches produits boutique vitrine etale",
    "serre_livres": "serre livres bookend etagere bureau bibliotheque",
    "presentoir_bijoux": "presentoir bijoux colliers bracelets boucles arche portique boutique",
    "organiseur_bureau": "organiseur bureau rangement stylos crayons trombones bac compartiment",
    "porte_cartes": "porte cartes visite presentoir comptoir boutique accueil",
}
# index normalisé id -> ensemble de mots-clés (nom FR + EN + synonymes)
_INDEX_RECHERCHE: dict[str, set] = {}


def _mots_norm(txt: str) -> set:
    import re
    import unicodedata
    t = unicodedata.normalize("NFKD", txt.lower()).encode("ascii", "ignore").decode()
    return set(re.findall(r"[a-z0-9]+", t)) - {
        "un", "une", "de", "des", "du", "le", "la", "les", "avec", "et", "en",
        "mm", "cm", "pour", "sur", "the", "a", "an", "with", "of", "je", "veux",
        "faire", "creer", "genere", "generer", "voudrais", "aimerais"}


def _construire_index() -> None:
    for e in CATALOGUE:
        # synonymes : table native, complétée par ceux des objets de la base
        # téléchargeable (_SYNO_MODULE) — la recherche trouve donc aussi ces objets.
        syn = _SYNONYMES.get(e["id"], "") + " " + _SYNO_MODULE.get(e["id"], "")
        mots = _mots_norm(e["fr"]) | _mots_norm(e["en"]) | _mots_norm(syn)
        _INDEX_RECHERCHE[e["id"]] = mots


_construire_index()


def recharger_objets_module() -> int:
    """Recharge à CHAUD les objets de la base téléchargeable (après « Mettre à
    jour la base ») SANS redémarrer : re-fusionne sur les natifs et reconstruit
    tous les index. Renvoie le nombre d'objets issus d'une mise à jour."""
    global PAR_ID
    _fusionner_objets_module()
    PAR_ID = {e["id"]: e for e in CATALOGUE}
    _INDEX_RECHERCHE.clear()
    _construire_index()
    return sum(1 for e in CATALOGUE if e.get("_module"))


def rechercher(phrase: str) -> str | None:
    """Objet de bibliothèque le plus proche d'une demande en langage naturel
    (recouvrement de mots-clés, SANS modèle -> instantané et fiable). Renvoie
    l'id, ou None si rien de pertinent (score nul)."""
    mots = _mots_norm(phrase or "")
    if not mots:
        return None
    best_id, best_score = None, 0
    for eid, cles in _INDEX_RECHERCHE.items():
        score = len(mots & cles)
        if score > best_score:
            best_id, best_score = eid, score
    return best_id


def par_domaine() -> list[tuple[tuple, list[dict]]]:
    """[(domaine (id, fr, en), [entrées...]), ...] dans l'ordre d'affichage.

    Domaines NATIFS + domaines définis par la base téléchargée (nouvelle CATÉGORIE
    sans rebuild). On n'affiche qu'un domaine ayant au moins un objet."""
    doms = list(DOMAINES)
    ids = {d[0] for d in doms}
    try:
        from core.neogen import objets_module
        for dm in objets_module.domaines_module():
            if dm["id"] not in ids:
                doms.append((dm["id"], dm.get("fr", dm["id"]), dm.get("en", dm["id"])))
                ids.add(dm["id"])
    except Exception:
        pass
    out = []
    for d in doms:
        entrees = [e for e in CATALOGUE if e["domaine"] == d[0]]
        if entrees:
            out.append((d, entrees))
    return out


def construire(entree_id: str, params: dict):
    """Construit l'objet du catalogue avec des paramètres BORNÉS au schéma."""
    e = PAR_ID[entree_id]
    p = {}
    for (pid, _fr, _en, mini, maxi, defaut, _pas) in e["params"]:
        try:
            p[pid] = min(maxi, max(mini, float(params.get(pid, defaut))))
        except (TypeError, ValueError):
            p[pid] = defaut
    for (fid, _fr, _en, defaut) in e["flags"]:
        p[fid] = bool(params.get(fid, defaut))
    for (cid, _fr, _en, options, defaut) in e["choix"]:
        val = params.get(cid, defaut)
        p[cid] = val if any(val == o[0] for o in options) else defaut
    for (cid, _fr, _en, hexd) in e.get("couleurs", []):     # couleur_<id> (bicolore)
        v = params.get(f"couleur_{cid}", hexd)
        p[f"couleur_{cid}"] = str(v) if v else hexd
    if e["texte"] != "aucun":
        # mode « lien » (URL, ex. QR) : requis + limite plus haute (pas 40 car.)
        _is_lien = (e["texte"] == "lien")
        _maxlen = 512 if _is_lien else 40
        t = str(params.get("texte", "") or "").strip()[:_maxlen]
        if e["texte"] in ("requis", "lien") and not t:
            raise ValueError("texte requis")
        p["texte"] = t
        if params.get("police"):
            p["police"] = str(params["police"])
        if "grave" in params and not any(f[0] == "grave" for f in e["flags"]):
            p["grave"] = bool(params.get("grave"))
        # relief/gravure : le paramètre est nommé « relief » dans les schémas
        if params.get("relief") is not None:
            try:
                p["relief"] = min(4.0, max(0.3, float(params["relief"])))
            except (TypeError, ValueError):
                pass
    if e["image"]:
        p["image"] = params.get("image")
        if not p["image"]:
            raise ValueError("image requise")
    # « De session » : atteignent TOUS les générateurs à texte (même ceux sans
    # paramètre dans leur signature — coquetier, trophée...). Police + hauteur
    # de relief / profondeur de gravure.
    from core.neogen import goodies as _g
    _g.POLICE_ACTIVE = p.get("police")
    _g.RELIEF_ACTIF = p.get("relief") if e["texte"] != "aucun" else None
    _g.ESPACEMENT_ACTIF = None
    if e["texte"] != "aucun" and params.get("espacement") is not None:
        try:
            _g.ESPACEMENT_ACTIF = max(0.0, float(params["espacement"]))
        except (TypeError, ValueError):
            pass
    try:
        return e["construire"](p)
    finally:
        _g.POLICE_ACTIVE = None
        _g.RELIEF_ACTIF = None
        _g.ESPACEMENT_ACTIF = None


def est_multicouleur(piece) -> bool:
    """True si `piece` est une Scene à ≥2 corps de couleurs de face DISTINCTES
    (objet bicolore : QR, texte objet+texte…) → route multicouleur (2 slots à
    l'export, aperçu des couleurs dans la fenêtre d'export)."""
    import trimesh
    if not isinstance(piece, trimesh.Scene) or len(piece.geometry) < 2:
        return False
    cols = set()
    for g in piece.geometry.values():
        try:
            cols.add(tuple(int(x) for x in g.visual.face_colors[0][:3]))
        except Exception:
            pass
    return len(cols) >= 2


def generer_fichier(entree_id: str, params: dict, piece=None):
    """Construit et exporte vers ~/.neoslice/neogen/. Renvoie le Path a charger.
    `piece` : géométrie déjà construite (évite de reconstruire) — optionnel."""
    import trimesh
    from core.neogen.pilote import DOSSIER_SORTIES, _slug
    if piece is None:
        piece = construire(entree_id, params)
    DOSSIER_SORTIES.mkdir(parents=True, exist_ok=True)
    suffixe = _slug(str(params.get("texte", "")))[:20]
    nom = entree_id
    if entree_id == "photo_relief" and \
            str(params.get("mode", "lithophanie")) == "lithophanie":
        # nom dédié : l'app reconnaît une LITHOPHANIE au chargement et applique
        # son profil d'impression automatique (remplissage 100 %, couche fine…)
        nom = "lithophanie"
    base = DOSSIER_SORTIES / (nom + ("_" + suffixe if suffixe and suffixe != "piece" else ""))
    fusion = (trimesh.util.concatenate(list(piece.geometry.values()))
              if isinstance(piece, trimesh.Scene) else piece)
    fusion.export(base.with_suffix(".stl"))
    try:
        piece.export(base.with_suffix(".3mf"))
        return base.with_suffix(".3mf")
    except Exception:
        return base.with_suffix(".stl")


def polices_disponibles() -> list[str]:
    """Familles de polices installées (via matplotlib, celles que TextPath
    sait réellement vectoriser). Triées, dédupliquées."""
    try:
        from matplotlib import font_manager
        familles = sorted({f.name for f in font_manager.fontManager.ttflist
                           if not f.name.startswith(".")})
        return familles
    except Exception:
        return ["Arial", "Arial Black", "Segoe UI"]
