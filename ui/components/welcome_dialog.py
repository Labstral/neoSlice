"""Popup de bienvenue — affiché au premier lancement de neoSlice."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QFrame, QWidget, QScrollArea, QApplication,
)
from PySide6.QtCore import Qt, QUrl, QPoint
from PySide6.QtGui import QFont, QPixmap, QDesktopServices, QMouseEvent

from version import __version__
from ui.styles.theme import FONT_MONO, MANAGER as _T, FONT_MAIN

_PREFS_FILE = Path.home() / ".neoslice" / "prefs.json"
_COFFEE_URL = "https://buymeacoffee.com/bambulabpourlesnuls"


def _load_prefs() -> dict:
    try:
        if _PREFS_FILE.exists():
            return json.loads(_PREFS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_prefs(prefs: dict) -> None:
    _PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PREFS_FILE.write_text(
        json.dumps(prefs, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def should_show_welcome() -> bool:
    prefs = _load_prefs()
    if prefs.get("last_seen_version") != __version__:
        return True
    return not prefs.get("skip_welcome", False)


def is_update() -> bool:
    """True si la version a changé depuis le dernier lancement (mise à jour)."""
    prefs = _load_prefs()
    lsv = prefs.get("last_seen_version")
    return lsv is not None and lsv != __version__


_WHATS_NEW_FR = [
    ("Nouveautés v0.1.8.4",
     "• La « Tour de température » de la catégorie Calibration & tests est "
     "désormais un modèle de référence complet (PLA + PETG), prêt à imprimer.\n"
     "• Le « Test de surplombs » a été entièrement refait : bras courbé net, "
     "angles gravés bien lisibles sur le dessus, avec hauteur, largeur, épaisseur "
     "et angle maximum réglables."),
    ("Nouveautés v0.1.8.3",
     "• Nouvelle catégorie « Calibration & tests » dans neoGen : cube XYZ, tour "
     "de température, tests de surplombs, de pont, de tolérance, de trous, "
     "d'épaisseur de parois, de retrait et de première couche. Tous réglables et "
     "prêts à imprimer, sans aller chercher de fichier ailleurs.\n"
     "• La bibliothèque neoGen peut désormais s'enrichir de nouvelles CATÉGORIES "
     "entières via « Mettre à jour la base », sans réinstaller."),
    ("Nouveautés v0.1.8.2",
     "• Une fenêtre au lancement vous prévient dès que de nouveaux objets neoGen "
     "ou une base de connaissances d'Oen enrichie sont disponibles, avec un bouton "
     "pour tout mettre à jour en un clic, sans réinstaller.\n"
     "• Import : si vous ouvrez par erreur un fichier « tranché » (.gcode.3mf) "
     "exporté depuis Bambu Studio, neoSlice l'explique clairement et vous indique "
     "comment exporter le modèle à la place (clic droit → « Convertir en un seul STL »)."),
    ("Nouveautés v0.1.8.1",
     "• neoGen : la « Boîte + couvercle » a désormais une forme RECTANGULAIRE "
     "(en plus de ronde et carrée), avec longueur et largeur réglables.\n"
     "• La bibliothèque neoGen s'enrichit et se corrige TOUTE SEULE via « Mettre à "
     "jour la base » — désormais SANS aucune limite : objets en plusieurs pièces, "
     "en deux couleurs ou générés à partir d'une image, tout arrive sans réinstaller.\n"
     "• Fenêtre Modules : coche verte devant le statut d'Oen, comme neoGen."),
    ("neoGen — générateur d'objets 3D (Pro)",
     "Le nouveau module phare : une bibliothèque d'objets prêts à imprimer, tous "
     "personnalisables au millimètre — porte-clés, cadres photo, QR codes 3D en "
     "deux couleurs, cartes de visite, clips de câble au diamètre exact, joints, "
     "équerres, vis et écrous, objets pour la restauration, le mariage et la "
     "boutique. Texte en relief ou gravé, choix de la police et des couleurs : "
     "chaque pièce est générée sur mesure, étanche et pensée pour sortir sans "
     "support."),
    ("Carte de fragilité par pièce",
     "Quand plusieurs pièces sont sur le plateau, cochez « Fragilité » dans la vue "
     "3D : chaque pièce se colore selon sa solidité (vert = solide, jaune = un peu "
     "fragile, rouge = fragile). Vous savez en un coup d'œil quelle pièce renforcer "
     "avant de lancer l'impression."),
    ("FlashPrint — 9e slicer compatible",
     "Sortie vers FlashPrint pour les imprimantes FlashForge, avec dépôt "
     "automatique du profil d'impression. Le catalogue d'imprimantes et les "
     "plateaux proposés s'adaptent désormais à chaque machine."),
    ("Mode performance automatique",
     "neoSlice choisit seul, pièce par pièce, le meilleur compromis entre vitesse "
     "d'analyse et précision selon votre machine. Plus rien à régler, et les "
     "fichiers complexes qui pouvaient bloquer le chargement s'ouvrent maintenant "
     "en quelques secondes."),
    ("Autres améliorations v0.1.8",
     "• Chargement fiable des 3MF complexes (assemblages multi-pièces Bambu).\n"
     "• Plus aucune analyse ne peut geler : un garde-fou de temps garantit qu'on "
     "arrive toujours au devis, même sur les maillages très denses.\n"
     "• Les petites pièces reposent correctement sur le plateau dans la vue 3D.\n"
     "• Le type de fichier réel (STL, OBJ ou 3MF) est affiché pendant l'analyse.\n"
     "• Messages d'analyse épurés et progression plus lisible.\n"
     "• Plages de dimensions élargies sur tous les objets neoGen.\n"
     "• macOS : la mise à jour dépose le fichier dans le dossier Téléchargements."),
    ("Oen — assistant IA local (Pro)",
     "Un modèle Qwen3 tourne directement sur votre machine (hors ligne, privé), "
     "nourri d'une base de connaissances imprimantes toutes marques. Activez le "
     "mode « Réflexion » pour des réponses raisonnées. La base se met à jour depuis "
     "GitHub sans réinstaller l'application."),
    ("Export multicouleur (Pro)",
     "Coloriez vos pièces après l'export 3MF, appliquez un filament par slot et "
     "obtenez le grammage par couleur/bobine — le stock est déduit automatiquement "
     "après impression."),
    ("Multi-slicers, 80+ marques, 600+ imprimantes",
     "Sortie compatible Bambu Studio, OrcaSlicer, PrusaSlicer, CrealityPrint et "
     "ElegooSlicer — le catalogue d'imprimantes s'adapte au slicer choisi. "
     "Nouvelles machines : Flashforge Creator 5 / 5 Pro, Phrozen Arco et gamme "
     "Anycubic Kobra étendue."),
    ("Version Pro",
     "Le Diagnostic IA et Oen deviennent des fonctionnalités Pro ; l'interface "
     "standard reste entièrement gratuite pour optimiser et exporter ses pièces."),
    ("Correctif v0.1.7",
     "• Barre de titre sombre native fiable sous Windows (plus de retour au thème "
     "clair).\n"
     "• Tutoriel enrichi (Oen + export multicouleur), adapté selon Pro/standard."),
    ("Nouveautés v0.1.6",
     "• Espace Pro — Gestion d'atelier complète : bobines (stock multi-couleur, "
     "coût/kg, alertes de réappro, liste de courses), devis, factures, clients, "
     "commandes (file de production) et catalogue d'articles — le tout connecté.\n"
     "• Tableau de bord : chiffre d'affaires facturé / encaissé / dû, factures en "
     "retard, graphe des 6 derniers mois et export comptable (CSV).\n"
     "• Facturation internationale : 13 pays, documents rédigés dans la langue du "
     "client (FR, EN, DE, NL, IT, ES), mentions légales par pays et frais de "
     "recouvrement configurables.\n"
     "• Décompte automatique du filament après chaque impression.\n"
     "• Multi-marques / multi-slicer : Creality, Prusa, Anycubic, Voron… et sortie "
     "vers Bambu Studio, OrcaSlicer ou PrusaSlicer.\n"
     "• Nombreux correctifs d'affichage (barre de titre, fenêtres, listes)."),
    ("Correctif v0.1.5.6",
     "• macOS : l'activation Pro et les mises à jour échouaient avec « Pas de "
     "connexion Internet » alors que tout fonctionnait — corrigé (certificats SSL).\n"
     "• Hauteur de couche « rapide » ramenée à 0.24 mm (buse 0.4) et température "
     "PETG ajustée à 250°C.\n"
     "• Import STL/3MF plus fiable sur Mac."),
    ("Correctif v0.1.5.5",
     "Correction de l'activation de neoSlice Pro : sur certaines connexions "
     "(réseau lent, antivirus/pare-feu), l'activation pouvait rester bloquée. "
     "Elle se fait désormais en arrière-plan, sans figer la fenêtre, et ne "
     "consomme plus d'activation en cas d'échec réseau."),
    ("Nouveautés v0.1.5.4",
     "• Aperçu miniature de vos fichiers dès l'import (STL / OBJ / 3MF)\n"
     "• Rendu 3D mat, plus agréable et lisible\n"
     "• Génération adaptée aux limites réelles de votre imprimante "
     "(vitesses, débit, températures)\n"
     "• Estimation du poids selon le matériau choisi\n"
     "• Tutoriel bilingue et nombreux fignolages d'interface"),
    ("Correctifs de compatibilité v0.1.5.3",
     "neoSlice démarre désormais sur davantage de configurations Windows. "
     "Diverses améliorations de compatibilité et de stabilité ont été apportées."),
    ("Correction importante v0.1.5.2",
     "• Taille des pièces — certaines pièces (entre 5 et 50 mm) étaient agrandies "
     "10× par erreur au chargement. La taille réelle du fichier est désormais "
     "toujours respectée.\n"
     "• Mises à jour plus fiables — le téléchargement est vérifié avant installation "
     "(fini l'erreur « application 16 bits »)."),
    ("Import de fichiers 3MF Bambu Studio",
     "Chargez directement vos fichiers .3mf depuis Bambu Studio — neoSlice affiche toutes vos pièces, "
     "respecte la disposition multi-plateau et génère un fichier optimisé qui préserve la structure d'origine."),
    ("Barres de fragilité par lot",
     "Une barre de fragilité flottante s'affiche au-dessus de chaque groupe de pièces, "
     "visible depuis n'importe quel angle de caméra."),
    ("Autres corrections",
     "• Imprimante H2C — bon modèle transmis à Bambu Studio\n"
     "• Imprimante par défaut correctement restaurée au démarrage (A1, A1 Mini, H2C…)\n"
     "• Angle de support minimum corrigé à 30°\n"
     "• Hauteurs de couche cohérentes avec les préréglages Bambu\n"
     "• Avertissements Bambu Studio supprimés à l'ouverture du fichier généré"),
]


class WelcomeDialog(QDialog):
    """Fenêtre de bienvenue modale, sans cadre natif, déplaçable."""

    def __init__(self, parent=None, assets_path: Path | None = None,
                 show_whats_new: bool = False):
        super().__init__(parent)
        self._assets = assets_path
        self._show_whats_new = show_whats_new
        self._drag_pos: QPoint | None = None
        self._pal = _T.palette()

        self.setWindowTitle("neoSlice")
        self.setMinimumWidth(480)
        self.setMaximumWidth(520)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet(f"""
            QDialog {{
                background: {self._pal['BG_PANEL']};
                border: 1px solid {self._pal['ACCENT']};
                border-radius: 6px;
            }}
        """)
        self._setup_ui()

    # ── Adaptation à l'écran ─────────────────────────────────────────────────

    def showEvent(self, event):
        """Borne la hauteur à la zone utile (hors barre des tâches/dock) et
        recentre. Le contenu défile si besoin → le pied de page reste visible."""
        super().showEvent(event)
        scr = self.screen() or QApplication.primaryScreen()
        if scr is None:
            return
        avail = scr.availableGeometry()          # exclut barre des tâches / dock
        max_h = int(avail.height() * 0.92)
        # Le scroll demande la hauteur EXACTE du contenu → pas de barre inutile ;
        # il ne défilera que si l'écran est vraiment trop petit (cap ci-dessous).
        try:
            self._scroll.setMinimumHeight(self._welcome_content.sizeHint().height())
            self.adjustSize()
        except Exception:
            pass
        if self.height() > max_h:
            self._scroll.setMinimumHeight(0)
            self.resize(self.width(), max_h)
        g = self.frameGeometry()
        g.moveCenter(avail.center())
        # Garde la fenêtre entièrement dans la zone utile
        g.moveTop(max(avail.top() + 8, min(g.top(), avail.bottom() - self.height() - 8)))
        g.moveLeft(max(avail.left() + 8, min(g.left(), avail.right() - self.width() - 8)))
        self.move(g.topLeft())

    # ── Drag-to-move ───────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None

    # ── UI ─────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        pal = self._pal
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Contenu DÉFILANT : la fenêtre ne doit jamais dépasser l'écran, sinon le
        # bouton « Commencer » passe sous la barre des tâches/dock → infermable.
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            f"QScrollBar:vertical{{background:{pal['BG_ELEVATED']};width:10px;margin:2px;border-radius:5px;}}"
            f"QScrollBar::handle:vertical{{background:{pal['TEXT_SECONDARY']};border-radius:5px;min-height:30px;}}"
            f"QScrollBar::handle:vertical:hover{{background:{pal['ACCENT']};}}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
            "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}"
        )
        _content = QWidget()
        _content.setStyleSheet("background: transparent;")
        self._scroll.setWidget(_content)
        self._welcome_content = _content
        outer.addWidget(self._scroll, 1)

        root = QVBoxLayout(_content)
        root.setContentsMargins(36, 12, 36, 12)
        root.setSpacing(0)

        # ── Logo (sans texte « neoSlice » : déjà dans le logo) ──────────────
        logo_lbl = QLabel()
        logo_lbl.setAlignment(Qt.AlignCenter)

        logo_loaded = False
        if self._assets:
            px_path = self._assets / "neoSlice.png"
            if px_path.exists():
                px = QPixmap(str(px_path))
                if not px.isNull():
                    logo_lbl.setPixmap(
                        px.scaled(190, 190, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    )
                    logo_loaded = True

        if not logo_loaded:
            logo_lbl.setText("◈")
            logo_lbl.setFont(QFont(FONT_MAIN, 84))
            logo_lbl.setStyleSheet(f"color: {pal['ACCENT_BRIGHT']}; background: transparent;")

        root.addWidget(logo_lbl)
        root.addSpacing(8)

        sub_lbl = QLabel("AI-POWERED 3D PRINT OPTIMIZER")
        sub_lbl.setAlignment(Qt.AlignCenter)
        sub_lbl.setFont(QFont(FONT_MONO, 8))
        sub_lbl.setStyleSheet(
            f"color: {pal['TEXT_SECONDARY']}; letter-spacing: 3px; background: transparent;"
        )
        root.addWidget(sub_lbl)

        root.addSpacing(12)

        # Badges version / auteur
        badges = QHBoxLayout()
        badges.setAlignment(Qt.AlignCenter)
        badges.setSpacing(8)

        _version_text = f"v{__version__}"
        for text, fg, bg, border in [
            (_version_text,               pal['ACCENT_BRIGHT'], pal['BG_SURFACE'], pal['ACCENT']),
            ("© 2026 Emmanuel Percheron", pal['TEXT_LABEL'],    "transparent",     "transparent"),
        ]:
            lbl = QLabel(text)
            lbl.setFont(QFont(FONT_MONO, 7, QFont.Bold if text == _version_text else QFont.Normal))
            lbl.setStyleSheet(
                f"color: {fg}; background: {bg}; border: 1px solid {border}; "
                f"border-radius: 3px; padding: 2px 7px;"
            )
            badges.addWidget(lbl)

        root.addLayout(badges)
        root.addSpacing(14)
        root.addWidget(self._sep())
        root.addSpacing(12)

        # ── Quoi de neuf (uniquement après une mise à jour) ───────────────
        if self._show_whats_new:
            wn_title = QLabel(f"Nouveautés de la v{__version__}")
            wn_title.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
            wn_title.setStyleSheet(f"color: {pal['ACCENT_BRIGHT']}; background: transparent;")
            wn_title.setAlignment(Qt.AlignCenter)
            root.addWidget(wn_title)
            root.addSpacing(12)

            # Le changelog peut être long (plusieurs versions) → on le borne dans
            # sa PROPRE zone défilante, sinon la fenêtre s'étire sur tout l'écran.
            wn_scroll = QScrollArea()
            wn_scroll.setWidgetResizable(True)
            wn_scroll.setFrameShape(QFrame.NoFrame)
            wn_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            wn_scroll.setMaximumHeight(240)
            wn_scroll.setStyleSheet(
                "QScrollArea{background:transparent;border:none;}"
                f"QScrollBar:vertical{{background:{pal['BG_ELEVATED']};width:10px;margin:2px;border-radius:5px;}}"
                f"QScrollBar::handle:vertical{{background:{pal['TEXT_SECONDARY']};border-radius:5px;min-height:30px;}}"
                f"QScrollBar::handle:vertical:hover{{background:{pal['ACCENT']};}}"
                "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
                "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}"
            )
            wn_inner = QWidget()
            wn_inner.setStyleSheet("background: transparent;")
            wn_lay = QVBoxLayout(wn_inner)
            wn_lay.setContentsMargins(0, 0, 10, 0)   # marge droite = place pour la scrollbar
            wn_lay.setSpacing(0)
            for title, body in _WHATS_NEW_FR:
                t = QLabel(title)
                t.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
                t.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
                t.setWordWrap(True)
                wn_lay.addWidget(t)

                b = QLabel(body)
                b.setFont(QFont(FONT_MAIN, 8))
                b.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
                b.setWordWrap(True)
                wn_lay.addWidget(b)
                wn_lay.addSpacing(8)
            wn_lay.addStretch()
            wn_scroll.setWidget(wn_inner)
            root.addWidget(wn_scroll)

            root.addSpacing(4)
            root.addWidget(self._sep())
            root.addSpacing(14)

        # ── Message principal ─────────────────────────────────────────────
        welcome = QLabel(
            "Si <b>neoSlice</b> te plaît et te fait gagner du temps,<br>"
            "ton soutien compte vraiment pour ce projet."
        )
        welcome.setFont(QFont(FONT_MAIN, 10))
        welcome.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        welcome.setWordWrap(True)
        welcome.setAlignment(Qt.AlignCenter)
        root.addWidget(welcome)
        root.addSpacing(10)

        gratuit_lbl = QLabel("Ce logiciel est <b>100% gratuit</b> et le restera toujours.")
        gratuit_lbl.setFont(QFont(FONT_MAIN, 9))
        gratuit_lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        gratuit_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(gratuit_lbl)

        geste_lbl = QLabel("Même un tout petit geste fait vraiment la différence.")
        geste_lbl.setFont(QFont(FONT_MAIN, 9))
        geste_lbl.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        geste_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(geste_lbl)

        root.addSpacing(16)

        from pathlib import Path as _Path
        from PySide6.QtGui import QIcon as _QIcon
        from PySide6.QtCore import QSize as _QSize
        _coffee_png = _Path(__file__).parent.parent.parent / "assets" / "coffee.png"
        if _coffee_png.exists():
            coffee_btn = QPushButton(" M'offrir un café")
            coffee_btn.setIcon(_QIcon(str(_coffee_png)))
            coffee_btn.setIconSize(_QSize(22, 22))
        else:
            coffee_btn = QPushButton("M'offrir un café")
        coffee_btn.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
        coffee_btn.setFixedHeight(40)
        coffee_btn.setCursor(Qt.PointingHandCursor)
        coffee_btn.setStyleSheet("""
            QPushButton {
                background: #FFDD00;
                color: #1A1A1A;
                border: none;
                border-radius: 5px;
                padding: 0 20px;
            }
            QPushButton:hover { background: #FFE840; }
            QPushButton:pressed { background: #F0CE00; }
        """)
        coffee_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(_COFFEE_URL))
        )
        root.addWidget(coffee_btn)

        root.addSpacing(12)

        # Encart « améliorations continues » (discret)
        feedback_box = QWidget()
        feedback_box.setStyleSheet(f"""
            QWidget {{
                background: rgba(30,144,255,0.06);
                border-left: 3px solid {pal['ACCENT']};
                border-radius: 2px;
            }}
        """)
        feedback_lay = QVBoxLayout(feedback_box)
        feedback_lay.setContentsMargins(12, 7, 12, 7)
        feedback_lbl = QLabel(
            f"<b style='color:{pal['ACCENT_BRIGHT']}'>Améliorations continues</b>"
            f"<span style='color:{pal['TEXT_LABEL']}'> — De nouvelles fonctionnalités arrivent "
            "régulièrement. N'hésitez pas à signaler un problème ou à proposer une idée.</span>"
        )
        feedback_lbl.setFont(QFont(FONT_MAIN, 8))
        feedback_lbl.setStyleSheet("background: transparent;")
        feedback_lbl.setWordWrap(True)
        feedback_lay.addWidget(feedback_lbl)
        root.addWidget(feedback_box)

        root.addSpacing(4)

        # ── Pied de page FIXE (hors zone défilante → toujours accessible) ──
        footer_box = QWidget()
        footer_box.setStyleSheet(
            f"QWidget{{background:{pal['BG_PANEL']};border-top:1px solid {pal['INACTIVE']};"
            "border-bottom-left-radius:6px;border-bottom-right-radius:6px;}"
        )
        footer = QHBoxLayout(footer_box)
        footer.setContentsMargins(36, 12, 36, 16)
        footer.setSpacing(10)

        self._skip_check = QCheckBox("Ne plus afficher ce message")
        self._skip_check.setFont(QFont(FONT_MAIN, 8))
        self._skip_check.setStyleSheet(f"""
            QCheckBox {{
                color: {pal['TEXT_LABEL']};
                background: transparent;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 14px; height: 14px;
                border: 1px solid {pal['INACTIVE']};
                border-radius: 2px;
                background: {pal['BG_SURFACE']};
            }}
            QCheckBox::indicator:checked {{
                background: {pal['ACCENT']};
                border-color: {pal['ACCENT']};
                image: none;
            }}
            QCheckBox::indicator:hover {{ border-color: {pal['ACCENT_BRIGHT']}; }}
        """)
        footer.addWidget(self._skip_check)
        footer.addStretch()

        close_btn = QPushButton("Commencer →")
        close_btn.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        close_btn.setFixedHeight(34)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setDefault(True)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {pal['ACCENT']};
                color: {pal['EXPORT_FG']};
                border: none;
                border-radius: 4px;
                padding: 0 22px;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}
        """)
        close_btn.clicked.connect(self._on_close)
        footer.addWidget(close_btn)

        outer.addWidget(footer_box)

    def _sep(self) -> QFrame:
        f = QFrame()
        f.setFixedHeight(1)
        f.setStyleSheet(f"background: {self._pal['INACTIVE']};")
        return f

    def _on_close(self):
        prefs = _load_prefs()
        prefs["last_seen_version"] = __version__
        # La case est autoritaire à CHAQUE fermeture : cochée → on masque,
        # décochée → la fenêtre continue d'apparaître à chaque lancement.
        # (Avant, on ne remettait jamais False → un True restait coincé à vie.)
        prefs["skip_welcome"] = self._skip_check.isChecked()
        _save_prefs(prefs)
        self.accept()
