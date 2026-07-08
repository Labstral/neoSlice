"""Tutoriel interactif pas à pas — neoSlice.

Architecture : QDialog top-level avec WA_TranslucentBackground.
Chaque étape est entièrement dessinée par un seul paintEvent (zéro widget
enfant). Le dialog a son propre HWND Windows : impossible d'avoir des fantômes
liés au compositing partagé avec la fenêtre principale.
"""
from __future__ import annotations
from dataclasses import dataclass

from PySide6.QtWidgets import QWidget, QDialog
from PySide6.QtCore import (
    Qt, QRect, QRectF, QPoint, QPointF, QEvent, Signal,
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QPainterPath, QFont, QBrush,
    QFontMetrics, QTextDocument,
)

from ui.styles.theme import (
    ACCENT, ACCENT_BRIGHT, TELE_GREEN,
    TEXT_PRIMARY, TEXT_SECONDARY, FONT_MONO,
    MANAGER as _T,
    FONT_MAIN,)

def _body_color() -> str:
    return _T.palette()["TEXT_SECONDARY"] if not _T.is_dark() else "#8AAABF"


# Glyphes ronds numérotés → chiffre simple (pour redessiner un badge propre).
def _is_pro() -> bool:
    """État Pro courant (tolérant : en cas d'erreur, on suppose non-Pro pour
    afficher l'explication d'upsell plutôt que de la masquer à tort)."""
    try:
        from core import licensing
        return bool(licensing.est_pro())
    except Exception:
        return False


# Glyphes ronds numérotés → chiffre simple (pour redessiner un badge propre).
_CIRCLED_TO_DIGIT = {
    "①": "1", "②": "2", "③": "3", "④": "4",
    "⑤": "5", "⑥": "6", "⑦": "7", "⑧": "8", "⑨": "9",
}
_BADGE_CACHE: dict = {}  # (digit, color) -> Path


def _badge_png(digit: str, color: str):
    """PNG d'un badge rond (cercle + chiffre centré sur l'encre), même design que
    les en-têtes du panneau gauche. Rendu en 2× pour la netteté, mis en cache."""
    key = (digit, color)
    if key in _BADGE_CACHE:
        return _BADGE_CACHE[key]
    from PySide6.QtGui import (QPixmap, QPainter, QColor, QPen, QFont as _QF,
                               QFontMetrics)
    from PySide6.QtCore import QPointF
    import tempfile, hashlib
    from pathlib import Path as _P
    S = 44          # taille widget 2× (badge final ~22px)
    D = 36          # diamètre du cercle 2×
    pix = QPixmap(S, S)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(3.2)
    p.setPen(pen)
    p.drawEllipse(QPointF(S / 2, S / 2), D / 2, D / 2)
    f = _QF(FONT_MAIN, 18, _QF.Bold)
    p.setFont(f)
    fm = QFontMetrics(f)
    br = fm.tightBoundingRect(digit)
    # Horizontal sur la chasse (alignement en colonne) ; vertical sur l'encre.
    bx = (S - fm.horizontalAdvance(digit)) / 2.0
    by = S / 2 - br.height() / 2 - br.y()
    p.drawText(QPointF(bx, by), digit)
    p.end()
    tag = hashlib.md5(f"{digit}{color}".encode()).hexdigest()[:8]
    out = _P(tempfile.gettempdir()) / f"neoslice_badge_{tag}.png"
    pix.save(str(out), "PNG")
    _BADGE_CACHE[key] = out
    return out


_COFFEE_SQ_CACHE: dict = {}  # tint_hex -> (Path, w, h) | False


def _coffee_square_path(tint_hex: str | None = None):
    """PNG du café (assets/coffee.png) recadré AU PLUS JUSTE → (Path, w, h).

    On recadre uniquement sur le contenu (boîte alpha), SANS canvas carré : ainsi
    la tasse se cale au bord gauche comme les glyphes voisins du tuto (pas de
    marge transparente qui la décalerait vers la droite). Le ratio est renvoyé
    pour l'afficher à hauteur fixe sans déformation. Comme le logo du topbar,
    l'image garde ses couleurs ; teinte en silhouette seulement si tint_hex.
    Mis en cache par couleur → (Path, w, h).
    """
    key = tint_hex or "_raw"
    if key in _COFFEE_SQ_CACHE:
        v = _COFFEE_SQ_CACHE[key]
        return v if v else None
    from pathlib import Path as _P
    src = _P(__file__).parent.parent.parent / "assets" / "coffee.png"
    if not src.exists():
        _COFFEE_SQ_CACHE[key] = False
        return None
    try:
        import numpy as _np
        from PySide6.QtGui import QPixmap, QImage, QPainter as _QP, QColor as _QC
        import tempfile, hashlib
        pix = QPixmap(str(src))
        img = pix.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        w, h = img.width(), img.height()
        ptr = img.constBits()
        arr = _np.frombuffer(ptr, _np.uint8).reshape(h, w, 4)
        ys, xs = _np.where(arr[:, :, 3] > 12)
        if len(xs) and len(ys):
            x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
            pix = pix.copy(x0, y0, x1 - x0 + 1, y1 - y0 + 1)
        # Teinte = silhouette monochrome dans la couleur des autres icônes
        if tint_hex:
            tinted = QPixmap(pix.size())
            tinted.fill(Qt.transparent)
            tp = _QP(tinted)
            tp.drawPixmap(0, 0, pix)
            tp.setCompositionMode(_QP.CompositionMode.CompositionMode_SourceIn)
            tp.fillRect(tinted.rect(), _QC(tint_hex))
            tp.end()
            pix = tinted
        tag = hashlib.md5(f"{src}{src.stat().st_mtime}{key}".encode()).hexdigest()[:8]
        out = _P(tempfile.gettempdir()) / f"neoslice_coffee_tight_{tag}.png"
        if not out.exists():
            pix.save(str(out), "PNG")
        res = (out, pix.width(), pix.height())
        _COFFEE_SQ_CACHE[key] = res
        return res
    except Exception:
        _COFFEE_SQ_CACHE[key] = False
        return None


def should_show_tutorial() -> bool:
    try:
        from ui.components.welcome_dialog import _load_prefs
        return not _load_prefs().get("tutorial_done", False)
    except Exception:
        return False


def _mark_done() -> None:
    try:
        from ui.components.welcome_dialog import _load_prefs, _save_prefs
        p = _load_prefs()
        p["tutorial_done"] = True
        _save_prefs(p)
    except Exception:
        pass


@dataclass
class _Step:
    target: str | None
    title: str
    body: str
    pad: int = 16
    pro: bool = False   # etape presentant une fonctionnalite Pro (gating + tuto Pro)
    no_auto_lock: bool = False  # ne pas ajouter la note « Reserve a Pro » (corps deja complet)


_STEPS_FR: list[_Step] = [
    _Step(
        None,
        "Bienvenue dans neoSlice",
        "neoSlice analyse votre fichier STL, OBJ ou 3MF et génère automatiquement "
        "les paramètres d'impression optimaux pour votre imprimante.\n\n"
        "Désormais compatible avec <b>5 slicers</b> — Bambu Studio, OrcaSlicer, "
        "PrusaSlicer, CrealityPrint et ElegooSlicer — et <b>plus de 80 marques / "
        "600 imprimantes</b> : Bambu Lab, Creality, Prusa, Anycubic, Elegoo, Sovol, "
        "Qidi, Flashforge, Voron et bien d'autres.\n\n"
        "Ce guide vous présente le workflow complet, du fichier à l'export, ainsi "
        "que les fonctionnalités <b>Pro</b>.\n"
        "Cliquez sur <b>Suivant</b> pour commencer.",
    ),
    _Step(
        "settings",
        "Première étape : choisissez votre slicer de sortie",
        "La toute première chose à faire : cliquez sur la <b>roue de réglages</b> "
        "<span style='font-family:\"Segoe MDL2 Assets\";font-size:11pt;color:#E8F4FF;'>&#xE713;</span> "
        "(en haut à droite) et sélectionnez votre <b>slicer de sortie</b> — "
        "<b>Bambu Studio</b>, <b>OrcaSlicer</b>, <b>PrusaSlicer</b>, "
        "<b>CrealityPrint</b> ou <b>ElegooSlicer</b>.\n\n"
        "C'est essentiel : <b>toutes les imprimantes ne sont pas compatibles avec "
        "tous les slicers</b>. Le catalogue d'imprimantes <b>s'adapte au slicer "
        "choisi</b> — par exemple, les <b>Prusa</b> (XL, CORE One…) n'apparaissent "
        "qu'en sélectionnant <b>PrusaSlicer</b> ou <b>OrcaSlicer</b>.\n\n"
        "Choisissez donc d'abord votre slicer pour voir apparaître l'imprimante que "
        "vous cherchez.",
        pad=10,
    ),
    _Step(
        "config",
        "① Configuration — Imprimante, Filament & Plateau",
        "Sélectionnez votre <b>imprimante cible</b> et votre <b>diamètre de buse</b>, "
        "puis cliquez sur <b>VALIDER</b>.\n"
        "Faites de même pour votre <b>filament</b>.\n\n"
        "Choisissez enfin votre <b>type de plateau</b> : la liste <b>s'adapte à "
        "votre slicer</b> (plateaux Bambu Studio / OrcaSlicer, ou sheets "
        "PrusaSlicer), et neoSlice ajuste automatiquement les températures et "
        "l'adhérence.",
        pad=12,
    ),
    _Step(
        "drop",
        "② Import STL / OBJ / 3MF",
        "Glissez votre <b>fichier STL, OBJ ou 3MF</b> dans cette zone, "
        "ou cliquez pour ouvrir l'explorateur de fichiers.\n\n"
        "neoSlice analyse automatiquement la géométrie :\n"
        "<b>surplombs · stabilité · zones fragiles</b>\n"
        "<b>volume & dimensions · orientation optimale</b>",
        pad=12,
    ),
    _Step(
        "intent",
        "③ Instruction Mission",
        "Ouvrez chaque accordéon pour choisir vos critères :\n"
        "<b>Qualité · Résistance · Vitesse · Supports · Adhérence · Usage · Mode</b>\n\n"
        "Le groupe <b>Mode</b> permet d'activer :\n"
        "— <b>Silencieux</b> : vitesses –40 % pour moins de bruit\n"
        "— <b>Multicolore (AMS Bambu / MMU Prusa)</b> : active la <b>prime tower</b> "
        "(tour de purge qui stabilise les changements de couleur) et le <b>flush</b> "
        "(purge automatique de la buse entre chaque filament)\n\n"
        "Sauvegardez vos combinaisons favorites en présets, "
        "puis cliquez sur <b>GÉNÉRER CONFIGURATION →</b>.",
        pad=12,
    ),
    _Step(
        "statusbar",
        "④ Export vers votre slicer",
        "Une fois la configuration générée, le <b>bouton d'export</b> s'active.\n\n"
        "neoSlice génère un fichier <b>.3MF</b> avec tous les paramètres "
        "optimisés selon votre matériau et la géométrie de la pièce.\n\n"
        "Choisissez votre <b>slicer de sortie</b> (Bambu Studio, OrcaSlicer, "
        "PrusaSlicer, CrealityPrint ou ElegooSlicer) dans les réglages — tout le "
        "logiciel s'adapte : catalogue "
        "d'imprimantes, plateaux et bouton d'export.\n\n"
        "Des <b>alertes matériau</b> peuvent apparaître dans le panneau d'analyse : "
        "risque de warping, séchage recommandé, incompatibilité multi-matériau "
        "(AMS/MMU)…",
        pad=6,
    ),
    _Step(
        "diag",
        "⑤ Diagnostic IA — corriger une impression ratée",
        "Une impression ratée ? Cliquez sur <b>DIAGNOSTIC IA</b>.\n\n"
        "Prenez ou chargez une <b>photo</b> de votre pièce : l'intelligence "
        "artificielle identifie le défaut — <b>stringing, warping, sous-extrusion, "
        "décollement…</b> — et vous donne les <b>corrections concrètes</b> à "
        "appliquer.\n\n"
        "<b>Fonctionnalité neoSlice Pro</b> (essais gratuits inclus).",
        pad=10,
        pro=True,
    ),
    _Step(
        "pro",
        "⑥ Espace Pro — gérez votre activité",
        "Le bouton <b>ESPACE PRO</b> ouvre votre hub de gestion complet :\n\n"
        "— <b>Tableau de bord</b> : chiffre d'affaires, payé, dû, stock\n"
        "— <b>Bobines</b> : suivi de votre stock de filament (grammes & valeur)\n"
        "— <b>Devis</b> : calcul du coût réel + devis PDF professionnel\n"
        "— <b>Facturation</b> : factures aux normes (TVA & devise de votre pays)\n"
        "— <b>Clients</b> : historique devis + factures et CA payé / dû par client\n\n"
        "<b>Fonctionnalité neoSlice Pro.</b>",
        pad=10,
        pro=True,
    ),
    _Step(
        "oen",
        "⑦ Oen — votre assistant IA local",
        "La <b>sphère</b> en bas à gauche de la vue 3D ouvre <b>Oen</b>, votre "
        "assistant IA <b>100 % local et hors ligne</b> (aucune donnée envoyée).\n\n"
        "Oen vous aide sur :\n"
        "— <b>Réglages & choix</b> : matériau, profil, paramètres d'impression\n"
        "— <b>Dépannage & entretien</b> de votre machine (toutes marques)\n"
        "— <b>Votre atelier</b> : stock de bobines, devis, coûts, rentabilité\n\n"
        "Il connaît votre imprimante, vos paramètres et l'analyse de la pièce en "
        "cours. Le bouton <b>Réflexion</b> le fait raisonner avant de répondre "
        "(plus précis). Sa base de connaissances se met à jour depuis les réglages.\n\n"
        "<b>Fonctionnalité neoSlice Pro</b> — installation optionnelle depuis les réglages.",
        pad=14,
        pro=True,
    ),
    _Step(
        "color",
        "⑧ Export multicouleur",
        "Après l'export d'un fichier <b>multicouleur</b> (assemblage de couleurs ou "
        "STL peint dans Bambu Studio), neoSlice calcule le <b>poids de filament par "
        "couleur</b>, colore l'aperçu 3D en direct, vous laisse <b>associer vos "
        "bobines</b> et <b>décompte le stock</b> de l'Espace Pro automatiquement.\n\n"
        "Idéal pour chiffrer précisément une pièce multicolore et suivre votre "
        "consommation réelle.\n\n"
        "<b>Fonctionnalité neoSlice Pro.</b>",
        pad=12,
        pro=True,
    ),
    _Step(
        "topbar",
        "⑨ Barre de titre",
        "À droite de la barre, quatre raccourcis sont disponibles à tout moment :"
        "<br><br>"
        "<table cellspacing='0' cellpadding='0' width='100%'>"
        "<tr>"
        "<td width='28' align='center' valign='top' style='padding-top:1px;'>"
        "<span style='font-family:\"Segoe MDL2 Assets\";font-size:11pt;color:#E8F4FF;'>&#xE713;</span>"
        "</td>"
        "<td valign='top'>Ouvrir les réglages : thème, langue, dossier "
        "d'export et statut neoSlice Pro.</td>"
        "</tr>"
        "<tr><td colspan='2' height='10'></td></tr>"
        "<tr>"
        "<td width='28' align='center' valign='top' style='padding-top:1px;'>"
        "<span style='font-family:\"Segoe MDL2 Assets\";font-size:11pt;color:#E8F4FF;'>&#xE8BD;</span>"
        "</td>"
        "<td valign='top'>Signaler un bug ou partager votre expérience."
        " Ouvre un formulaire en ligne&nbsp;; vos retours sont lus personnellement.</td>"
        "</tr>"
        "<tr><td colspan='2' height='10'></td></tr>"
        "<tr>"
        "<td width='28' align='center' valign='top' style='padding-top:1px;'>"
        "<b style='color:#E8F4FF;font-size:11pt;'>?</b>"
        "</td>"
        "<td valign='top'>Relancer ce tutoriel.</td>"
        "</tr>"
        "<tr><td colspan='2' height='10'></td></tr>"
        "<tr>"
        "<td width='28' align='center' valign='top' style='padding-top:2px;'>{{COFFEE}}</td>"
        "<td valign='top'>Soutenir le développement du logiciel via un don volontaire.</td>"
        "</tr>"
        "</table>",
        pad=10,
    ),
]

_STEPS_EN: list[_Step] = [
    _Step(
        None,
        "Welcome to neoSlice",
        "neoSlice analyzes your STL, OBJ or 3MF file and automatically generates "
        "the optimal print settings for your printer.\n\n"
        "Now compatible with <b>5 slicers</b> — Bambu Studio, OrcaSlicer, PrusaSlicer, "
        "CrealityPrint and ElegooSlicer — and <b>80+ brands / 600+ printers</b>: Bambu "
        "Lab, Creality, Prusa, Anycubic, Elegoo, Sovol, Qidi, Flashforge, Voron and "
        "many more.\n\n"
        "This guide walks you through the full workflow, from file to export, plus "
        "the <b>Pro</b> features.\n"
        "Click <b>Next</b> to begin.",
    ),
    _Step(
        "settings",
        "First step: choose your output slicer",
        "The very first thing to do: click the <b>settings gear</b> "
        "<span style='font-family:\"Segoe MDL2 Assets\";font-size:11pt;color:#E8F4FF;'>&#xE713;</span>"
        " (top right) and select your <b>output slicer</b> — <b>Bambu Studio</b>, "
        "<b>OrcaSlicer</b>, <b>PrusaSlicer</b>, <b>CrealityPrint</b> or "
        "<b>ElegooSlicer</b>.\n\n"
        "This matters: <b>not all printers work with every slicer</b>. The printer "
        "catalog <b>adapts to the slicer you choose</b> — for example, <b>Prusa</b> "
        "models (XL, CORE One…) only appear when you pick <b>PrusaSlicer</b> or "
        "<b>OrcaSlicer</b>.\n\n"
        "So pick your slicer first to reveal the printer you are looking for.",
        pad=10,
    ),
    _Step(
        "config",
        "① Setup — Printer, Filament & Plate",
        "Select your <b>target printer</b> and <b>nozzle diameter</b>, "
        "then click <b>CONFIRM</b>.\n"
        "Do the same for your <b>filament</b>.\n\n"
        "Finally choose your <b>plate type</b>: the list <b>adapts to your "
        "slicer</b> (Bambu Studio / OrcaSlicer plates, or PrusaSlicer sheets), and "
        "neoSlice automatically adjusts temperatures and adhesion.",
        pad=12,
    ),
    _Step(
        "drop",
        "② Import STL / OBJ / 3MF",
        "Drag your <b>STL, OBJ or 3MF file</b> into this area, "
        "or click to open the file browser.\n\n"
        "neoSlice automatically analyzes the geometry:\n"
        "<b>overhangs · stability · fragile zones</b>\n"
        "<b>volume & dimensions · optimal orientation</b>",
        pad=12,
    ),
    _Step(
        "intent",
        "③ Mission Brief",
        "Open each accordion to choose your criteria:\n"
        "<b>Quality · Strength · Speed · Supports · Adhesion · Use · Mode</b>\n\n"
        "The <b>Mode</b> group lets you enable:\n"
        "— <b>Silent</b>: speeds –40% for less noise\n"
        "— <b>Multicolor (Bambu AMS / Prusa MMU)</b>: enables the <b>prime tower</b> "
        "(purge tower that stabilizes color changes) and <b>flush</b> "
        "(automatic nozzle purge between filaments)\n\n"
        "Save your favorite combinations as presets, "
        "then click <b>GENERATE CONFIGURATION →</b>.",
        pad=12,
    ),
    _Step(
        "statusbar",
        "④ Export to your slicer",
        "Once the configuration is generated, the <b>export button</b> activates.\n\n"
        "neoSlice generates a <b>.3MF</b> file with all settings "
        "optimized for your material and the part's geometry.\n\n"
        "Pick your <b>output slicer</b> (Bambu Studio, OrcaSlicer, PrusaSlicer, "
        "CrealityPrint or ElegooSlicer) in settings — the whole app adapts: printer "
        "catalog, plates and export button.\n\n"
        "<b>Material alerts</b> may appear in the analysis panel: "
        "warping risk, drying recommended, multi-material incompatibility (AMS/MMU)…",
        pad=6,
    ),
    _Step(
        "diag",
        "⑤ AI Diagnostic — fix a failed print",
        "Bad print? Click <b>AI DIAGNOSTIC</b>.\n\n"
        "Take or load a <b>photo</b> of your part: the AI identifies the defect — "
        "<b>stringing, warping, under-extrusion, lifting…</b> — and gives you the "
        "<b>concrete fixes</b> to apply.\n\n"
        "<b>neoSlice Pro feature</b> (free trials included).",
        pad=10,
        pro=True,
    ),
    _Step(
        "pro",
        "⑥ Pro Space — manage your business",
        "The <b>PRO SPACE</b> button opens your full management hub:\n\n"
        "— <b>Dashboard</b>: revenue, paid, due, stock\n"
        "— <b>Spools</b>: track your filament stock (grams & value)\n"
        "— <b>Quotes</b>: real cost calculation + professional PDF quote\n"
        "— <b>Invoicing</b>: compliant invoices (VAT & your country's currency)\n"
        "— <b>Clients</b>: quote + invoice history and paid / due revenue per client\n\n"
        "<b>neoSlice Pro feature.</b>",
        pad=10,
        pro=True,
    ),
    _Step(
        "oen",
        "⑦ Oen — your local AI assistant",
        "The <b>sphere</b> at the bottom-left of the 3D view opens <b>Oen</b>, your "
        "<b>100% local, offline</b> AI assistant (no data sent).\n\n"
        "Oen helps you with:\n"
        "— <b>Settings & choices</b>: material, profile, print parameters\n"
        "— <b>Troubleshooting & maintenance</b> of your machine (any brand)\n"
        "— <b>Your workshop</b>: spool stock, quotes, costs, profitability\n\n"
        "It knows your printer, your settings and the analysis of the current part. "
        "The <b>Thinking</b> button makes it reason before answering (more accurate). "
        "Its knowledge base updates from the settings.\n\n"
        "<b>neoSlice Pro feature</b> — optional install from the settings.",
        pad=14,
        pro=True,
    ),
    _Step(
        "color",
        "⑧ Multicolor export",
        "After exporting a <b>multicolor</b> file (color assembly or a part painted "
        "in Bambu Studio), neoSlice computes the <b>filament weight per color</b>, "
        "colors the 3D preview live, lets you <b>match your spools</b> and "
        "<b>deducts stock</b> from the Pro workspace automatically.\n\n"
        "Perfect to price a multicolor part precisely and track your real usage.\n\n"
        "<b>neoSlice Pro feature.</b>",
        pad=12,
        pro=True,
    ),
    _Step(
        "topbar",
        "⑨ Title bar",
        "On the right of the bar, four shortcuts are available at any time:"
        "<br><br>"
        "<table cellspacing='0' cellpadding='0' width='100%'>"
        "<tr>"
        "<td width='28' align='center' valign='top' style='padding-top:1px;'>"
        "<span style='font-family:\"Segoe MDL2 Assets\";font-size:11pt;color:#E8F4FF;'>&#xE713;</span>"
        "</td>"
        "<td valign='top'>Open settings: theme, language, export folder "
        "and neoSlice Pro status.</td>"
        "</tr>"
        "<tr><td colspan='2' height='10'></td></tr>"
        "<tr>"
        "<td width='28' align='center' valign='top' style='padding-top:1px;'>"
        "<span style='font-family:\"Segoe MDL2 Assets\";font-size:11pt;color:#E8F4FF;'>&#xE8BD;</span>"
        "</td>"
        "<td valign='top'>Report a bug or share your experience."
        " Opens an online form&nbsp;; your feedback is read personally.</td>"
        "</tr>"
        "<tr><td colspan='2' height='10'></td></tr>"
        "<tr>"
        "<td width='28' align='center' valign='top' style='padding-top:1px;'>"
        "<b style='color:#E8F4FF;font-size:11pt;'>?</b>"
        "</td>"
        "<td valign='top'>Replay this tutorial.</td>"
        "</tr>"
        "<tr><td colspan='2' height='10'></td></tr>"
        "<tr>"
        "<td width='28' align='center' valign='top' style='padding-top:2px;'>{{COFFEE}}</td>"
        "<td valign='top'>Support the software's development with a voluntary donation.</td>"
        "</tr>"
        "</table>",
        pad=12,
    ),
]


def _get_steps() -> list[_Step]:
    """Liste des étapes dans la langue active (FR par défaut)."""
    from core.i18n import lang
    return _STEPS_EN if lang() == "en" else _STEPS_FR


def _pro_intro_step() -> _Step:
    """Intro du tuto POST-ACTIVATION (uniquement les fonctionnalités Pro)."""
    from core.i18n import lang
    if lang() == "en":
        return _Step(
            None, "Welcome to neoSlice Pro",
            "Pro is now active — thank you! Here is a quick tour of everything you "
            "just unlocked: <b>AI Diagnosis</b>, the <b>Pro workspace</b> (quotes, "
            "invoicing, spool stock), your local AI assistant <b>Oen</b>, and "
            "<b>multicolor export</b>.\n\nClick <b>Next</b> to start.", pro=True)
    return _Step(
        None, "Bienvenue dans neoSlice Pro",
        "La version Pro est activée — merci&nbsp;! Voici un tour rapide de tout ce "
        "que vous venez de débloquer : le <b>Diagnostic IA</b>, l'<b>Espace Pro</b> "
        "(devis, facturation, stock de bobines), votre assistant IA local <b>Oen</b>, "
        "et l'<b>export multicouleur</b>.\n\nCliquez sur <b>Suivant</b> pour commencer.",
        pro=True)


def _pro_upsell_step() -> _Step:
    """Diapo unique qui REMPLACE les étapes Pro détaillées pour un utilisateur NON-Pro
    (évite 4 diapos verrouillées d'affilée pointant le même bouton). target='pro' →
    surligne le bouton « neoSlice Pro ». Corps auto-suffisant (pas de note ajoutée)."""
    from core.i18n import lang
    if lang() == "en":
        return _Step(
            "pro", "Unlock neoSlice Pro",
            "neoSlice <b>Pro</b> adds tools for makers who sell:\n\n"
            "— <b>AI Diagnostic</b>: fix a failed print from a photo\n"
            "— <b>Pro workspace</b>: quotes, invoices, clients, spool stock, profitability\n"
            "— <b>Oen</b>: your local AI assistant (settings, troubleshooting, workshop)\n"
            "— <b>Multicolor export</b>: weight per color & automatic stock deduction\n\n"
            "<b>Free trials included.</b> Click the highlighted <b>neoSlice Pro</b> "
            "button to learn more.", pad=10, pro=True, no_auto_lock=True)
    return _Step(
        "pro", "Passez à neoSlice Pro",
        "neoSlice <b>Pro</b> ajoute des outils pour les makers qui vendent :\n\n"
        "— <b>Diagnostic IA</b> : corrige une impression ratée à partir d'une photo\n"
        "— <b>Espace Pro</b> : devis, factures, clients, stock de bobines, rentabilité\n"
        "— <b>Oen</b> : votre assistant IA local (réglages, dépannage, atelier)\n"
        "— <b>Export multicouleur</b> : poids par couleur & décompte automatique du stock\n\n"
        "<b>Essais gratuits inclus.</b> Cliquez sur le bouton <b>neoSlice Pro</b> en "
        "surbrillance pour en savoir plus.", pad=10, pro=True, no_auto_lock=True)


def _build_steps(mode: str) -> list[_Step]:
    """Étapes selon le mode :
      'pro'  = tuto post-activation : intro Pro + les seules étapes Pro (détaillées).
      'full' = onboarding. Pour un utilisateur PRO : toutes les étapes (Pro détaillées).
               Pour un NON-Pro : les étapes Pro sont condensées en UNE diapo d'upsell
               (au lieu de 4 diapos verrouillées consécutives)."""
    steps = _get_steps()
    if mode == "pro":
        return [_pro_intro_step()] + [s for s in steps if s.pro]
    if _is_pro():
        return steps
    # Non-Pro : remplacer la 1re série d'étapes Pro par une seule diapo d'upsell.
    out: list[_Step] = []
    inserted = False
    for s in steps:
        if s.pro:
            if not inserted:
                out.append(_pro_upsell_step())
                inserted = True
        else:
            out.append(s)
    return out


# ── Layout constants ─────────────────────────────────────────────────────────
_CARD_W    = 380
_MARGIN    = 28
_BTN_H     = 34
_PAD_H     = 20
_PAD_V     = 18
_BTN_SKIP_W = 112
_BTN_NAV_W  = 110

_HOVER_NONE = 0
_HOVER_SKIP = 1
_HOVER_PREV = 2
_HOVER_NEXT = 3


class TutorialOverlay(QDialog):
    """Dialog plein-écran transparent — tout dessiné via QPainter, zéro widget enfant."""

    finished = Signal()

    def __init__(self, parent: QWidget, targets: dict[str, QWidget], mode: str = "full"):
        # FramelessWindowHint : pas de barre de titre
        # WindowStaysOnTopHint : toujours devant la fenêtre principale
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        # WA_TranslucentBackground : les pixels transparents laissent voir la fenêtre parent
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)

        self._targets = targets
        # mode "full" = onboarding complet ; "pro" = tuto post-activation (uniquement
        # les fonctionnalites Pro, avec une intro dediee). La liste est figee a la
        # construction pour rester coherente pendant tout le parcours.
        self._mode  = mode
        self._steps = _build_steps(mode)
        self._idx     = 0
        self._hovered = _HOVER_NONE

        self._card_rect = QRect()
        self._btn_skip  = QRect()
        self._btn_prev  = QRect()
        self._btn_next  = QRect()

        self.setMouseTracking(True)
        self._sync_geometry()
        parent.installEventFilter(self)

        self._go_to(0)
        self.show()
        self.raise_()
        self.activateWindow()

    # ── Géométrie ─────────────────────────────────────────────────────────────

    def _sync_geometry(self):
        """Positionne le dialog exactement sur la zone client de la fenêtre parent."""
        p = self.parent()
        if p:
            tl = p.mapToGlobal(QPoint(0, 0))
            self.setGeometry(tl.x(), tl.y(), p.width(), p.height())

    # ── Event filter ─────────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if obj is self.parent() and event.type() in (QEvent.Resize, QEvent.Move):
            self._sync_geometry()
            self._layout()
            self.update()
        return False

    def closeEvent(self, event):
        p = self.parent()
        if p:
            p.removeEventFilter(self)
        super().closeEvent(event)

    # ── Navigation ───────────────────────────────────────────────────────────

    def _go_to(self, idx: int):
        self._idx     = idx
        self._hovered = _HOVER_NONE
        self._layout()
        self.repaint()

    def _prev(self):
        if self._idx > 0:
            self._go_to(self._idx - 1)

    def _next(self):
        if self._idx < len(self._steps) - 1:
            self._go_to(self._idx + 1)
        else:
            self._finish()

    def _finish(self):
        _mark_done()
        self.finished.emit()
        self.close()

    # ── Spotlight ────────────────────────────────────────────────────────────

    def _spotlight(self) -> QRect | None:
        step = self._steps[self._idx]
        if step.target is None:
            return None
        w = self._targets.get(step.target)
        if w is None:
            return None
        # Une cible peut être un widget unique OU une liste (ex. titre de section
        # + contenu) → on prend l'UNION des rectangles pour englober le titre.
        widgets = w if isinstance(w, (list, tuple)) else [w]
        rect: QRect | None = None
        for widget in widgets:
            if widget is None or not widget.isVisible():
                continue
            # Coordonnées GLOBALES → repère de l'overlay : marche pour un enfant de la
            # fenêtre ET pour une fenêtre top-level (ex. la sphère Oen, qui est une
            # mini-fenêtre translucide séparée). mapTo(parent) échouait pour celle-ci.
            tl = self.mapFromGlobal(widget.mapToGlobal(QPoint(0, 0)))
            r = QRect(tl, widget.size())
            rect = r if rect is None else rect.united(r)
        if rect is None:
            return None
        spot = rect.adjusted(-step.pad, -step.pad, step.pad, step.pad)
        # Ne jamais laisser le cadre sortir de la fenetre : une cible collee au bord
        # (ex. les icones de la barre de titre, tout en haut) donnait un `top` negatif
        # -> le bord superieur etait rogne. On borne a l'overlay avec une petite marge
        # pour que le contour arrondi reste entierement dessine.
        m = 3
        bounds = self.rect().adjusted(m, m, -m, -m)
        return spot.intersected(bounds)

    # ── Layout ───────────────────────────────────────────────────────────────

    def _body_html(self) -> str:
        icon_color = _T.palette()["TEXT_SECONDARY"]
        # Icône café = même visuel que le logo de la barre du haut (couleurs en
        # thème clair, silhouette teintée en sombre). Recadrée au plus juste et
        # affichée à hauteur fixe (16px) avec largeur proportionnelle → calée au
        # bord gauche comme les glyphes ⚙ 💬 ?, sans déformation. Repli emoji.
        _tint = _T.palette()["TEXT_SECONDARY"] if _T.is_dark() else None
        _cof = _coffee_square_path(_tint)
        if _cof is not None:
            _path, _cw, _ch = _cof
            _dw = max(1, round(16 * _cw / _ch)) if _ch else 16
            coffee_tag = f"<img src='{_path.as_uri()}' width='{_dw}' height='16'>"
        else:
            coffee_tag = "&#x2615;"
        step = self._steps[self._idx]
        body = step.body
        # Étapes Pro (Diagnostic IA / Espace Pro) : pour un utilisateur SANS Pro,
        # les boutons concernés sont masqués (remplacés par le bouton « neoSlice
        # Pro »). On ajoute donc un encart expliquant que c'est réservé au Pro et
        # qu'il faut cliquer sur le bouton mis en surbrillance pour débloquer.
        if step.pro and not _is_pro() and not step.no_auto_lock:
            from core.i18n import lang as _lang
            if _lang() == "en":
                body += ("\n\n🔒 <b>Available with neoSlice Pro.</b> Click the "
                         "highlighted <b>neoSlice Pro</b> button to unlock these "
                         "features — free trials included.")
            else:
                body += ("\n\n🔒 <b>Réservé à neoSlice Pro.</b> Cliquez sur le "
                         "bouton <b>neoSlice Pro</b> en surbrillance pour débloquer "
                         "ces fonctionnalités — essais gratuits inclus.")
        return (body
                .replace("\n", "<br>")
                .replace("#E8F4FF", icon_color)
                .replace("{{COFFEE}}", coffee_tag))

    def _measure_card_height(self) -> int:
        text_w = _CARD_W - 2 * _PAD_H
        h = _PAD_V + 18 + 14  # top pad + dots row + spacing

        td = QTextDocument()
        td.setDefaultFont(QFont(FONT_MAIN, 13, QFont.Bold))
        td.setPlainText(self._steps[self._idx].title)
        td.setTextWidth(text_w)
        h += int(td.size().height()) + 12 + 1 + 12  # title + sep

        bd = QTextDocument()
        bd.setDefaultFont(QFont(FONT_MAIN, 9))
        bd.setHtml(
            f"<body style='font-family:Segoe UI;font-size:9pt;color:{_body_color()};'>"
            f"{self._body_html()}</body>"
        )
        bd.setTextWidth(text_w)
        h += int(bd.size().height()) + 20 + _BTN_H + _PAD_V
        return max(h, 220)

    def _layout(self):
        cw = _CARD_W
        ch = self._measure_card_height()
        ow, oh = self.width(), self.height()
        m = _MARGIN
        spot = self._spotlight()

        if spot is None:
            x = (ow - cw) // 2
            y = (oh - ch) // 2
        else:
            if spot.right() + m + cw <= ow - m:
                x = spot.right() + m
                y = max(m, min(spot.top(), oh - ch - m))
            elif spot.left() - m - cw >= m:
                x = spot.left() - m - cw
                y = max(m, min(spot.top(), oh - ch - m))
            elif spot.bottom() + m + ch <= oh - m:
                x = max(m, (ow - cw) // 2)
                y = spot.bottom() + m
            else:
                x = max(m, (ow - cw) // 2)
                y = max(m, spot.top() - m - ch)
            x = max(m, min(x, ow - cw - m))
            y = max(m, min(y, oh - ch - m))

        self._card_rect = QRect(x, y, cw, ch)

        btn_y = y + ch - _PAD_V - _BTN_H
        self._btn_skip = QRect(x + _PAD_H,                                        btn_y, _BTN_SKIP_W, _BTN_H)
        self._btn_next = QRect(x + cw - _PAD_H - _BTN_NAV_W,                      btn_y, _BTN_NAV_W,  _BTN_H)
        self._btn_prev = QRect(x + cw - _PAD_H - _BTN_NAV_W - 8 - _BTN_NAV_W,    btn_y, _BTN_NAV_W,  _BTN_H)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        # Effacer d'abord avec transparent (obligatoire pour WA_TranslucentBackground)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        self._paint_dim(painter)
        self._paint_card(painter)
        painter.end()

    def _paint_dim(self, painter: QPainter):
        dim = QColor(4, 8, 16, 215) if _T.is_dark() else QColor(20, 30, 50, 190)
        spot = self._spotlight()

        if spot is None:
            painter.fillRect(self.rect(), dim)
        else:
            path = QPainterPath()
            r = self.rect()
            path.addRect(float(r.x()), float(r.y()), float(r.width()), float(r.height()))
            hole = QPainterPath()
            hole.addRoundedRect(float(spot.x()), float(spot.y()),
                                float(spot.width()), float(spot.height()), 6.0, 6.0)
            painter.fillPath(path.subtracted(hole), QBrush(dim))

            _pal = _T.palette()
            glow = QColor(_pal["ACCENT"])
            glow.setAlpha(40)
            painter.setPen(QPen(glow, 8))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(spot), 6, 6)
            painter.setPen(QPen(QColor(_pal["ACCENT"]), 2))
            painter.drawRoundedRect(QRectF(spot), 6, 6)

    def _paint_card(self, painter: QPainter):
        idx   = self._idx
        step  = self._steps[idx]
        total = len(self._steps)
        cr    = QRectF(self._card_rect)
        cx    = float(self._card_rect.x())
        cy    = float(self._card_rect.y())
        tw    = float(_CARD_W - 2 * _PAD_H)
        _tp   = _T.palette()

        # Fond de carte — adapté au thème
        _card_bg = QColor(10, 20, 36) if _T.is_dark() else QColor(_tp["BG_PANEL"])
        painter.setPen(Qt.NoPen)
        painter.setBrush(_card_bg)
        painter.drawRoundedRect(cr, 8.0, 8.0)

        # Bordure
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(_tp["ACCENT"]), 1))
        painter.drawRoundedRect(cr.adjusted(0, 0, -1, -1), 8.0, 8.0)

        # Barre gauche accent
        painter.setBrush(QColor(_tp["ACCENT"]))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(cx, cy + 8, 3, cr.height() - 16), 2.0, 2.0)

        y = cy + _PAD_V

        # ── Points de progression ──
        dot_font = QFont(FONT_MAIN, 9)
        fm = QFontMetrics(dot_font)
        painter.setFont(dot_font)
        dx = cx + _PAD_H
        for i in range(total):
            ch_str = "●" if i <= idx else "○"
            color  = _tp["TELE_GREEN"] if i < idx else (_tp["ACCENT_BRIGHT"] if i == idx else _tp["INACTIVE"])
            painter.setPen(QColor(color))
            painter.drawText(QPointF(dx, y + fm.ascent()), ch_str)
            dx += fm.horizontalAdvance(ch_str) + 8

        painter.setPen(QColor(_tp["TEXT_SECONDARY"]))
        painter.setFont(QFont(FONT_MONO, 7))
        painter.drawText(QRectF(cx + _PAD_H, y, tw, float(fm.height())),
                         Qt.AlignRight | Qt.AlignVCenter,
                         f"{idx + 1} / {total}")
        y += 18 + 14

        # ── Titre — setHtml avec couleur inline pour forcer l'application du thème ──
        _title_color = _tp["TEXT_PRIMARY"]
        # Remplacer le glyphe rond (①②③…) par un badge dessiné identique au panneau
        # gauche : cercle + chiffre centré, en couleur d'accent.
        _title_txt = step.title
        _badge_html = ""
        if _title_txt and _title_txt[0] in _CIRCLED_TO_DIGIT:
            _digit = _CIRCLED_TO_DIGIT[_title_txt[0]]
            _badge = _badge_png(_digit, _tp["ACCENT"])
            _badge_html = (f"<img src='{_badge.as_uri()}' width='22' height='22' "
                           f"style='vertical-align:middle'>&nbsp;&nbsp;")
            _title_txt = _title_txt[1:].lstrip()
        td = QTextDocument()
        td.setDefaultFont(QFont(FONT_MAIN, 13, QFont.Bold))
        td.setHtml(
            f"{_badge_html}<span style='color:{_title_color};font-family:{FONT_MAIN};"
            f"font-size:13pt;font-weight:bold;'>{_title_txt}</span>"
        )
        td.setTextWidth(tw)
        painter.save()
        painter.translate(cx + _PAD_H, y)
        td.drawContents(painter)
        painter.restore()
        y += td.size().height() + 12

        # ── Séparateur — couleur adaptée aux deux thèmes ──
        _sep_color = _tp["TEXT_LABEL"] if not _T.is_dark() else _tp["INACTIVE"]
        painter.setPen(QPen(QColor(_sep_color), 1))
        painter.drawLine(QPointF(cx + _PAD_H, y), QPointF(cx + _CARD_W - _PAD_H, y))
        y += 1 + 12

        # ── Corps ──
        bd = QTextDocument()
        bd.setDefaultFont(QFont(FONT_MAIN, 9))
        _bold_color = _tp['TELE_GREEN'] if not _T.is_dark() else _tp['ACCENT_BRIGHT']
        bd.setDefaultStyleSheet(
            f"body {{ color:{_body_color()}; }} b {{ color:{_bold_color}; font-weight:bold; }}"
        )
        bd.setHtml(
            f"<body style='font-family:Segoe UI;font-size:9pt;color:{_body_color()};'>"
            f"{self._body_html()}</body>"
        )
        bd.setTextWidth(tw)
        painter.save()
        painter.translate(cx + _PAD_H, y)
        bd.drawContents(painter)
        painter.restore()

        # ── Boutons (libellés selon la langue) ──
        from core.i18n import lang as _lang
        _en = _lang() == "en"
        _skip = "Skip guide" if _en else "Passer le guide"
        _prev = "← Previous" if _en else "← Précédent"
        if idx == total - 1:
            _next = "Finish  ✓" if _en else "Terminer  ✓"
        else:
            _next = "Next →" if _en else "Suivant →"
        self._paint_btn(painter, self._btn_skip, _skip,
                        "secondary", self._hovered == _HOVER_SKIP, idx < total - 1)
        self._paint_btn(painter, self._btn_prev, _prev,
                        "outline", self._hovered == _HOVER_PREV, idx > 0)
        self._paint_btn(painter, self._btn_next, _next,
                        "primary", self._hovered == _HOVER_NEXT, True)

    def _paint_btn(self, p: QPainter, rect: QRect, text: str,
                   variant: str, hovered: bool, visible: bool):
        if not visible:
            return
        rf = QRectF(rect)
        p.setPen(Qt.NoPen)

        _tp = _T.palette()
        _accent = _tp["ACCENT"]
        _accent_bright = _tp["ACCENT_BRIGHT"]
        _text_fg = _tp["EXPORT_FG"]
        if variant == "primary":
            p.setBrush(QColor(_accent_bright if hovered else _accent))
            p.drawRoundedRect(rf, 4.0, 4.0)
            p.setPen(QColor(_text_fg))
            p.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        elif variant == "outline":
            _ac = QColor(_accent)
            _ac.setAlpha(40)
            p.setBrush(_ac if hovered else Qt.NoBrush)
            p.drawRoundedRect(rf, 4.0, 4.0)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(_accent), 1))
            p.drawRoundedRect(rf.adjusted(.5, .5, -.5, -.5), 4.0, 4.0)
            p.setPen(QColor(_accent))
            p.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        else:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(_tp["TEXT_SECONDARY"] if hovered else _tp["INACTIVE"]), 1))
            p.drawRoundedRect(rf.adjusted(.5, .5, -.5, -.5), 4.0, 4.0)
            p.setPen(QColor(_tp["TEXT_PRIMARY"] if hovered else _tp["TEXT_SECONDARY"]))
            p.setFont(QFont(FONT_MAIN, 8))

        p.drawText(rf, Qt.AlignCenter, text)

    # ── Souris ───────────────────────────────────────────────────────────────

    def mouseMoveEvent(self, event):
        pos   = event.pos()
        total = len(self._steps)
        old   = self._hovered

        if self._btn_next.contains(pos):
            self._hovered = _HOVER_NEXT
        elif self._idx > 0 and self._btn_prev.contains(pos):
            self._hovered = _HOVER_PREV
        elif self._idx < total - 1 and self._btn_skip.contains(pos):
            self._hovered = _HOVER_SKIP
        else:
            self._hovered = _HOVER_NONE

        self.setCursor(Qt.PointingHandCursor if self._hovered != _HOVER_NONE else Qt.ArrowCursor)
        if self._hovered != old:
            self.update()
        event.accept()

    def leaveEvent(self, event):
        if self._hovered != _HOVER_NONE:
            self._hovered = _HOVER_NONE
            self.setCursor(Qt.ArrowCursor)
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos   = event.pos()
            total = len(self._steps)
            if self._btn_next.contains(pos):
                self._next()
            elif self._idx > 0 and self._btn_prev.contains(pos):
                self._prev()
            elif self._idx < total - 1 and self._btn_skip.contains(pos):
                self._finish()
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    # ── Clavier ──────────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        k = event.key()
        if k == Qt.Key_Escape:
            self._finish()
        elif k in (Qt.Key_Right, Qt.Key_Return, Qt.Key_Space):
            self._next()
        elif k == Qt.Key_Left:
            self._prev()
        else:
            event.ignore()
