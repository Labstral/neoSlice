#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
neoForge : modeleur 3D parametrique pilote a la manette.
Concu pour un ecran de 640x480 et une console type Anbernic RG353V.

Dependances :
    pip install pygame-ce PyOpenGL manifold3d

Lancement :
    python3 neoforge.py                 # fenetre 640x480
    python3 neoforge.py --plein-ecran   # plein ecran (console)
    python3 neoforge.py --boutons       # affiche l'index des boutons de ta manette
    python3 neoforge.py --autotest      # verifie geometrie, export et sauvegarde, sans fenetre

Les projets sont dans ./projets, les exports dans ./export.
"""

import os
import sys
import json
import math
import time
import ctypes
import struct
import traceback
import zipfile
import datetime

VERSION = "1.1"
RACINE = os.path.dirname(os.path.abspath(__file__))
DOSSIER_PROJETS = os.path.join(RACINE, "projets")
DOSSIER_EXPORT = os.path.join(RACINE, "export")

LARGEUR, HAUTEUR = 640, 480
PLATEAU = 256.0          # plateau de reference, en mm
SEGMENTS = 48            # facettes des formes rondes

# ---------------------------------------------------------------- modele

CUBE, SPHERE, CYLINDRE, CONE = 0, 1, 2, 3
NOMS_FORMES = ["CUBE", "SPHÈRE", "CYLINDRE", "CÔNE"]

UNION, SOUSTRAIT, INTERSECT = 0, 1, 2
NOMS_OPS = ["AJOUTER", "CREUSER", "INTERSECTION"]
SIGNES_OPS = ["+", "-", "x"]

DEPLACER, TAILLE, PIVOTER = 0, 1, 2
NOMS_MODES = ["DÉPLACER", "TAILLE", "PIVOTER"]


class Primitive:
    """Une forme elementaire et son operation booleenne."""

    def __init__(self, forme=CUBE, op=UNION, pos=None, dim=None, rot=None):
        self.forme = forme
        self.op = op
        self.pos = list(pos) if pos else [0.0, 0.0, 10.0]
        self.dim = list(dim) if dim else [20.0, 20.0, 20.0]
        self.rot = list(rot) if rot else [0.0, 0.0, 0.0]

    def copie(self):
        return Primitive(self.forme, self.op, self.pos, self.dim, self.rot)

    def dico(self):
        return {"forme": self.forme, "op": self.op,
                "pos": self.pos, "dim": self.dim, "rot": self.rot}

    @staticmethod
    def depuis_dico(d):
        return Primitive(d.get("forme", CUBE), d.get("op", UNION),
                         d.get("pos"), d.get("dim"), d.get("rot"))

    def noms_dimensions(self):
        if self.forme == CUBE:
            return ["LARGEUR X", "PROFONDEUR Y", "HAUTEUR Z"]
        if self.forme == SPHERE:
            return ["DIAMÈTRE", None, None]
        if self.forme == CYLINDRE:
            return ["DIAMÈTRE", None, "HAUTEUR Z"]
        return ["DIAM. BAS", "DIAM. HAUT", "HAUTEUR Z"]

    def resume_dimensions(self):
        d = self.dim
        if self.forme == CUBE:
            return "%g x %g x %g" % (d[0], d[1], d[2])
        if self.forme == SPHERE:
            return "diam. %g" % d[0]
        if self.forme == CYLINDRE:
            return "diam. %g  h %g" % (d[0], d[2])
        if d[1] <= 0.05:
            return "base %g  h %g" % (d[0], d[2])
        return "%g vers %g  h %g" % (d[0], d[1], d[2])

    def demi_etendue(self):
        """Demi dimensions de la boite englobante, avant rotation."""
        d = self.dim
        if self.forme == CUBE:
            return [d[0] / 2.0, d[1] / 2.0, d[2] / 2.0]
        if self.forme == SPHERE:
            r = d[0] / 2.0
            return [r, r, r]
        if self.forme == CYLINDRE:
            return [d[0] / 2.0, d[0] / 2.0, d[2] / 2.0]
        r = max(d[0], d[1]) / 2.0
        return [r, r, d[2] / 2.0]

    def coins(self):
        """Les huit sommets de la boite englobante, apres rotation."""
        ex, ey, ez = self.demi_etendue()
        cr = [math.radians(a) for a in self.rot]
        cx, sx = math.cos(cr[0]), math.sin(cr[0])
        cy, sy = math.cos(cr[1]), math.sin(cr[1])
        cz, sz = math.cos(cr[2]), math.sin(cr[2])
        out = []
        for i in range(8):
            x = ex if i & 1 else -ex
            y = ey if i & 2 else -ey
            z = ez if i & 4 else -ez
            y, z = y * cx - z * sx, y * sx + z * cx
            x, z = x * cy + z * sy, -x * sy + z * cy
            x, y = x * cz - y * sz, x * sz + y * cz
            out.append((x + self.pos[0], y + self.pos[1], z + self.pos[2]))
        return out

    def boite(self):
        c = self.coins()
        mini = [min(p[i] for p in c) for i in range(3)]
        maxi = [max(p[i] for p in c) for i in range(3)]
        return mini, maxi

    def solide(self, mf):
        """Construit le solide manifold correspondant."""
        d = [max(0.01, v) for v in self.dim]
        if self.forme == CUBE:
            s = mf.Manifold.cube([d[0], d[1], d[2]], True)
        elif self.forme == SPHERE:
            s = mf.Manifold.sphere(d[0] / 2.0, SEGMENTS)
        elif self.forme == CYLINDRE:
            s = mf.Manifold.cylinder(d[2], d[0] / 2.0, d[0] / 2.0, SEGMENTS, True)
        else:
            s = mf.Manifold.cylinder(d[2], d[0] / 2.0, d[1] / 2.0, SEGMENTS, True)
        if any(self.rot):
            s = s.rotate([self.rot[0], self.rot[1], self.rot[2]])
        return s.translate([self.pos[0], self.pos[1], self.pos[2]])


class Projet:
    def __init__(self):
        self.nom = ""
        self.prims = []
        self.sel = 0
        self.nouveau()

    def nouveau(self):
        self.nom = ""
        self.prims = [Primitive(CUBE, UNION, [0, 0, 15], [30, 30, 30])]
        self.sel = 0

    def exemple(self):
        """Une platine percee, pour avoir quelque chose a l'ecran des l'ouverture."""
        self.nom = ""
        self.prims = [
            Primitive(CUBE, UNION, [0, 0, 5], [80, 50, 10]),
            Primitive(CYLINDRE, SOUSTRAIT, [-30, -16, 5], [8, 8, 30]),
            Primitive(CYLINDRE, SOUSTRAIT, [30, -16, 5], [8, 8, 30]),
            Primitive(CUBE, UNION, [0, 12, 16], [30, 20, 12]),
        ]
        self.sel = 3

    def courante(self):
        if not self.prims:
            return None
        self.sel = max(0, min(self.sel, len(self.prims) - 1))
        return self.prims[self.sel]

    def dico(self):
        return {"neoforge": VERSION, "nom": self.nom,
                "primitives": [p.dico() for p in self.prims]}

    def charger_dico(self, d):
        self.prims = [Primitive.depuis_dico(x) for x in d.get("primitives", [])]
        if not self.prims:
            self.prims = [Primitive()]
        self.nom = d.get("nom", "")
        self.sel = 0


# ---------------------------------------------------------------- geometrie

def construire(projet):
    """Empile les primitives et renvoie le solide final."""
    import manifold3d as mf
    resultat = None
    for p in projet.prims:
        s = p.solide(mf)
        if resultat is None:
            resultat = s
            continue
        if p.op == UNION:
            resultat = resultat + s
        elif p.op == SOUSTRAIT:
            resultat = resultat - s
        else:
            resultat = resultat ^ s
    return resultat


def triangles(solide):
    """Renvoie la liste des triangles (sommets) du solide."""
    if solide is None:
        return []
    m = solide.to_mesh()
    vp = m.vert_properties
    tv = m.tri_verts
    n = vp.shape[1]
    tris = []
    for t in tv:
        a = vp[t[0]][:3]
        b = vp[t[1]][:3]
        c = vp[t[2]][:3]
        tris.append(((float(a[0]), float(a[1]), float(a[2])),
                     (float(b[0]), float(b[1]), float(b[2])),
                     (float(c[0]), float(c[1]), float(c[2]))))
    del n
    return tris


def normale(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    lg = math.sqrt(nx * nx + ny * ny + nz * nz)
    if lg < 1e-12:
        return (0.0, 0.0, 1.0)
    return (nx / lg, ny / lg, nz / lg)


# ---------------------------------------------------------------- export

def exporter_stl(tris, chemin):
    """STL binaire."""
    with open(chemin, "wb") as f:
        entete = ("neoForge %s  %s" % (VERSION, datetime.date.today().isoformat()))
        f.write(entete.encode("ascii", "replace").ljust(80, b"\0")[:80])
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            nx, ny, nz = normale(a, b, c)
            f.write(struct.pack("<12fH", nx, ny, nz,
                                a[0], a[1], a[2],
                                b[0], b[1], b[2],
                                c[0], c[1], c[2], 0))
    return chemin


TYPES_3MF = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>"""

RELS_3MF = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>"""


def exporter_3mf(tris, chemin):
    """3MF minimal conforme au coeur de la specification."""
    sommets = {}
    ordre = []
    faces = []
    for tri in tris:
        idx = []
        for s in tri:
            cle = (round(s[0], 5), round(s[1], 5), round(s[2], 5))
            if cle not in sommets:
                sommets[cle] = len(ordre)
                ordre.append(cle)
            idx.append(sommets[cle])
        faces.append(idx)

    out = []
    out.append('<?xml version="1.0" encoding="UTF-8"?>')
    out.append('<model unit="millimeter" xml:lang="en-US" '
               'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">')
    out.append('<metadata name="Application">neoForge %s</metadata>' % VERSION)
    out.append('<resources><object id="1" type="model"><mesh><vertices>')
    for v in ordre:
        out.append('<vertex x="%.5f" y="%.5f" z="%.5f"/>' % v)
    out.append('</vertices><triangles>')
    for f in faces:
        out.append('<triangle v1="%d" v2="%d" v3="%d"/>' % (f[0], f[1], f[2]))
    out.append('</triangles></mesh></object></resources>')
    out.append('<build><item objectid="1"/></build></model>')
    modele = "\n".join(out)

    with zipfile.ZipFile(chemin, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", TYPES_3MF)
        z.writestr("_rels/.rels", RELS_3MF)
        z.writestr("3D/3dmodel.model", modele)
    return chemin


# ---------------------------------------------------------------- fichiers

def assurer_dossiers():
    for d in (DOSSIER_PROJETS, DOSSIER_EXPORT):
        if not os.path.isdir(d):
            os.makedirs(d)


def nom_libre(dossier, base, ext):
    i = 1
    while True:
        nom = "%s_%03d%s" % (base, i, ext)
        if not os.path.exists(os.path.join(dossier, nom)):
            return nom
        i += 1


def sauver_projet(projet):
    assurer_dossiers()
    if not projet.nom:
        projet.nom = nom_libre(DOSSIER_PROJETS, "piece", ".nfg")
    chemin = os.path.join(DOSSIER_PROJETS, projet.nom)
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(projet.dico(), f, indent=1)
    return chemin


def lister_projets():
    assurer_dossiers()
    noms = [n for n in os.listdir(DOSSIER_PROJETS) if n.lower().endswith(".nfg")]
    noms.sort()
    return noms


def charger_projet(projet, nom):
    chemin = os.path.join(DOSSIER_PROJETS, nom)
    with open(chemin, "r", encoding="utf-8") as f:
        d = json.load(f)
    projet.charger_dico(d)
    projet.nom = nom
    return chemin


# ---------------------------------------------------------------- partage reseau

PARTAGE = {"serveur": None, "port": 0, "ip": ""}


def adresse_locale():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = ""
    finally:
        s.close()
    return ip


def chemin_windows(ip):
    """Le partage samba de la console expose /userdata sous le nom share."""
    if not ip or not RACINE.startswith("/userdata"):
        return ""
    reste = RACINE[len("/userdata"):].strip("/")
    queue = ("\\" + reste.replace("/", "\\")) if reste else ""
    return "\\\\%s\\share%s\\export" % (ip, queue)


PAGE_HTML = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>neoForge, fichiers exportes</title><style>
body{background:#141319;color:#ebe8f1;font:15px/1.6 system-ui,sans-serif;
margin:0;padding:28px 20px;}
h1{font-size:1.3rem;margin:0 0 4px;color:#b992e0;}
p.s{color:#8b849b;margin:0 0 22px;font-size:.9rem;}
a{display:flex;justify-content:space-between;gap:16px;padding:12px 14px;
margin-bottom:8px;background:#1c1a23;border:1px solid #302c3b;border-radius:6px;
color:#ebe8f1;text-decoration:none;}
a:hover{border-color:#b992e0;}
span{color:#8b849b;font-size:.85rem;white-space:nowrap;}
.v{color:#8b849b;padding:14px;border:1px dashed #302c3b;border-radius:6px;}
</style></head><body><h1>neoForge</h1>
<p class="s">Fichiers exportes par la console. Clique pour telecharger.</p>
%s</body></html>"""


def demarrer_partage():
    """Sert le dossier d export en HTTP. Renvoie (ip, port) ou (ip, 0)."""
    if PARTAGE["serveur"] is not None:
        PARTAGE["ip"] = adresse_locale()
        return PARTAGE["ip"], PARTAGE["port"]

    import http.server
    import threading
    import html as _html

    dossier = DOSSIER_EXPORT
    assurer_dossiers()

    class Poignee(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=dossier, **k)

        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                lignes = []
                try:
                    noms = sorted(os.listdir(dossier))
                except OSError:
                    noms = []
                for n in noms:
                    c = os.path.join(dossier, n)
                    if not os.path.isfile(c):
                        continue
                    ko = os.path.getsize(c) / 1024.0
                    taille = "%.0f Ko" % ko if ko < 1024 else "%.1f Mo" % (ko / 1024)
                    lignes.append('<a href="%s" download><b>%s</b><span>%s</span></a>'
                                  % (_html.escape(n), _html.escape(n), taille))
                if not lignes:
                    lignes = ['<div class="v">Aucun fichier exporte pour le moment.</div>']
                corps = (PAGE_HTML % "\n".join(lignes)).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                self.wfile.write(corps)
                return
            super().do_GET()

    for port in range(8080, 8086):
        try:
            srv = http.server.ThreadingHTTPServer(("", port), Poignee)
        except OSError:
            continue
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        PARTAGE["serveur"] = srv
        PARTAGE["port"] = port
        PARTAGE["ip"] = adresse_locale()
        return PARTAGE["ip"], port
    PARTAGE["ip"] = adresse_locale()
    return PARTAGE["ip"], 0


def lister_exports():
    assurer_dossiers()
    out = []
    for n in sorted(os.listdir(DOSSIER_EXPORT)):
        c = os.path.join(DOSSIER_EXPORT, n)
        if os.path.isfile(c):
            out.append((n, os.path.getsize(c), os.path.getmtime(c)))
    out.sort(key=lambda e: e[2], reverse=True)
    return out


def taille_lisible(o):
    ko = o / 1024.0
    return "%.0f Ko" % ko if ko < 1024 else "%.1f Mo" % (ko / 1024.0)


# ---------------------------------------------------------------- manette

FICHIER_MANETTE = os.path.join(RACINE, "manette.json")
TEMOIN_ACCUEIL = os.path.join(RACINE, ".accueil-vu")
FICHIER_REGLAGES = os.path.join(RACINE, "reglages.json")

REGLAGES = {"collage": True}


def charger_reglages():
    if os.path.exists(FICHIER_REGLAGES):
        try:
            with open(FICHIER_REGLAGES, "r", encoding="utf-8") as fic:
                REGLAGES.update(json.load(fic))
        except Exception as err:
            print("reglages.json illisible :", err)
    return REGLAGES


def sauver_reglages():
    try:
        with open(FICHIER_REGLAGES, "w", encoding="utf-8") as fic:
            json.dump(REGLAGES, fic, indent=1)
    except Exception as err:
        print("reglages non enregistres :", err)


def limiter(piece, index, prims, axe, delta, force=False):
    """Arrete la piece a fleur des autres pieces de matiere et du plateau."""
    if delta == 0.0:
        return delta
    if not force and not REGLAGES.get("collage", True):
        return delta
    if index > 0 and piece.op != UNION:
        return delta                      # un creux traverse tout, c est son role

    mini, maxi = piece.boite()
    d = delta
    for i, autre in enumerate(prims):
        if i == index:
            continue
        if i > 0 and autre.op != UNION:
            continue                      # on ne se colle pas a un creux
        ami, ama = autre.boite()
        touche = True
        for k in range(3):
            if k == axe:
                continue
            if min(maxi[k], ama[k]) - max(mini[k], ami[k]) <= 0.01:
                touche = False
                break
        if not touche:
            continue
        if d > 0 and maxi[axe] <= ami[axe] + 0.001:
            d = min(d, ami[axe] - maxi[axe])
        elif d < 0 and mini[axe] >= ama[axe] - 0.001:
            d = max(d, ama[axe] - mini[axe])

    if axe == 2 and d < 0 and mini[2] >= -0.001:
        d = max(d, -mini[2])
    return d

COMMANDES = [
    ("haut", "CROIX HAUT"), ("bas", "CROIX BAS"),
    ("gauche", "CROIX GAUCHE"), ("droite", "CROIX DROITE"),
    ("a", "BOUTON A"), ("b", "BOUTON B"),
    ("x", "BOUTON X"), ("y", "BOUTON Y"),
    ("l1", "GÂCHETTE L1"), ("r1", "GÂCHETTE R1"),
    ("l2", "GÂCHETTE L2"), ("r2", "GÂCHETTE R2"),
    ("select", "SELECT"), ("start", "START"),
    ("l3", "CLIC DU STICK GAUCHE"), ("r3", "CLIC DU STICK DROIT"),
]

MANETTE_DEFAUT = {
    "a": ["bouton", 0], "b": ["bouton", 1], "x": ["bouton", 2], "y": ["bouton", 3],
    "l1": ["bouton", 4], "r1": ["bouton", 5], "l2": ["bouton", 6], "r2": ["bouton", 7],
    "select": ["bouton", 8], "start": ["bouton", 9],
}


def charger_manette():
    """Mapping enregistre par le calibrage, sinon valeurs par defaut."""
    if os.path.exists(FICHIER_MANETTE):
        try:
            with open(FICHIER_MANETTE, "r", encoding="utf-8") as fic:
                d = json.load(fic)
            if isinstance(d, dict) and d.get("commandes"):
                return d["commandes"], d.get("axes_sticks", [0, 1, 2, 3])
        except Exception as err:
            print("manette.json illisible :", err)
    return dict(MANETTE_DEFAUT), [0, 1, 2, 3]


def calibrer():
    """Ecran de calibrage : demande chaque commande et enregistre le mapping."""
    import pygame

    pygame.init()
    pygame.display.set_caption("neoForge, calibrage")
    ecran = pygame.display.set_mode((LARGEUR, HAUTEUR))
    pygame.joystick.init()
    manettes = []
    for i in range(pygame.joystick.get_count()):
        j = pygame.joystick.Joystick(i)
        j.init()
        manettes.append(j)

    chemin = None
    for c in ("/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
              "C:/Windows/Fonts/consola.ttf"):
        if os.path.exists(c):
            chemin = c
            break
    if chemin is None:
        chemin = pygame.font.match_font("dejavusansmono,consolas,couriernew,monospace")
    fp = pygame.font.Font(chemin, 13) if chemin else pygame.font.Font(None, 15)
    fg = pygame.font.Font(chemin, 26) if chemin else pygame.font.Font(None, 30)
    fm = pygame.font.Font(chemin, 15) if chemin else pygame.font.Font(None, 17)

    ACCENT = (198, 155, 240)
    CLAIR = (235, 232, 241)
    GRIS = (139, 132, 155)

    commandes = {}
    utilises = set()
    axes_bouges = set()
    repos = {}
    for j in manettes:
        for a in range(j.get_numaxes()):
            repos[(j.get_id(), a)] = j.get_axis(a)

    def dessiner(i, libelle, message, reste):
        ecran.fill((10, 9, 16))
        pygame.draw.rect(ecran, (36, 30, 51), pygame.Rect(0, 0, LARGEUR, 34))
        t = fp.render("neoFORGE   CALIBRAGE DE LA MANETTE", True, ACCENT)
        ecran.blit(t, (14, 10))
        t = fp.render("%d / %d" % (i + 1, len(COMMANDES)), True, GRIS)
        ecran.blit(t, (LARGEUR - 14 - t.get_width(), 10))

        t = fp.render("APPUIE SUR", True, GRIS)
        ecran.blit(t, (LARGEUR // 2 - t.get_width() // 2, 150))
        t = fg.render(libelle, True, CLAIR)
        ecran.blit(t, (LARGEUR // 2 - t.get_width() // 2, 178))

        t = fm.render(message, True, ACCENT)
        ecran.blit(t, (LARGEUR // 2 - t.get_width() // 2, 240))

        largeur_barre = int(400 * reste)
        pygame.draw.rect(ecran, (36, 30, 51), pygame.Rect(120, 285, 400, 6))
        pygame.draw.rect(ecran, (110, 80, 150), pygame.Rect(120, 285, largeur_barre, 6))

        t = fp.render("ne touche à rien pendant 6 secondes pour passer",
                      True, GRIS)
        ecran.blit(t, (LARGEUR // 2 - t.get_width() // 2, 330))
        t = fp.render("le calibrage se termine tout seul", True, GRIS)
        ecran.blit(t, (LARGEUR // 2 - t.get_width() // 2, 350))

        y = 400
        deja = ", ".join("%s=%s" % (n, commandes[n][1]) for n, _ in COMMANDES
                         if n in commandes)
        for ligne in [deja[k:k + 74] for k in range(0, len(deja), 74)][:2]:
            t = fp.render(ligne, True, GRIS)
            ecran.blit(t, (14, y))
            y += 16
        pygame.display.flip()

    horloge = pygame.time.Clock()
    for i, (nom, libelle) in enumerate(COMMANDES):
        debut = time.time()
        message = ""
        pris = False
        while not pris:
            reste = max(0.0, 1.0 - (time.time() - debut) / 6.0)
            if reste <= 0.0:
                break
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit()
                    return 1
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                    pygame.quit()
                    return 1
                if ev.type == pygame.JOYBUTTONDOWN:
                    cle = ("bouton", ev.button)
                    if cle in utilises:
                        message = "déjà utilisé, essaie un autre"
                        continue
                    commandes[nom] = ["bouton", ev.button]
                    utilises.add(cle)
                    pris = True
                elif ev.type == pygame.JOYAXISMOTION:
                    base = repos.get((ev.joy, ev.axis), 0.0)
                    if abs(ev.value - base) > 0.7:
                        sens = 1 if ev.value > base else -1
                        cle = ("axe", ev.axis, sens)
                        if cle in utilises:
                            message = "déjà utilisé, essaie un autre"
                            continue
                        commandes[nom] = ["axe", ev.axis, sens]
                        utilises.add(cle)
                        axes_bouges.add(ev.axis)
                        pris = True
            dessiner(i, libelle, message or "en attente", reste)
            horloge.tick(60)
        if pris:
            # attendre le relachement pour ne pas enchainer sur le meme appui
            fin = time.time() + 0.45
            while time.time() < fin:
                pygame.event.pop() if False else pygame.event.get()
                horloge.tick(60)

    axes_sticks = [a for a in range(6) if a not in axes_bouges][:4]
    if not axes_sticks:
        axes_sticks = [0, 1, 2, 3]

    with open(FICHIER_MANETTE, "w", encoding="utf-8") as fic:
        json.dump({"commandes": commandes, "axes_sticks": axes_sticks}, fic, indent=1)

    ecran.fill((10, 9, 16))
    t = fg.render("CALIBRAGE ENREGISTRÉ", True, ACCENT)
    ecran.blit(t, (LARGEUR // 2 - t.get_width() // 2, 150))
    t = fm.render("%d commandes sur %d" % (len(commandes), len(COMMANDES)), True, CLAIR)
    ecran.blit(t, (LARGEUR // 2 - t.get_width() // 2, 200))
    t = fp.render("tu peux lancer neoForge", True, GRIS)
    ecran.blit(t, (LARGEUR // 2 - t.get_width() // 2, 250))
    pygame.display.flip()
    time.sleep(3)
    pygame.quit()
    print("mapping enregistre dans", FICHIER_MANETTE)
    print(json.dumps(commandes, indent=1))
    return 0


# ---------------------------------------------------------------- autotest

def autotest():
    print("neoForge %s, autotest" % VERSION)
    assurer_dossiers()
    p = Projet()
    p.exemple()

    s = construire(p)
    assert s is not None, "solide vide"
    vol = s.volume()
    print("  volume ............ %.1f mm3" % vol)
    assert vol > 0, "volume nul"
    print("  genre ............. %d (2 trous attendus)" % s.genus())
    assert s.genus() == 2, "les deux percages ne sont pas traverses"

    tris = triangles(s)
    print("  triangles ......... %d" % len(tris))
    assert len(tris) > 100

    stl = exporter_stl(tris, os.path.join(DOSSIER_EXPORT, "autotest.stl"))
    taille = os.path.getsize(stl)
    with open(stl, "rb") as f:
        f.seek(80)
        n = struct.unpack("<I", f.read(4))[0]
    print("  stl ............... %d triangles, %d octets" % (n, taille))
    assert n == len(tris)
    assert taille == 84 + 50 * n

    tmf = exporter_3mf(tris, os.path.join(DOSSIER_EXPORT, "autotest.3mf"))
    with zipfile.ZipFile(tmf) as z:
        noms = z.namelist()
        modele = z.read("3D/3dmodel.model").decode("utf-8")
    print("  3mf ............... %s" % ", ".join(noms))
    assert "[Content_Types].xml" in noms and "_rels/.rels" in noms
    assert modele.count("<triangle ") == len(tris)
    assert 'unit="millimeter"' in modele

    p.nom = "autotest.nfg"
    chemin = sauver_projet(p)
    q = Projet()
    charger_projet(q, "autotest.nfg")
    assert len(q.prims) == len(p.prims)
    assert q.prims[1].forme == p.prims[1].forme
    assert q.prims[1].pos == p.prims[1].pos
    print("  projet ............ aller retour ok (%s)" % os.path.basename(chemin))

    p2 = Projet()
    p2.prims = [Primitive(CUBE, UNION, [0, 0, 10], [20, 20, 20]),
                Primitive(SPHERE, INTERSECT, [0, 0, 10], [26, 26, 26])]
    v2 = construire(p2).volume()
    print("  intersection ...... %.1f mm3" % v2)
    assert 0 < v2 < 8000

    p3 = Projet()
    p3.prims = [Primitive(CONE, UNION, [0, 0, 10], [30, 10, 20], [0, 0, 30])]
    assert construire(p3).volume() > 0
    print("  cone pivote ....... ok")

    print("Tout est bon.")
    return 0


# ---------------------------------------------------------------- application

def choisir_backend():
    """OpenGL ES sur la console (KMSDRM, Mali), OpenGL de bureau ailleurs."""
    if "--gles" in sys.argv:
        return "gles"
    if "--gl" in sys.argv:
        return "gl"
    if os.name == "nt":
        return "gl"
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return "gl"
    if os.path.exists("/usr/lib/libmali.so") or os.path.exists("/usr/lib/libmali.so.1"):
        return "gles"
    return "gl"


def lancer(plein_ecran=False, lister_boutons=False):
    import pygame
    import numpy as np

    backend = choisir_backend()
    if backend == "gles":
        os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
        from OpenGL import GLES2 as G
        ENTETE_V = "#version 100\n"
        ENTETE_F = "#version 100\nprecision mediump float;\n"
    else:
        from OpenGL import GL as G
        ENTETE_V = "#version 120\n"
        ENTETE_F = "#version 120\n"
    print("moteur de rendu :", "OpenGL ES 2.0" if backend == "gles" else "OpenGL de bureau")

    pygame.init()
    pygame.display.set_caption("neoForge %s" % VERSION)
    drapeaux = pygame.OPENGL | pygame.DOUBLEBUF
    if plein_ecran:
        drapeaux |= pygame.FULLSCREEN
    if backend == "gles":
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK,
                                        pygame.GL_CONTEXT_PROFILE_ES)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 2)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 0)
    pygame.display.gl_set_attribute(pygame.GL_DEPTH_SIZE, 24)
    pygame.display.set_mode((LARGEUR, HAUTEUR), drapeaux)

    pygame.joystick.init()
    manettes = []
    for i in range(pygame.joystick.get_count()):
        j = pygame.joystick.Joystick(i)
        j.init()
        manettes.append(j)

    # ---- polices
    def fichier_police():
        """Une police a chasse fixe, ni grasse ni italique."""
        candidats = [
            "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "C:/Windows/Fonts/consola.ttf",
            "/System/Library/Fonts/Menlo.ttc",
        ]
        for c in candidats:
            if os.path.exists(c):
                return c
        import glob
        for motif in ("/usr/share/fonts/**/*Mono*.ttf",
                      "/usr/share/fonts/**/*mono*.ttf"):
            for c in sorted(glob.glob(motif, recursive=True)):
                b = os.path.basename(c).lower()
                if "bold" in b or "oblique" in b or "italic" in b:
                    continue
                return c
        return pygame.font.match_font("dejavusansmono,consolas,couriernew,monospace")

    CHEMIN_POLICE = fichier_police()
    print("police :", CHEMIN_POLICE)

    def police(taille):
        if CHEMIN_POLICE:
            return pygame.font.Font(CHEMIN_POLICE, taille)
        return pygame.font.Font(None, taille + 2)

    F_PETIT = police(11)
    F_NORM = police(13)
    F_GRAND = police(17)

    ACCENT = (198, 155, 240)
    CLAIR = (235, 232, 241)
    GRIS = (139, 132, 155)
    DOUX = (196, 190, 210)
    VERT = (110, 210, 150)
    ROUGE = (240, 115, 115)

    # ---- etat
    charger_reglages()
    projet = Projet()

    etat = {
        "yaw": 0.7, "pitch": 0.5, "dist": 210.0,
        "cible": [0.0, 0.0, 20.0],
        "ecran": "edition",
        "flash": "", "flash_t": 0.0,
        "hist": [],
        "menu_i": 0, "fic_i": 0, "champ_i": 0, "pave_i": 0, "accueil_i": 0,
        "exp_i": 0,
        "saisie": "", "champ_actif": None,
        "quitter": False,
        "solide": None, "tris": [],
        "sale": True, "fantome": True,
        "roue": None, "observation": False,
    }
    etat["suite"] = "edition" if os.path.exists(TEMOIN_ACCUEIL) else "accueil"
    etat["ecran"] = "lancement"
    etat["t_lancement"] = time.time()

    MENU = ["SAUVEGARDER", "CHARGER", "EXPORTER STL", "EXPORTER 3MF",
            "FICHIERS ET PARTAGE", "COLLAGE", "NOUVEAU PROJET", "QUITTER"]

    def libelles_menu():
        out = []
        for e in MENU:
            if e == "COLLAGE":
                out.append("COLLAGE DES PIÈCES : %s"
                           % ("OUI" if REGLAGES.get("collage", True) else "NON"))
            else:
                out.append(e)
        return out
    PAVE = ["7", "8", "9", "4", "5", "6", "1", "2", "3", "0", ".", "-",
            "EFFACER", "VALIDER"]

    def flash(txt):
        etat["flash"] = txt.upper()
        etat["flash_t"] = 2.2

    def instantane():
        etat["hist"].append(json.dumps(projet.dico()))
        if len(etat["hist"]) > 60:
            etat["hist"].pop(0)

    def annuler():
        if not etat["hist"]:
            flash("rien à annuler")
            return
        projet.charger_dico(json.loads(etat["hist"].pop()))
        etat["sale"] = True
        flash("annulé")

    # ---------------------------------------------------------------- shaders

    def compiler(source, genre):
        s = G.glCreateShader(genre)
        G.glShaderSource(s, source)
        G.glCompileShader(s)
        if not G.glGetShaderiv(s, G.GL_COMPILE_STATUS):
            raise RuntimeError("shader : " + str(G.glGetShaderInfoLog(s)))
        return s

    def programme(vs, fs):
        p = G.glCreateProgram()
        G.glAttachShader(p, compiler(ENTETE_V + vs, G.GL_VERTEX_SHADER))
        G.glAttachShader(p, compiler(ENTETE_F + fs, G.GL_FRAGMENT_SHADER))
        G.glLinkProgram(p)
        if not G.glGetProgramiv(p, G.GL_LINK_STATUS):
            raise RuntimeError("lien : " + str(G.glGetProgramInfoLog(p)))
        return p

    VS_GEO = """
attribute vec3 aPos;
attribute vec3 aNrm;
uniform mat4 uMVP;
uniform float uPousse;
varying vec3 vNrm;
void main(){
  vNrm = aNrm;
  gl_Position = uMVP * vec4(aPos + aNrm * uPousse, 1.0);
}
"""
    FS_GEO = """
varying vec3 vNrm;
uniform vec3 uCouleur;
uniform vec3 uLumiere;
uniform float uUni;
uniform float uAlpha;
void main(){
  if (uUni > 0.5) {
    gl_FragColor = vec4(uCouleur, 1.0);
  } else {
    vec3 n = normalize(vNrm);
    float d = max(dot(n, normalize(uLumiere)), 0.0);
    float amb = 0.34 + 0.18 * n.z;
    gl_FragColor = vec4(uCouleur * (amb + 0.80 * d), uAlpha);
  }
}
"""
    VS_HUD = """
attribute vec2 aPos;
attribute vec2 aUV;
varying vec2 vUV;
void main(){
  vUV = aUV;
  gl_Position = vec4(aPos, 0.0, 1.0);
}
"""
    FS_HUD = """
varying vec2 vUV;
uniform sampler2D uTex;
void main(){
  gl_FragColor = texture2D(uTex, vUV);
}
"""

    prog_geo = programme(VS_GEO, FS_GEO)
    prog_hud = programme(VS_HUD, FS_HUD)

    L_POS = G.glGetAttribLocation(prog_geo, "aPos")
    L_NRM = G.glGetAttribLocation(prog_geo, "aNrm")
    U_MVP = G.glGetUniformLocation(prog_geo, "uMVP")
    U_COL = G.glGetUniformLocation(prog_geo, "uCouleur")
    U_LUM = G.glGetUniformLocation(prog_geo, "uLumiere")
    U_UNI = G.glGetUniformLocation(prog_geo, "uUni")
    U_ALPHA = G.glGetUniformLocation(prog_geo, "uAlpha")
    U_POUSSE = G.glGetUniformLocation(prog_geo, "uPousse")

    H_POS = G.glGetAttribLocation(prog_hud, "aPos")
    H_UV = G.glGetAttribLocation(prog_hud, "aUV")
    H_TEX = G.glGetUniformLocation(prog_hud, "uTex")

    # ---------------------------------------------------------------- tampons

    def tampon(donnees):
        b = G.glGenBuffers(1)
        G.glBindBuffer(G.GL_ARRAY_BUFFER, b)
        G.glBufferData(G.GL_ARRAY_BUFFER, donnees.nbytes, donnees, G.GL_DYNAMIC_DRAW)
        return b

    def remplir(b, donnees):
        G.glBindBuffer(G.GL_ARRAY_BUFFER, b)
        G.glBufferData(G.GL_ARRAY_BUFFER, donnees.nbytes, donnees, G.GL_DYNAMIC_DRAW)

    def lignes_plateau():
        pts = []
        d = PLATEAU / 2.0
        v = -d
        while v <= d + 0.1:
            pts += [v, -d, 0.0, 0, 0, 1, v, d, 0.0, 0, 0, 1]
            pts += [-d, v, 0.0, 0, 0, 1, d, v, 0.0, 0, 0, 1]
            v += 16.0
        return np.array(pts, dtype=np.float32)

    def lignes_bord():
        d = PLATEAU / 2.0
        c = [(-d, -d, d, -d), (d, -d, d, d), (d, d, -d, d), (-d, d, -d, -d)]
        pts = []
        for a, b, e, f in c:
            pts += [a, b, 0.0, 0, 0, 1, e, f, 0.0, 0, 0, 1]
        pts += [0, 0, 0, 0, 0, 1, 24, 0, 0, 0, 0, 1]
        pts += [0, 0, 0, 0, 0, 1, 0, 24, 0, 0, 0, 1]
        return np.array(pts, dtype=np.float32)

    B_GRILLE = tampon(lignes_plateau())
    N_GRILLE = len(lignes_plateau()) // 6
    B_BORD = tampon(lignes_bord())
    N_BORD = len(lignes_bord()) // 6
    B_SOLIDE = tampon(np.zeros(6, dtype=np.float32))
    N_SOLIDE = [0]
    B_SEL = tampon(np.zeros(6 * 24, dtype=np.float32))
    B_FANTOME = tampon(np.zeros(6, dtype=np.float32))
    N_FANTOME = [0]

    QUAD = np.array([-1, -1, 0, 0,  1, -1, 1, 0,  1, 1, 1, 1,
                     -1, -1, 0, 0,  1, 1, 1, 1,  -1, 1, 0, 1], dtype=np.float32)
    B_QUAD = tampon(QUAD)
    TEX_HUD = G.glGenTextures(1)

    def dessiner_tampon(b, n, mode, couleur, uni, mvp, lumiere, alpha=1.0, pousse=0.0):
        G.glUseProgram(prog_geo)
        G.glUniform1f(U_ALPHA, alpha)
        G.glUniform1f(U_POUSSE, pousse)
        G.glUniformMatrix4fv(U_MVP, 1, G.GL_FALSE, mvp)
        G.glUniform3f(U_COL, couleur[0], couleur[1], couleur[2])
        G.glUniform3f(U_LUM, lumiere[0], lumiere[1], lumiere[2])
        G.glUniform1f(U_UNI, uni)
        G.glBindBuffer(G.GL_ARRAY_BUFFER, b)
        G.glEnableVertexAttribArray(L_POS)
        G.glVertexAttribPointer(L_POS, 3, G.GL_FLOAT, G.GL_FALSE, 24, ctypes.c_void_p(0))
        if L_NRM >= 0:
            G.glEnableVertexAttribArray(L_NRM)
            G.glVertexAttribPointer(L_NRM, 3, G.GL_FLOAT, G.GL_FALSE, 24, ctypes.c_void_p(12))
        G.glDrawArrays(mode, 0, n)

    # ---------------------------------------------------------------- matrices

    def m_perspective(fovy, ratio, proche, loin):
        f = 1.0 / math.tan(math.radians(fovy) / 2.0)
        m = np.zeros((4, 4), dtype=np.float32)
        m[0, 0] = f / ratio
        m[1, 1] = f
        m[2, 2] = (loin + proche) / (proche - loin)
        m[2, 3] = -1.0
        m[3, 2] = (2.0 * loin * proche) / (proche - loin)
        return m

    def m_regard(oeil, cible, haut):
        oeil = np.array(oeil, dtype=np.float64)
        cible = np.array(cible, dtype=np.float64)
        av = cible - oeil
        av = av / (np.linalg.norm(av) or 1.0)
        dr = np.cross(av, np.array(haut, dtype=np.float64))
        dr = dr / (np.linalg.norm(dr) or 1.0)
        hh = np.cross(dr, av)
        m = np.zeros((4, 4), dtype=np.float32)
        m[0, 0], m[1, 0], m[2, 0] = dr
        m[0, 1], m[1, 1], m[2, 1] = hh
        m[0, 2], m[1, 2], m[2, 2] = -av
        m[3, 0] = -np.dot(dr, oeil)
        m[3, 1] = -np.dot(hh, oeil)
        m[3, 2] = np.dot(av, oeil)
        m[3, 3] = 1.0
        return m

    def camera():
        cp = math.cos(etat["pitch"])
        return (etat["cible"][0] + etat["dist"] * cp * math.sin(etat["yaw"]),
                etat["cible"][1] + etat["dist"] * cp * math.cos(etat["yaw"]),
                etat["cible"][2] + etat["dist"] * math.sin(etat["pitch"]))

    def mvp_courant():
        p = m_perspective(52.0, LARGEUR / float(HAUTEUR), 1.0, 3000.0)
        v = m_regard(camera(), etat["cible"], [0.0, 0.0, 1.0])
        return (v @ p).astype(np.float32)

    def projeter(pt, mvp):
        v = np.array([pt[0], pt[1], pt[2], 1.0], dtype=np.float32) @ mvp
        if v[3] <= 0.001:
            return None
        x = v[0] / v[3]
        y = v[1] / v[3]
        return ((x + 1.0) * 0.5 * LARGEUR, (1.0 - (y + 1.0) * 0.5) * HAUTEUR)

    # ---------------------------------------------------------------- geometrie

    def reconstruire():
        try:
            solide = construire(projet)
        except Exception as err:
            flash("géométrie impossible")
            print("erreur de construction :", err)
            etat["sale"] = False
            return
        etat["solide"] = solide
        tris = triangles(solide)
        etat["tris"] = tris
        donnees = np.zeros((len(tris) * 3, 6), dtype=np.float32)
        k = 0
        for a, b, c in tris:
            n = normale(a, b, c)
            for s in (a, b, c):
                donnees[k, 0:3] = s
                donnees[k, 3:6] = n
                k += 1
        remplir(B_SOLIDE, donnees.reshape(-1))
        N_SOLIDE[0] = len(tris) * 3
        etat["sale"] = False
        maj_fantome()

    def maj_fantome():
        """Silhouette translucide de la piece selectionnee."""
        p = None if etat["observation"] else projet.courante()
        if not p:
            N_FANTOME[0] = 0
            return
        try:
            import manifold3d as mf
            tris = triangles(p.solide(mf))
        except Exception:
            N_FANTOME[0] = 0
            return
        d = np.zeros((len(tris) * 3, 6), dtype=np.float32)
        k = 0
        for a, b, c in tris:
            n = normale(a, b, c)
            for som in (a, b, c):
                d[k, 0:3] = som
                d[k, 3:6] = n
                k += 1
        remplir(B_FANTOME, d.reshape(-1))
        N_FANTOME[0] = len(tris) * 3

    # ---------------------------------------------------------------- actions

    ROUE = [("CUBE", CUBE), ("CYLINDRE", CYLINDRE), ("SPHÈRE", SPHERE),
            ("CÔNE", CONE), ("TROU", "trou"), ("DUPLIQUER", "dup"),
            ("SUPPRIMER", "del")]
    PAS_ROUE = 360.0 / len(ROUE)

    def poser_a_cote(p):
        """Place une nouvelle piece a droite de la selection, sur le plateau."""
        base = projet.courante()
        if base:
            mn, mx = base.boite()
            p.pos[0] = mx[0] + p.demi_etendue()[0] + 6.0
            p.pos[1] = base.pos[1]
        p.pos[2] = p.demi_etendue()[2]

    def nouvelle_forme(forme):
        if len(projet.prims) >= 24:
            flash("24 pièces maximum")
            return
        instantane()
        dims = [20.0, 0.0, 24.0] if forme == CONE else [20.0, 20.0, 20.0]
        p = Primitive(forme, UNION, [0, 0, 10], dims)
        poser_a_cote(p)
        projet.prims.append(p)
        projet.sel = len(projet.prims) - 1
        etat["sale"] = True
        flash(NOMS_FORMES[forme].lower() + " ajouté")

    def nouveau_trou():
        base = projet.courante()
        if not base or len(projet.prims) >= 24:
            flash("24 pièces maximum")
            return
        instantane()
        mn, mx = base.boite()
        h = (mx[2] - mn[2]) + 30.0
        p = Primitive(CYLINDRE, SOUSTRAIT,
                      [base.pos[0], base.pos[1], (mn[2] + mx[2]) / 2.0],
                      [8.0, 8.0, h])
        projet.prims.append(p)
        projet.sel = len(projet.prims) - 1
        etat["sale"] = True
        flash("trou traversant, R1 et la croix pour le diamètre")

    def executer_roue(i):
        if i is None or i < 0 or i >= len(ROUE):
            return
        _, quoi = ROUE[i]
        if quoi == "trou":
            nouveau_trou()
        elif quoi == "dup":
            dupliquer()
        elif quoi == "del":
            supprimer()
        else:
            nouvelle_forme(quoi)

    def dupliquer():
        if etat["observation"]:
            rien_selectionne()
            return
        base = projet.courante()
        if not base or len(projet.prims) >= 24:
            flash("24 pièces maximum")
            return
        instantane()
        c = base.copie()
        c.pos[0] += max(12.0, base.demi_etendue()[0] * 2 + 6)
        projet.prims.append(c)
        projet.sel = len(projet.prims) - 1
        etat["sale"] = True
        flash("dupliquée")

    def supprimer():
        if etat["observation"]:
            rien_selectionne()
            return
        if len(projet.prims) <= 1:
            flash("il faut au moins une pièce")
            return
        instantane()
        projet.prims.pop(projet.sel)
        projet.sel = max(0, projet.sel - 1)
        etat["sale"] = True
        flash("supprimée")

    def basculer_creuser():
        if etat["observation"]:
            rien_selectionne()
            return
        if projet.sel == 0:
            flash("la première pièce est toujours de la matière")
            return
        instantane()
        p = projet.courante()
        p.op = SOUSTRAIT if p.op == UNION else UNION
        etat["sale"] = True
        flash("cette pièce : " + NOMS_OPS[p.op])

    def quart_tour():
        p = projet.courante()
        if not p:
            return
        instantane()
        p.rot[2] = (p.rot[2] + 90.0) % 360.0
        etat["sale"] = True
        flash("quart de tour")

    def precedente():
        if etat["observation"]:
            etat["observation"] = False
            projet.sel = len(projet.prims) - 1
        elif projet.sel <= 0:
            etat["observation"] = True
        else:
            projet.sel -= 1
        annonce_selection()

    def cycler_forme():
        if etat["observation"]:
            rien_selectionne()
            return
        instantane()
        p = projet.courante()
        p.forme = (p.forme + 1) % 4
        if p.forme == CONE and p.dim[1] >= p.dim[0] * 0.9:
            p.dim[1] = 0.0
        etat["sale"] = True
        flash("forme : " + NOMS_FORMES[p.forme])

    def poser_plateau():
        """Fait tomber la piece jusqu au premier obstacle, sinon le plateau."""
        if etat["observation"]:
            rien_selectionne()
            return
        p = projet.courante()
        if not p:
            return
        instantane()
        if projet.sel > 0 and p.op != UNION:
            # un creux ne se pose sur rien, il traverse : on le ramene au plateau
            p.pos[2] = p.demi_etendue()[2]
            flash("creux ramené au plateau")
        else:
            p.pos[2] += limiter(p, projet.sel, projet.prims, 2, -10000.0, force=True)
            mini, _ = p.boite()
            flash("posée sur le plateau" if abs(mini[2]) < 0.01
                  else "posée sur la pièce du dessous")
        etat["sale"] = True

    def piece_dessous(p, index):
        """La piece de matiere sur laquelle celle-ci repose, ou celle qu elle recouvre."""
        mini, maxi = p.boite()
        candidates = []
        for i, autre in enumerate(projet.prims):
            if i == index:
                continue
            if i > 0 and autre.op != UNION:
                continue
            ami, ama = autre.boite()
            recouvre = min(
                min(maxi[0], ama[0]) - max(mini[0], ami[0]),
                min(maxi[1], ama[1]) - max(mini[1], ami[1]))
            if recouvre <= 0.01:
                continue
            if ama[2] <= mini[2] + 1.0:          # elle est bien dessous
                candidates.append((0, ama[2], recouvre, i))
            else:                                 # sinon, celle qu on recouvre le plus
                candidates.append((1, 0.0, recouvre, i))
        if not candidates:
            return None
        poses = [c for c in candidates if c[0] == 0]
        if poses:
            poses.sort(key=lambda c: (-c[1], -c[2]))
            return projet.prims[poses[0][3]]
        candidates.sort(key=lambda c: -c[2])
        return projet.prims[candidates[0][3]]

    def centrer_sur_dessous():
        if etat["observation"]:
            rien_selectionne()
            return
        p = projet.courante()
        if not p:
            return
        cible = piece_dessous(p, projet.sel)
        instantane()
        mini, maxi = p.boite()
        cx = (mini[0] + maxi[0]) / 2.0
        cy = (mini[1] + maxi[1]) / 2.0
        if cible is None:
            vx, vy = 0.0, 0.0
            msg = "centrée sur le plateau"
        else:
            cmi, cma = cible.boite()
            vx = (cmi[0] + cma[0]) / 2.0
            vy = (cmi[1] + cma[1]) / 2.0
            msg = "centrée sur la pièce du dessous"
        p.pos[0] += vx - cx
        p.pos[1] += vy - cy
        etat["sale"] = True
        flash(msg)

    def recadrer():
        p = projet.courante()
        if not p:
            etat["cible"] = [0.0, 0.0, 10.0]
            etat["dist"] = 135.0
            flash("vue recentrée sur le plateau")
            return
        etat["cible"] = list(p.pos)
        etat["dist"] = max(90.0, max(p.demi_etendue()) * 6 + 60)
        flash("vue recadrée")

    def annonce_selection():
        maj_fantome()
        flash("observation, rien n'est sélectionné" if etat["observation"]
              else "pièce %d sur %d" % (projet.sel + 1, len(projet.prims)))

    def suivante():
        if etat["observation"]:
            etat["observation"] = False
            projet.sel = 0
        elif projet.sel >= len(projet.prims) - 1:
            etat["observation"] = True
        else:
            projet.sel += 1
        annonce_selection()

    def base_sol():
        yaw = etat["yaw"]
        return math.sin(yaw), math.cos(yaw), math.cos(yaw), -math.sin(yaw)

    def axe_dominant(x, y):
        if abs(x) > abs(y):
            return 0, 1 if x > 0 else -1
        return 1, 1 if y > 0 else -1

    NOMS_AXES = ["X", "Y", "Z"]

    def axes_ecran():
        """Quel axe du monde la croix pilote, vu d ou est la camera."""
        avx, avy, drx, dry = base_sol()
        a_av, s_av = axe_dominant(-avx, -avy)
        a_dr, s_dr = axe_dominant(drx, dry)
        return a_dr, s_dr, a_av, s_av

    def rien_selectionne():
        flash("rien n'est sélectionné, L1 ou R1 pour choisir une pièce")

    def croix(direction, pas=1.0):
        if etat["observation"]:
            return
        p = projet.courante()
        if not p:
            return
        hauteur = "l1" in enfonce
        taille = "r1" in enfonce
        if hauteur:
            enfonce["l1"]["fait"] = True
        if taille:
            enfonce["r1"]["fait"] = True

        instantane()
        a_dr, s_dr, a_av, s_av = axes_ecran()
        vertical = direction in ("haut", "bas")
        avant = direction in ("haut", "droite")

        if hauteur and taille:
            # les deux gachettes ensemble : rotation par pas de 15 degres
            axe = a_dr if vertical else 2
            p.rot[axe] = (p.rot[axe] + (15.0 if avant else -15.0)) % 360.0
            flash("%s %.0f°" % (NOMS_AXES[axe], p.rot[axe]))
            etat["sale"] = True
            return

        if taille:
            grandir = 1 if avant else -1
            if p.forme == SPHERE:
                cible = 0
            elif vertical:
                cible = 2                      # haut et bas : toujours la hauteur
            elif p.forme in (CYLINDRE, CONE):
                cible = 0                      # gauche et droite : le diametre
            else:
                cible = a_dr                   # gauche et droite : l axe horizontal vu
            p.dim[cible] = max(1.0, p.dim[cible] + pas * grandir)
            if p.forme == SPHERE:
                p.dim[1] = p.dim[2] = p.dim[0]
            flash("%s %g mm" % (
                "DIAMÈTRE" if (cible == 0 and p.forme != CUBE) else
                ("HAUTEUR Z" if cible == 2 else NOMS_AXES[cible]),
                p.dim[cible]))
        elif hauteur and vertical:
            demande = pas if direction == "haut" else -pas
            reel = limiter(p, projet.sel, projet.prims, 2, demande)
            p.pos[2] += reel
            if abs(reel) < abs(demande) - 0.0001:
                flash("collée")
        else:
            if vertical:
                axe = a_av
                demande = pas * s_av * (1 if direction == "haut" else -1)
            else:
                axe = a_dr
                demande = pas * s_dr * (1 if direction == "droite" else -1)
            reel = limiter(p, projet.sel, projet.prims, axe, demande)
            p.pos[axe] += reel
            if abs(reel) < abs(demande) - 0.0001:
                flash("collée")
        etat["sale"] = True

    def champs_courants():
        p = projet.courante()
        if not p:
            return []
        noms = p.noms_dimensions()
        ch = [("POSITION X", ("pos", 0)), ("POSITION Y", ("pos", 1)),
              ("POSITION Z", ("pos", 2))]
        for i, n in enumerate(noms):
            if n:
                ch.append((n, ("dim", i)))
        ch += [("ROTATION X", ("rot", 0)), ("ROTATION Y", ("rot", 1)),
               ("ROTATION Z", ("rot", 2))]
        return ch

    def valeur_champ(ref):
        return getattr(projet.courante(), ref[0])[ref[1]]

    def poser_champ(ref, v):
        p = projet.courante()
        instantane()
        if ref[0] == "dim":
            v = max(0.1, v)
            getattr(p, ref[0])[ref[1]] = v
            if p.forme == SPHERE:
                p.dim[1] = p.dim[2] = p.dim[0]
        else:
            getattr(p, ref[0])[ref[1]] = v
        etat["sale"] = True

    def executer_menu():
        choix = MENU[etat["menu_i"]]
        if choix == "SAUVEGARDER":
            chemin = sauver_projet(projet)
            flash("enregistré : " + os.path.basename(chemin))
            etat["ecran"] = "edition"
        elif choix == "CHARGER":
            etat["fic_i"] = 0
            etat["ecran"] = "fichiers"
        elif choix in ("EXPORTER STL", "EXPORTER 3MF"):
            if etat["sale"]:
                reconstruire()
            assurer_dossiers()
            base = os.path.splitext(projet.nom)[0] if projet.nom else "piece"
            if choix.endswith("STL"):
                nom = nom_libre(DOSSIER_EXPORT, base, ".stl")
                exporter_stl(etat["tris"], os.path.join(DOSSIER_EXPORT, nom))
            else:
                nom = nom_libre(DOSSIER_EXPORT, base, ".3mf")
                exporter_3mf(etat["tris"], os.path.join(DOSSIER_EXPORT, nom))
            flash("%s  %d triangles" % (nom, len(etat["tris"])))
            etat["exp_i"] = 0
            demarrer_partage()
            etat["ecran"] = "exports"
        elif choix == "FICHIERS ET PARTAGE":
            etat["exp_i"] = 0
            demarrer_partage()
            etat["ecran"] = "exports"
        elif choix == "COLLAGE":
            REGLAGES["collage"] = not REGLAGES.get("collage", True)
            sauver_reglages()
            flash("collage des pièces : %s"
                  % ("activé" if REGLAGES["collage"] else "désactivé"))
        elif choix == "NOUVEAU PROJET":
            instantane()
            projet.nouveau()
            etat["sale"] = True
            etat["ecran"] = "edition"
            flash("nouveau projet")
        else:
            etat["quitter"] = True

    def appui(nom):
        try:
            _appui(nom)
        except Exception:
            traceback.print_exc()
            flash("erreur interne, action ignorée")

    def maintien(nom):
        try:
            _maintien(nom)
        except Exception:
            traceback.print_exc()
            flash("erreur interne, action ignorée")

    def _appui(nom):
        e = etat["ecran"]

        if e == "lancement":
            etat["ecran"] = etat["suite"]
            return

        if e == "accueil":
            etat["accueil_i"] += 1
            if etat["accueil_i"] >= 3:
                etat["ecran"] = "edition"
                try:
                    open(TEMOIN_ACCUEIL, "w").write("vu")
                except Exception:
                    pass
            return

        if e == "aide":
            etat["ecran"] = "edition"
            return

        if e == "menu":
            if nom == "haut":
                etat["menu_i"] = (etat["menu_i"] - 1) % len(MENU)
            elif nom == "bas":
                etat["menu_i"] = (etat["menu_i"] + 1) % len(MENU)
            elif nom == "a":
                executer_menu()
            elif nom in ("b", "start"):
                etat["ecran"] = "edition"
            return

        if e == "fichiers":
            fics = lister_projets()
            if nom == "haut":
                etat["fic_i"] = (etat["fic_i"] - 1) % max(1, len(fics))
            elif nom == "bas":
                etat["fic_i"] = (etat["fic_i"] + 1) % max(1, len(fics))
            elif nom == "a" and fics:
                instantane()
                charger_projet(projet, fics[etat["fic_i"]])
                etat["sale"] = True
                etat["ecran"] = "edition"
                flash("chargé : " + projet.nom)
            elif nom in ("b", "start"):
                etat["ecran"] = "menu"
            return

        if e == "exports":
            fics = lister_exports()
            if nom == "haut":
                etat["exp_i"] = (etat["exp_i"] - 1) % max(1, len(fics))
            elif nom == "bas":
                etat["exp_i"] = (etat["exp_i"] + 1) % max(1, len(fics))
            elif nom == "x" and fics:
                cible = os.path.join(DOSSIER_EXPORT, fics[etat["exp_i"]][0])
                try:
                    os.remove(cible)
                    flash("fichier supprimé")
                except OSError as err:
                    flash("suppression impossible")
                    print(err)
                etat["exp_i"] = max(0, etat["exp_i"] - 1)
            elif nom in ("b", "start"):
                etat["ecran"] = "menu"
            return

        if e == "champs":
            ch = champs_courants()
            if nom == "haut":
                etat["champ_i"] = (etat["champ_i"] - 1) % len(ch)
            elif nom == "bas":
                etat["champ_i"] = (etat["champ_i"] + 1) % len(ch)
            elif nom == "a":
                etat["champ_actif"] = ch[etat["champ_i"]]
                etat["saisie"] = ""
                etat["pave_i"] = 0
                etat["ecran"] = "pave"
            elif nom in ("b", "r1"):
                etat["ecran"] = "edition"
            return

        if e == "pave":
            cols = 3
            if nom == "haut":
                etat["pave_i"] = (etat["pave_i"] - cols) % len(PAVE)
            elif nom == "bas":
                etat["pave_i"] = (etat["pave_i"] + cols) % len(PAVE)
            elif nom == "gauche":
                etat["pave_i"] = (etat["pave_i"] - 1) % len(PAVE)
            elif nom == "droite":
                etat["pave_i"] = (etat["pave_i"] + 1) % len(PAVE)
            elif nom == "a":
                t = PAVE[etat["pave_i"]]
                if t == "EFFACER":
                    etat["saisie"] = etat["saisie"][:-1]
                elif t == "VALIDER":
                    try:
                        v = float(etat["saisie"])
                    except ValueError:
                        flash("valeur illisible")
                        return
                    poser_champ(etat["champ_actif"][1], v)
                    etat["ecran"] = "champs"
                    flash("valeur posée")
                else:
                    etat["saisie"] += t
            elif nom == "b":
                etat["ecran"] = "champs"
            return

        if etat["roue"] is not None:
            if nom in ("droite", "bas"):
                etat["roue"] = (etat["roue"] + 1) % len(ROUE)
            elif nom in ("gauche", "haut"):
                etat["roue"] = (etat["roue"] - 1) % len(ROUE)
            return

        if nom in ("haut", "bas", "gauche", "droite"):
            croix(nom, 1.0)
        elif nom == "a":
            ajouter()
        elif nom == "b":
            annuler()
        elif nom == "x":
            basculer_creuser()
        elif nom == "y":
            cycler_forme()
        elif nom == "l1":
            precedente()
        elif nom == "r1":
            suivante()
        elif nom == "select":
            etat["ecran"] = "aide"
        elif nom == "start":
            etat["menu_i"] = 0
            etat["ecran"] = "menu"
        elif nom == "l3":
            centrer_sur_dessous()
        elif nom == "r3":
            poser_plateau()

    def _maintien(nom):
        e = etat["ecran"]
        if e in ("menu", "fichiers", "pave", "accueil"):
            return
        if e == "aide":
            return
        if nom == "b":
            supprimer()
        elif nom == "x":
            poser_plateau()
        elif nom == "y":
            centrer_sur_dessous()
        elif nom == "select":
            etat["champ_i"] = 0
            etat["ecran"] = "champs"
        elif nom == "start":
            recadrer()

    SECONDAIRE = {"b", "x", "y", "select", "start"}
    MODIFICATEURS = {"l1", "r1"}
    MUETS = {"l2", "r2"}
    REPETE = {"haut", "bas", "gauche", "droite"}
    MAINTIEN_S = 0.42

    TOUCHES = {
        pygame.K_UP: "haut", pygame.K_DOWN: "bas",
        pygame.K_LEFT: "gauche", pygame.K_RIGHT: "droite",
        pygame.K_SPACE: "a", pygame.K_b: "b", pygame.K_x: "x", pygame.K_y: "y",
        pygame.K_q: "l1", pygame.K_e: "r1",
        pygame.K_TAB: "select", pygame.K_RETURN: "start",
        pygame.K_KP_ENTER: "start",
    }
    ANALOG = {pygame.K_a: "gx-", pygame.K_d: "gx+",
              pygame.K_w: "gy-", pygame.K_s: "gy+",
              pygame.K_j: "dx-", pygame.K_l: "dx+",
              pygame.K_i: "dy-", pygame.K_k: "dy+",
              pygame.K_z: "zoom-", pygame.K_c: "zoom+"}
    MAPPING, AXES_STICKS = charger_manette()
    BOUTONS_MANETTE = {}
    AXES_COMMANDE = {}
    for _nom, _def in MAPPING.items():
        if _def[0] == "bouton":
            BOUTONS_MANETTE[_def[1]] = _nom
        elif _def[0] == "axe":
            AXES_COMMANDE[(_def[1], _def[2])] = _nom
    AXES_STICKS = [a for a in AXES_STICKS
                   if not any(a == k[0] for k in AXES_COMMANDE)]
    while len(AXES_STICKS) < 4:
        AXES_STICKS.append(-1)
    CHAPEAU = {(0, 1): "haut", (0, -1): "bas", (-1, 0): "gauche", (1, 0): "droite"}
    etat_axes = {}
    print("commandes chargees :", len(MAPPING), " axes des sticks :", AXES_STICKS[:4])

    enfonce = {}
    axes_clavier = {}

    def presser(nom):
        if nom in enfonce:
            return
        enfonce[nom] = {"t": time.time(), "fait": False, "rep": 0.0}
        if nom == "a":
            if etat["ecran"] == "edition":
                etat["roue"] = -1
            else:
                appui("a")
            return
        if nom in SECONDAIRE or nom in MODIFICATEURS or nom in MUETS:
            return
        appui(nom)

    def relacher(nom):
        info = enfonce.pop(nom, None)
        if info is None:
            return
        if nom == "a":
            if etat["roue"] is not None:
                choix = etat["roue"]
                etat["roue"] = None
                if choix is not None and choix >= 0:
                    executer_roue(choix)
                elif time.time() - info["t"] < 0.35:
                    flash("maintiens A pour ajouter une pièce")
            return
        if (nom in SECONDAIRE or nom in MODIFICATEURS) and not info["fait"]:
            appui(nom)

    # ---------------------------------------------------------------- hud

    surface_hud = pygame.Surface((LARGEUR, HAUTEUR), pygame.SRCALPHA)

    def texte(x, y, s, f=F_NORM, c=CLAIR):
        img = f.render(s, True, c)
        surface_hud.blit(img, (x, y))
        return img.get_width()

    def texte_droite(x, y, s, f=F_NORM, c=CLAIR):
        img = f.render(s, True, c)
        surface_hud.blit(img, (x - img.get_width(), y))

    def pastille(x, y, lib, rond=False):
        img = F_PETIT.render(lib, True, ACCENT)
        w = 17 if rond else img.get_width() + 10
        r = pygame.Rect(x, y - 1, w, 16)
        pygame.draw.rect(surface_hud, (60, 53, 80), r, border_radius=8 if rond else 3)
        surface_hud.blit(img, (x + (w - img.get_width()) // 2, y + 1))
        return w

    def indice(x, y, lib, val, rond=False, f=F_PETIT):
        w = pastille(x, y, lib, rond)
        img = f.render(val, True, DOUX)
        surface_hud.blit(img, (x + w + 5, y + 1))
        return x + w + 5 + img.get_width() + 12

    def pilule(cx, cy, libelle, actif, f=None, pad=14, haut=24):
        """Un bouton arrondi dimensionne sur son texte, centre sur cx cy."""
        f = f or F_PETIT
        lw, lh = f.size(libelle)
        w, h = lw + pad * 2, max(haut, lh + 8)
        r = pygame.Rect(int(cx - w / 2), int(cy - h / 2), w, h)
        pygame.draw.rect(surface_hud, (198, 155, 240) if actif else (26, 22, 38),
                         r, border_radius=h // 2)
        pygame.draw.rect(surface_hud, (150, 120, 195) if actif else (72, 63, 96),
                         r, 1, border_radius=h // 2)
        img = f.render(libelle, True, (14, 12, 20) if actif else DOUX)
        surface_hud.blit(img, (r.centerx - lw // 2, r.centery - lh // 2))
        return r

    def etiquette(x, y, libelle, fond, encre, f=None, pad=7, haut=15):
        """Petit bandeau colore, dimensionne sur son texte. Renvoie le x suivant."""
        f = f or F_PETIT
        lw, lh = f.size(libelle)
        r = pygame.Rect(x, y, lw + pad * 2, haut)
        pygame.draw.rect(surface_hud, fond, r, border_radius=3)
        img = f.render(libelle, True, encre)
        surface_hud.blit(img, (x + pad, r.centery - lh // 2))
        return x + r.width

    def panneau(x, y, w, h, alpha=218):
        pygame.draw.rect(surface_hud, (10, 9, 16, alpha), pygame.Rect(x, y, w, h))

    def hud_edition():
        p = projet.courante()
        creuse = bool(p and projet.sel > 0 and p.op == SOUSTRAIT)

        # ---- bandeau du haut : tout est mesure, rien ne se chevauche
        HB = 26
        panneau(0, 0, LARGEUR, HB)
        if etat["observation"]:
            etiquette(8, 5, "OBSERVATION", (44, 38, 62), ACCENT)
            texte(122, 5, "L1 ou R1 pour choisir une pièce", F_PETIT, GRIS)
        elif p:
            y = 5
            x = 8
            x = etiquette(x, y, "%d/%d" % (projet.sel + 1, len(projet.prims)),
                          (44, 38, 62), DOUX) + 8
            x = etiquette(x, y, "CREUX" if creuse else "MATIÈRE",
                          ROUGE if creuse else VERT, (12, 10, 18)) + 8
            x = etiquette(x, y, NOMS_FORMES[p.forme], (30, 26, 42), GRIS) + 8
            if any(abs(a) > 0.01 for a in p.rot):
                vifs = [i for i in range(3) if abs(p.rot[i]) > 0.01]
                if len(vifs) == 1:
                    rot = "PIVOT %s %.0f°" % (NOMS_AXES[vifs[0]], p.rot[vifs[0]])
                else:
                    rot = "PIVOT %.0f %.0f %.0f" % tuple(p.rot)
                x = etiquette(x, y, rot, (46, 34, 66), ACCENT) + 8
            dims = p.resume_dimensions() + " mm"
            lw, lh = F_PETIT.size(dims)
            if x + lw + 12 < LARGEUR:
                surface_hud.blit(F_PETIT.render(dims, True, CLAIR),
                                 (LARGEUR - 10 - lw, HB // 2 - lh // 2))

        # ---- message passager, juste au dessus du bandeau du bas
        if etat["flash_t"] > 0:
            lw, lh = F_PETIT.size(etat["flash"])
            r = pygame.Rect(LARGEUR // 2 - lw // 2 - 12, HAUTEUR - 66, lw + 24, 22)
            pygame.draw.rect(surface_hud, (24, 20, 36, 240), r, border_radius=11)
            pygame.draw.rect(surface_hud, (110, 92, 150), r, 1, border_radius=11)
            surface_hud.blit(F_PETIT.render(etat["flash"], True, ACCENT),
                             (r.centerx - lw // 2, r.centery - lh // 2))

        # ---- bandeau du bas : ce que font les boutons, ici et maintenant
        BB = 32
        panneau(0, HAUTEUR - BB, LARGEUR, BB)
        yb = HAUTEUR - BB // 2

        if etat["observation"]:
            msg = "STICK G AVANCE, STICK D REGARDE"
            lw, lh = F_PETIT.size(msg)
            r = pygame.Rect(8, yb - 10, lw + 16, 20)
            pygame.draw.rect(surface_hud, (44, 38, 62), r, border_radius=4)
            surface_hud.blit(F_PETIT.render(msg, True, ACCENT),
                             (r.x + 8, r.centery - lh // 2))
            x = r.right + 14
        elif p:
            a_dr, s_dr, a_av, s_av = axes_ecran()
            if "r1" in enfonce and "l1" in enfonce:
                croixtxt = "CROIX : PIVOTER 15°"
            elif "r1" in enfonce:
                if p.forme == SPHERE:
                    croixtxt = "TAILLE : DIAMÈTRE"
                elif p.forme in (CYLINDRE, CONE):
                    croixtxt = "TAILLE  %s%s DIAM   %s%s Z" % (
                        chr(9664), chr(9654), chr(9650), chr(9660))
                else:
                    croixtxt = "TAILLE  %s%s %s   %s%s Z" % (
                        chr(9664), chr(9654), NOMS_AXES[a_dr],
                        chr(9650), chr(9660))
            elif "l1" in enfonce:
                croixtxt = "CROIX : HAUTEUR Z"
            else:
                croixtxt = "%s%s %s   %s%s %s" % (chr(9664), chr(9654), NOMS_AXES[a_dr],
                                                  chr(9650), chr(9660), NOMS_AXES[a_av])
            lw, lh = F_PETIT.size(croixtxt)
            r = pygame.Rect(8, yb - 10, lw + 16, 20)
            pygame.draw.rect(surface_hud, (44, 38, 62), r, border_radius=4)
            surface_hud.blit(F_PETIT.render(croixtxt, True, ACCENT),
                             (r.x + 8, r.centery - lh // 2))
            x = r.right + 14
        else:
            x = 8

        def bouton(x, lib, act):
            lw, lh = F_PETIT.size(lib)
            pygame.draw.circle(surface_hud, (60, 53, 80), (x + 9, yb), 9)
            img = F_PETIT.render(lib, True, ACCENT)
            surface_hud.blit(img, (x + 9 - img.get_width() // 2, yb - lh // 2))
            aw, ah = F_PETIT.size(act)
            surface_hud.blit(F_PETIT.render(act, True, DOUX),
                             (x + 23, yb - ah // 2))
            return x + 23 + aw + 14

        x = bouton(x, "A", "TENIR = AJOUTER")
        if not etat["observation"]:
            x = bouton(x, "X", "CREUSER" if not creuse else "MATIÈRE")
        x = bouton(x, "B", "ANNULER")
        aide = "SELECT = AIDE"
        aw, ah = F_PETIT.size(aide)
        if x + aw + 10 < LARGEUR:
            surface_hud.blit(F_PETIT.render(aide, True, GRIS),
                             (LARGEUR - 10 - aw, yb - ah // 2))

    LIGNES_AIDE = [
        ("CROIX", "Seule façon de déplacer une pièce, 1 mm", ""),
        ("L1 + CROIX", "Déplace en hauteur", ""),
        ("R1 + CROIX", "Taille : haut et bas pour la hauteur Z", ""),
        ("L1+R1+CROIX", "Fait pivoter la pièce par pas de 15°", ""),
        ("STICK G", "Avance, recule, pas de côté", ""),
        ("STICK D", "Tourne la tête sur place, vue libre", ""),
        ("L2 R2", "Recule ou rapproche le point de vue", ""),
        ("L1", "Pièce précédente, puis observation", ""),
        ("R1", "Pièce suivante, puis observation", ""),
        ("A", "Valide, rien de plus", "la roue des pièces"),
        ("B", "Annuler", "supprimer la pièce"),
        ("LA ROUE", "Ajouter, dupliquer, supprimer", ""),
        ("X", "Matière ou creux", "faire tomber la pièce"),
        ("Y", "Changer la forme", "centrer sur celle du dessous"),
        ("CLIC STICK G", "Centre la pièce sur celle du dessous", ""),
        ("CLIC STICK D", "Fait tomber la pièce sur ce qu'il y a dessous", ""),
        ("SELECT", "Cette aide", "valeurs exactes"),
        ("START", "Menu, sauver, charger, exporter", "recadrer la vue"),
    ]
    NOTE_AIDE = "Les pièces de matière se collent entre elles et sur le plateau."

    def hud_aide():
        panneau(0, 0, LARGEUR, HAUTEUR, 243)
        pygame.draw.rect(surface_hud, (60, 53, 80),
                         pygame.Rect(18, 16, LARGEUR - 36, HAUTEUR - 32), 1)
        texte(30, 22, "COMMANDES", F_GRAND, ACCENT)
        texte_droite(LARGEUR - 30, 27, "N'IMPORTE QUEL BOUTON POUR FERMER", F_PETIT, GRIS)
        y = 50
        for lib, principal, second in LIGNES_AIDE:
            texte(30, y, lib, F_PETIT, ACCENT)
            texte(140, y, principal, F_PETIT, CLAIR)
            if second:
                texte(400, y, "maintenu : " + second, F_PETIT, GRIS)
            y += 20
        pygame.draw.rect(surface_hud, (36, 30, 51, 240),
                         pygame.Rect(30, y + 2, LARGEUR - 60, 34))
        texte(44, y + 6, "maintenir un bouton déclenche son action secondaire",
              F_PETIT, DOUX)
        texte(44, y + 19, NOTE_AIDE, F_PETIT, GRIS)

    ACCUEIL = [
        ("LA CROIX DÉPLACE",
         "La pièce verte suit la croix, un millimètre par appui.",
         "Stick gauche pour avancer, stick droit pour regarder."),
        ("MAINTIENS A POUR AJOUTER",
         "Une roue apparaît : cube, cylindre, sphère, cône, trou.",
         "Tu choisis au stick, tu relâches, la pièce se pose."),
        ("X CREUSE",
         "Une pièce rouge creuse la matière au lieu de l'ajouter.",
         "C'est comme ça qu'on fait un trou. B annule toujours."),
    ]

    def hud_accueil():
        panneau(0, 0, LARGEUR, HAUTEUR, 250)
        i = min(etat["accueil_i"], len(ACCUEIL) - 1)
        titre, l1, l2 = ACCUEIL[i]
        texte(30, 26, "neoFORGE", F_PETIT, ACCENT)
        texte_droite(LARGEUR - 30, 26, "%d / 3" % (i + 1), F_PETIT, GRIS)
        t = F_GRAND.render(titre, True, CLAIR)
        surface_hud.blit(t, (LARGEUR // 2 - t.get_width() // 2, 170))
        for k, ligne in enumerate((l1, l2)):
            t = F_NORM.render(ligne, True, DOUX)
            surface_hud.blit(t, (LARGEUR // 2 - t.get_width() // 2, 220 + k * 24))
        for k in range(3):
            c = ACCENT if k == i else (60, 53, 80)
            pygame.draw.circle(surface_hud, c, (LARGEUR // 2 - 20 + k * 20, 300), 5)
        t = F_PETIT.render("appuie sur un bouton", True, GRIS)
        surface_hud.blit(t, (LARGEUR // 2 - t.get_width() // 2, 340))

    def cadre_liste(titre, elements, index, vide, bas):
        panneau(0, 0, LARGEUR, HAUTEUR, 243)
        pygame.draw.rect(surface_hud, (60, 53, 80),
                         pygame.Rect(80, 50, LARGEUR - 160, HAUTEUR - 110), 1)
        texte(100, 62, titre, F_GRAND, ACCENT)
        if not elements:
            texte(100, 110, vide, F_NORM, GRIS)
        else:
            debut = max(0, min(index - 5, len(elements) - 11))
            for i in range(debut, min(len(elements), debut + 11)):
                y = 100 + (i - debut) * 24
                if i == index:
                    pygame.draw.rect(surface_hud, (58, 44, 78, 240),
                                     pygame.Rect(92, y - 3, LARGEUR - 184, 24))
                texte(104, y, elements[i], F_NORM, ACCENT if i == index else CLAIR)
        texte(100, HAUTEUR - 52, bas, F_PETIT, GRIS)

    def hud_exports():
        fics = lister_exports()
        panneau(0, 0, LARGEUR, HAUTEUR, 245)
        pygame.draw.rect(surface_hud, (60, 53, 80),
                         pygame.Rect(24, 20, LARGEUR - 48, HAUTEUR - 40), 1)
        texte(40, 30, "FICHIERS EXPORTÉS", F_GRAND, ACCENT)
        texte_droite(LARGEUR - 40, 36,
                     "%d fichier%s" % (len(fics), "s" if len(fics) > 1 else ""),
                     F_PETIT, GRIS)

        if not fics:
            texte(40, 74, "Aucun export pour l'instant.", F_NORM, GRIS)
            texte(40, 96, "Menu, puis EXPORTER STL ou EXPORTER 3MF.", F_PETIT, GRIS)
        else:
            debut = max(0, min(etat["exp_i"] - 2, len(fics) - 5))
            for i in range(debut, min(len(fics), debut + 5)):
                n, o, m = fics[i]
                y = 72 + (i - debut) * 21
                if i == etat["exp_i"]:
                    pygame.draw.rect(surface_hud, (58, 44, 78, 240),
                                     pygame.Rect(34, y - 3, LARGEUR - 68, 21))
                c = ACCENT if i == etat["exp_i"] else CLAIR
                texte(44, y, n[:28], F_PETIT, c)
                texte(370, y, taille_lisible(o), F_PETIT, GRIS)
                texte(450, y, time.strftime("%d/%m  %H:%M", time.localtime(m)),
                      F_PETIT, GRIS)
            if len(fics) > 5:
                texte_droite(LARGEUR - 44, 72 + 5 * 21,
                             "et %d autre%s" % (len(fics) - 5,
                                                "s" if len(fics) - 5 > 1 else ""),
                             F_PETIT, GRIS)

        yb = 190
        pygame.draw.line(surface_hud, (60, 53, 80), (40, yb), (LARGEUR - 40, yb))
        texte(40, yb + 10, "RÉCUPÉRER LES FICHIERS SUR TON ORDINATEUR",
              F_PETIT, ACCENT)

        ip, port = PARTAGE["ip"], PARTAGE["port"]
        y = yb + 34
        texte(44, y, "1", F_NORM, ACCENT)
        texte(66, y, "Dans un navigateur, le plus simple", F_PETIT, CLAIR)
        if ip and port:
            texte(66, y + 18, "http://%s:%d" % (ip, port), F_NORM, VERT)
        else:
            texte(66, y + 18, "réseau indisponible, vérifie le wifi", F_PETIT, ROUGE)
        texte(66, y + 40, "Aucun mot de passe. Marche aussi depuis un téléphone.",
              F_PETIT, GRIS)

        y += 72
        texte(44, y, "2", F_NORM, ACCENT)
        texte(66, y, "Dans l'explorateur Windows", F_PETIT, CLAIR)
        chemin = chemin_windows(ip) or DOSSIER_EXPORT
        place = LARGEUR - 66 - 44
        while chemin and F_NORM.size(chemin)[0] > place:
            chemin = chemin[:-2]
        texte(66, y + 18, chemin, F_NORM, VERT)
        texte(66, y + 40, "Identifiants : root  et  linux    coche Mémoriser",
              F_PETIT, GRIS)

        texte(40, HAUTEUR - 40, "B revient au menu", F_PETIT, GRIS)
        if fics:
            texte_droite(LARGEUR - 40, HAUTEUR - 40,
                         "X supprime le fichier choisi", F_PETIT, GRIS)

    def hud_menu():
        cadre_liste("MENU", libelles_menu(), etat["menu_i"], "",
                    "A valide, B revient au modèle")

    def hud_fichiers():
        cadre_liste("CHARGER UN PROJET", lister_projets(), etat["fic_i"],
                    "aucun projet enregistré", "A charge, B revient au menu")

    def hud_champs():
        ch = champs_courants()
        libelles = ["%-14s %g" % (nom, valeur_champ(ref)) for nom, ref in ch]
        cadre_liste("VALEURS EXACTES", libelles, etat["champ_i"], "",
                    "A modifie la valeur, B revient au modèle")

    def hud_pave():
        panneau(0, 0, LARGEUR, HAUTEUR, 243)
        pygame.draw.rect(surface_hud, (60, 53, 80), pygame.Rect(150, 50, 340, 380), 1)
        nom = etat["champ_actif"][0] if etat["champ_actif"] else ""
        texte(172, 64, nom, F_NORM, ACCENT)
        pygame.draw.rect(surface_hud, (26, 22, 38, 245), pygame.Rect(172, 90, 296, 34))
        texte(182, 98, (etat["saisie"] or "_"), F_GRAND, CLAIR)
        for i, t in enumerate(PAVE):
            if i < 12:
                col, lig = i % 3, i // 3
                r = pygame.Rect(172 + col * 100, 138 + lig * 46, 92, 38)
            else:
                r = pygame.Rect(172 + (i - 12) * 150, 330, 142, 38)
            fond = (58, 44, 78) if i == etat["pave_i"] else (26, 22, 38)
            pygame.draw.rect(surface_hud, fond, r, border_radius=3)
            img = F_NORM.render(t, True, ACCENT if i == etat["pave_i"] else CLAIR)
            surface_hud.blit(img, (r.x + (r.w - img.get_width()) // 2,
                                   r.y + (r.h - img.get_height()) // 2))
        texte(172, 386, "croix pour choisir, A pour appuyer, B pour sortir", F_PETIT, GRIS)

    def cadre_selection_inutilisee(mvp):
        p = projet.courante()
        if not p:
            return
        ex, ey, ez = p.demi_etendue()
        cr = [math.radians(a) for a in p.rot]
        cx, sx = math.cos(cr[0]), math.sin(cr[0])
        cy, sy = math.cos(cr[1]), math.sin(cr[1])
        cz, sz = math.cos(cr[2]), math.sin(cr[2])

        def tr(x, y, z):
            y, z = y * cx - z * sx, y * sx + z * cx
            x, z = x * cy + z * sy, -x * sy + z * cy
            x, y = x * cz - y * sz, x * sz + y * cz
            return (x + p.pos[0], y + p.pos[1], z + p.pos[2])

        coins = [tr(ex if i & 1 else -ex, ey if i & 2 else -ey, ez if i & 4 else -ez)
                 for i in range(8)]
        aretes = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3),
                  (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)]
        pts = []
        for a, b in aretes:
            pts += list(coins[a]) + [0, 0, 1] + list(coins[b]) + [0, 0, 1]
        remplir(B_SEL, np.array(pts, dtype=np.float32))
        del mvp

    def hud_roue():
        cx, cy = LARGEUR // 2, HAUTEUR // 2 - 4
        rx, ry = 176, 118
        panneau(0, 0, LARGEUR, HAUTEUR, 185)
        sel = etat["roue"]
        for i, (nom, _) in enumerate(ROUE):
            ang = math.radians(-90 + i * PAS_ROUE)
            pilule(cx + math.cos(ang) * rx, cy + math.sin(ang) * ry,
                   nom, i == sel, F_NORM, pad=16, haut=30)
        pygame.draw.circle(surface_hud, (12, 10, 18), (cx, cy), 56)
        pygame.draw.circle(surface_hud, (72, 63, 96), (cx, cy), 56, 1)
        if sel is None or sel < 0:
            t1, t2 = "CHOISIS", "stick ou croix"
        else:
            t1, t2 = ROUE[sel][0], "relâche A"
        img = F_NORM.render(t1, True, CLAIR)
        surface_hud.blit(img, (cx - img.get_width() // 2, cy - 15))
        img = F_PETIT.render(t2, True, GRIS)
        surface_hud.blit(img, (cx - img.get_width() // 2, cy + 4))

    DUREE_LANCEMENT = 2.0

    def police_grasse(taille):
        if CHEMIN_POLICE:
            gras = CHEMIN_POLICE.replace("DejaVuSansMono.ttf",
                                         "DejaVuSansMono-Bold.ttf")
            if gras != CHEMIN_POLICE and os.path.exists(gras):
                return pygame.font.Font(gras, taille)
        return police(taille)

    def calque_titre(couleur):
        petit = police_grasse(13).render("neoForge", False, couleur)
        return pygame.transform.scale(
            petit, (petit.get_width() * 5, petit.get_height() * 5))

    TITRE_COEUR = calque_titre((198, 155, 240))
    TITRE_GAUCHE = calque_titre((255, 60, 150))
    TITRE_DROITE = calque_titre((70, 200, 255))
    VOILE = pygame.Surface((LARGEUR, HAUTEUR), pygame.SRCALPHA)
    for _y in range(0, HAUTEUR, 3):
        pygame.draw.line(VOILE, (0, 0, 0, 75), (0, _y), (LARGEUR, _y))

    def hud_lancement():
        surface_hud.fill((0, 0, 0, 255))
        t = time.time() - etat["t_lancement"]
        if t < 0.45:
            a = t / 0.45
        elif t > DUREE_LANCEMENT - 0.5:
            a = max(0.0, (DUREE_LANCEMENT - t) / 0.5)
        else:
            a = 1.0
        x = LARGEUR // 2 - TITRE_COEUR.get_width() // 2
        y = HAUTEUR // 2 - TITRE_COEUR.get_height() // 2
        TITRE_GAUCHE.set_alpha(int(165 * a))
        TITRE_DROITE.set_alpha(int(165 * a))
        TITRE_COEUR.set_alpha(int(255 * a))
        surface_hud.blit(TITRE_GAUCHE, (x - 5, y))
        surface_hud.blit(TITRE_DROITE, (x + 5, y))
        surface_hud.blit(TITRE_COEUR, (x, y))
        surface_hud.blit(VOILE, (0, 0))

    def dessiner_hud():
        surface_hud.fill((0, 0, 0, 0))
        e = etat["ecran"]
        if e == "lancement":
            hud_lancement()
        elif e == "accueil":
            hud_accueil()
        elif e == "aide":
            hud_aide()
        elif e == "menu":
            hud_menu()
        elif e == "fichiers":
            hud_fichiers()
        elif e == "exports":
            hud_exports()
        elif e == "champs":
            hud_champs()
        elif e == "pave":
            hud_pave()
        else:
            hud_edition()
            if etat["roue"] is not None:
                hud_roue()

        donnees = pygame.image.tostring(surface_hud, "RGBA", True)
        G.glUseProgram(prog_hud)
        G.glActiveTexture(G.GL_TEXTURE0)
        G.glBindTexture(G.GL_TEXTURE_2D, TEX_HUD)
        G.glTexImage2D(G.GL_TEXTURE_2D, 0, G.GL_RGBA, LARGEUR, HAUTEUR, 0,
                       G.GL_RGBA, G.GL_UNSIGNED_BYTE, donnees)
        G.glTexParameteri(G.GL_TEXTURE_2D, G.GL_TEXTURE_MIN_FILTER, G.GL_NEAREST)
        G.glTexParameteri(G.GL_TEXTURE_2D, G.GL_TEXTURE_MAG_FILTER, G.GL_NEAREST)
        G.glTexParameteri(G.GL_TEXTURE_2D, G.GL_TEXTURE_WRAP_S, G.GL_CLAMP_TO_EDGE)
        G.glTexParameteri(G.GL_TEXTURE_2D, G.GL_TEXTURE_WRAP_T, G.GL_CLAMP_TO_EDGE)
        G.glUniform1i(H_TEX, 0)

        G.glDisable(G.GL_DEPTH_TEST)
        G.glEnable(G.GL_BLEND)
        G.glBlendFunc(G.GL_SRC_ALPHA, G.GL_ONE_MINUS_SRC_ALPHA)
        G.glBindBuffer(G.GL_ARRAY_BUFFER, B_QUAD)
        G.glEnableVertexAttribArray(H_POS)
        G.glVertexAttribPointer(H_POS, 2, G.GL_FLOAT, G.GL_FALSE, 16, ctypes.c_void_p(0))
        G.glEnableVertexAttribArray(H_UV)
        G.glVertexAttribPointer(H_UV, 2, G.GL_FLOAT, G.GL_FALSE, 16, ctypes.c_void_p(8))
        G.glDrawArrays(G.GL_TRIANGLES, 0, 6)
        G.glDisableVertexAttribArray(H_POS)
        G.glDisableVertexAttribArray(H_UV)
        G.glDisable(G.GL_BLEND)
        G.glEnable(G.GL_DEPTH_TEST)

    # ---------------------------------------------------------------- boucle

    G.glEnable(G.GL_DEPTH_TEST)
    G.glClearColor(0.051, 0.047, 0.078, 1.0)
    G.glViewport(0, 0, LARGEUR, HAUTEUR)

    horloge = pygame.time.Clock()
    reconstruire()
    if lister_boutons:
        print("Appuie sur les boutons, ferme la fenetre pour sortir.")

    while not etat["quitter"]:
        dt = horloge.tick(60) / 1000.0
        maintenant = time.time()

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                etat["quitter"] = True
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    if etat["ecran"] == "edition":
                        etat["quitter"] = True
                    else:
                        etat["ecran"] = "edition"
                elif ev.key == pygame.K_h:
                    etat["ecran"] = "aide" if etat["ecran"] != "aide" else "edition"
                elif ev.key in TOUCHES:
                    presser(TOUCHES[ev.key])
                elif ev.key in ANALOG:
                    axes_clavier[ANALOG[ev.key]] = True
            elif ev.type == pygame.KEYUP:
                if ev.key in TOUCHES:
                    relacher(TOUCHES[ev.key])
                elif ev.key in ANALOG:
                    axes_clavier[ANALOG[ev.key]] = False
            elif ev.type == pygame.JOYBUTTONDOWN:
                if lister_boutons:
                    print("bouton", ev.button)
                nom = BOUTONS_MANETTE.get(ev.button)
                if nom:
                    presser(nom)
            elif ev.type == pygame.JOYBUTTONUP:
                nom = BOUTONS_MANETTE.get(ev.button)
                if nom:
                    relacher(nom)
            elif ev.type == pygame.JOYHATMOTION:
                for cle, nom in CHAPEAU.items():
                    if ev.value == cle:
                        presser(nom)
                    else:
                        relacher(nom)
            elif ev.type == pygame.JOYAXISMOTION:
                for (idx, sens), nom in AXES_COMMANDE.items():
                    if ev.axis != idx:
                        continue
                    actif = (ev.value * sens) > 0.55
                    if actif and not etat_axes.get(nom):
                        etat_axes[nom] = True
                        presser(nom)
                    elif not actif and etat_axes.get(nom):
                        etat_axes[nom] = False
                        relacher(nom)

        for nom in list(enfonce.keys()):
            info = enfonce[nom]
            duree = maintenant - info["t"]
            if nom in SECONDAIRE and not info["fait"] and duree >= MAINTIEN_S:
                info["fait"] = True
                maintien(nom)
            elif nom in REPETE and duree >= 0.32 and maintenant - info["rep"] >= 0.08:
                info["rep"] = maintenant
                if etat["ecran"] == "edition":
                    croix(nom, 5.0 if duree > 1.4 else 1.0)
                else:
                    appui(nom)

        gx = (1 if axes_clavier.get("gx+") else 0) - (1 if axes_clavier.get("gx-") else 0)
        gy = (1 if axes_clavier.get("gy+") else 0) - (1 if axes_clavier.get("gy-") else 0)
        dx = (1 if axes_clavier.get("dx+") else 0) - (1 if axes_clavier.get("dx-") else 0)
        dy = (1 if axes_clavier.get("dy+") else 0) - (1 if axes_clavier.get("dy-") else 0)
        zoom = (1 if axes_clavier.get("zoom-") else 0) - (1 if axes_clavier.get("zoom+") else 0)

        for j in manettes:
            def lire(i):
                if i < 0 or i >= j.get_numaxes():
                    return 0.0
                try:
                    v = j.get_axis(i)
                except Exception:
                    return 0.0
                return v if abs(v) > 0.18 else 0.0
            gx += lire(AXES_STICKS[0])
            gy += lire(AXES_STICKS[1])
            dx += lire(AXES_STICKS[2])
            dy += lire(AXES_STICKS[3])

        zoom += (1 if "l2" in enfonce else 0) - (1 if "r2" in enfonce else 0)

        gx = max(-1.0, min(1.0, gx))
        gy = max(-1.0, min(1.0, gy))
        dx = max(-1.0, min(1.0, dx))
        dy = max(-1.0, min(1.0, dy))

        if etat["roue"] is not None:
            amp = math.hypot(gx, gy)
            if amp > 0.45:
                ang = math.degrees(math.atan2(gy, gx)) + 90.0
                etat["roue"] = int(round(ang / PAS_ROUE)) % len(ROUE)
            gx = gy = dx = dy = 0.0

        if etat["ecran"] == "edition" and etat["roue"] is None:
            if dx or dy:
                # stick droit : on tourne la tete sur place. L oeil ne bouge
                # pas d un millimetre, c est le point vise qui tourne autour
                # de lui, donc plus aucun point d ancrage au centre du plateau
                oeil = camera()
                etat["yaw"] += dx * 2.0 * dt
                etat["pitch"] = max(-1.35, min(1.35,
                                              etat["pitch"] + dy * 1.4 * dt))
                cp = math.cos(etat["pitch"])
                etat["cible"] = [
                    oeil[0] - etat["dist"] * cp * math.sin(etat["yaw"]),
                    oeil[1] - etat["dist"] * cp * math.cos(etat["yaw"]),
                    oeil[2] - etat["dist"] * math.sin(etat["pitch"])]
            if zoom:
                # les gachettes reculent et rapprochent l oeil, le regard
                # garde exactement la meme direction
                etat["dist"] = max(50.0, min(600.0,
                                             etat["dist"] + zoom * 170.0 * dt))
            if gx or gy:
                # stick gauche : haut et bas pour avancer et reculer dans l
                # axe du regard, gauche et droite pour les pas de cote
                cp = math.cos(etat["pitch"])
                sp = math.sin(etat["pitch"])
                sy = math.sin(etat["yaw"])
                cy = math.cos(etat["yaw"])
                regard = (-cp * sy, -cp * cy, -sp)     # vers ou l on regarde
                droite = (-cy, sy, 0.0)                # la droite de l ecran
                vit = 95.0 * dt
                av = -gy * vit
                lat = gx * vit
                for k in range(3):
                    etat["cible"][k] += regard[k] * av + droite[k] * lat
                # on borne l altitude de l oeil, pas celle du point vise
                oz = camera()[2]
                if oz < -40.0:
                    etat["cible"][2] += -40.0 - oz
                elif oz > 700.0:
                    etat["cible"][2] -= oz - 700.0

        if etat["sale"]:
            reconstruire()

        if (etat["ecran"] == "lancement"
                and time.time() - etat["t_lancement"] > DUREE_LANCEMENT):
            etat["ecran"] = etat["suite"]

        if etat["flash_t"] > 0:
            etat["flash_t"] -= dt

        mvp = mvp_courant()
        lum = (0.45, 0.35, 0.82)

        G.glClear(G.GL_COLOR_BUFFER_BIT | G.GL_DEPTH_BUFFER_BIT)
        G.glEnable(G.GL_DEPTH_TEST)

        dessiner_tampon(B_GRILLE, N_GRILLE, G.GL_LINES, (0.17, 0.16, 0.23), 1.0, mvp, lum)
        dessiner_tampon(B_BORD, N_BORD, G.GL_LINES, (0.36, 0.30, 0.47), 1.0, mvp, lum)

        if N_SOLIDE[0]:
            dessiner_tampon(B_SOLIDE, N_SOLIDE[0], G.GL_TRIANGLES,
                            (0.62, 0.56, 0.72), 0.0, mvp, lum)

        if etat["ecran"] in ("edition", "champs", "aide"):
            pr = None if etat["observation"] else projet.courante()
            creuse = bool(pr and projet.sel > 0 and pr.op == SOUSTRAIT)
            if N_FANTOME[0]:
                teinte = (0.96, 0.42, 0.42) if creuse else (0.38, 0.85, 0.58)
                G.glEnable(G.GL_BLEND)
                G.glBlendFunc(G.GL_SRC_ALPHA, G.GL_ONE_MINUS_SRC_ALPHA)
                G.glEnable(G.GL_CULL_FACE)
                G.glCullFace(G.GL_BACK)
                G.glDepthMask(G.GL_FALSE)
                # ce qui est cache par la matiere, tres attenue
                G.glDisable(G.GL_DEPTH_TEST)
                dessiner_tampon(B_FANTOME, N_FANTOME[0], G.GL_TRIANGLES,
                                teinte, 0.0, mvp, lum, 0.14, 0.35)
                # ce qui est visible, franc, decolle pour ne pas battre avec le solide
                G.glEnable(G.GL_DEPTH_TEST)
                dessiner_tampon(B_FANTOME, N_FANTOME[0], G.GL_TRIANGLES,
                                teinte, 0.0, mvp, lum, 0.5, 0.35)
                G.glDepthMask(G.GL_TRUE)
                G.glDisable(G.GL_CULL_FACE)
                G.glDisable(G.GL_BLEND)

        dessiner_hud()
        pygame.display.flip()

    pygame.quit()
    return 0


def main():
    args = sys.argv[1:]
    if "--autotest" in args:
        return autotest()
    if "--calibrer" in args:
        return calibrer()
    return lancer(plein_ecran="--plein-ecran" in args,
                  lister_boutons="--boutons" in args)


if __name__ == "__main__":
    sys.exit(main())
