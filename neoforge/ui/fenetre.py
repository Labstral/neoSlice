# -*- coding: utf-8 -*-
"""La fenêtre de neoForge.

Trois zones : la pile d'étapes à gauche, la pièce au centre, les réglages à
droite. Chaque modification relance le calcul EN ARRIÈRE-PLAN : la fenêtre ne
gèle jamais, et une étape qui échoue laisse la dernière pièce valide à l'écran.

Rien n'est destructif : tout passe par l'historique (annuler / rétablir), une
étape se masque au lieu de se supprimer, et le travail est enregistré tout seul
pour être repris si le noyau de CAO plante.
"""
from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QIcon, QKeySequence, QPainter, QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox,
    QPushButton, QSplitter, QStackedWidget, QVBoxLayout, QWidget,
)

from core.neoforge import pont as P
from neoforge.noyau import aretes as A
from neoforge.noyau import export as X
from neoforge.noyau import occ as O
from neoforge.noyau.construction import Constructeur
from neoforge.noyau.maillage import polyligne, trianguler, trianguler_affichage
from neoforge.noyau.primitives import solide
from neoforge.projet import ergonomie as E
from neoforge.projet import unites as U
from neoforge.projet import nfg
from neoforge.projet.historique import Historique
from neoforge.projet.modele import Arrondi, Coupe, Forme, Projet, identifiant
from neoforge.ui import dialogues as D
from neoforge.ui import style as S
from neoforge.ui.style import respirer as _respirer
from loguru import logger

from neoforge.ui.accueil import Accueil
from neoforge.ui.panneaux import Proprietes
from neoforge.ui.pile import Pile
from neoforge.ui.textes import T
from neoforge.ui.viewer import Viewer
from ui.styles.theme import FONT_MAIN, MANAGER as _T

PLATEAU_DEFAUT = (256.0, 256.0, 256.0)


def icone() -> QIcon:
    """Icône propre à neoForge (barre des tâches distincte de neoSlice)."""
    pm = QPixmap(64, 64)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(S.pal()["ACCENT"]))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(2, 2, 60, 60, 14, 14)
    p.setPen(QColor("#FFFFFF"))
    p.setFont(QFont(FONT_MAIN, 26, QFont.Bold))
    p.drawText(pm.rect(), Qt.AlignCenter, "nF")
    p.end()
    return QIcon(pm)


class _Calcul(QThread):
    """Recalcule la pièce hors du fil de l'interface."""
    fini = Signal(object)

    def __init__(self, constructeur: Constructeur, projet: Projet, selection: int,
                 mode_aretes: bool, parent=None):
        super().__init__(parent)
        self._c = constructeur
        self._projet = projet
        self._selection = selection
        self._mode = mode_aretes

    def run(self):
        sortie = {"resultats": [], "V": None, "F": None, "forme": None,
                  "fantome": None, "creux": False, "aretes": [], "signatures": [],
                  "choisies": set(), "volume": 0.0, "boite": None, "erreur": None,
                  "Va": None, "Fa": None}      # maillage d'AFFICHAGE (non soudé)
        try:
            resultats = self._c.construire(self._projet)
            sortie["resultats"] = resultats
            etapes = self._projet.etapes
            i = self._selection
            etape = etapes[i] if 0 <= i < len(etapes) else None
            forme = resultats[-1].forme if resultats else None

            # Arrondi sur des arêtes choisies. En mode CHOIX, on montre la pièce
            # telle qu'elle est AVANT l'arrondi, avec toutes ses arêtes. Sinon,
            # on garde en surbrillance les seules arêtes retenues : elles
            # disparaissaient dès qu'on validait, et on croyait les avoir perdues
            # en changeant de genre (retour d'Emmanuel, alors qu'elles étaient
            # bien là dans le projet).
            if isinstance(etape, Arrondi) and (self._mode or etape.regle == "liste"):
                forme_base = resultats[i - 1].forme if i > 0 else None
                if forme_base is not None:
                    boite = O.boite(forme_base)
                    candidates = A.aretes_arrondissables(forme_base)
                    if getattr(etape, "cible", ""):
                        # On ne propose QUE les arêtes de l'objet visé : c'est
                        # sur lui que l'arrondi portera.
                        from neoforge.projet.modele import groupe_de
                        vises = groupe_de(etapes, etape.cible)
                        if vises:
                            candidates = A.restreindre(candidates, vises)
                    trouvees, _manque = A.retrouver(etape.aretes, candidates, boite)
                    retenues = sorted(k for k, e in enumerate(candidates)
                                      if any(e.IsSame(t) for t in trouvees))
                    if self._mode:
                        # ⚠️ On montre la pièce ARRONDIE, pas celle d'avant.
                        # En affichant la pièce brute pendant le choix des
                        # arêtes, changer le rayon ne se voyait nulle part : il
                        # fallait valider pour découvrir le résultat (retour
                        # d'Emmanuel). Les arêtes proposées, elles, restent
                        # celles de la pièce AVANT arrondi : ce sont elles
                        # qu'on clique, et elles se dessinent juste au dessus
                        # du congé, là où l'angle vif se trouvait.
                        sortie["aretes"] = [polyligne(e) for e in candidates]
                        sortie["signatures"] = [A.signature(e, boite) for e in candidates]
                        sortie["choisies"] = set(retenues)
                    else:
                        sortie["aretes"] = [polyligne(candidates[k]) for k in retenues]
                        sortie["choisies"] = set(range(len(retenues)))
            if forme is not None:
                V, F = trianguler(forme)          # étanche : export et volume
                Va, Fa = trianguler_affichage(forme)   # à l'écran : ombrage juste
                sortie.update(V=V, F=F, Va=Va, Fa=Fa, forme=forme,
                              volume=O.volume(forme), boite=O.boite(forme))
            if isinstance(etape, Forme) and etape.actif:
                fv, ff = trianguler(solide(etape))
                premiere = next((k for k, e in enumerate(etapes)
                                 if isinstance(e, Forme) and e.actif), None)
                sortie["fantome"] = (fv, ff)
                sortie["creux"] = (i != premiere and etape.op != "matiere")
        except Exception as exc:                       # le noyau ne doit jamais tuer l'UI
            sortie["erreur"] = str(exc)
        self.fini.emit(sortie)


class FenetreNeoForge(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("neoForge")
        self.setWindowIcon(icone())
        self.setMinimumSize(1100, 700)
        self.resize(1320, 820)

        self._projet: Projet | None = None
        self._chemin: Path | None = None
        self._modifie = False
        self._selection = 0
        self._constructeur = Constructeur()
        self._historique = Historique()
        self._calcul: _Calcul | None = None
        self._recalcul_demande = False
        self._resultats: list = []
        self._forme_finale = None
        self._V = self._F = None
        self._boite = None                # boîte de la pièce : sert au plan de coupe
        self._ferme = False               # vrai dès que la fenêtre se ferme
        self._boite_coupe = None          # boîte tranchée : mesures du plan en direct
        self._partie = ""                 # « bas » / « haut » d'une découpe choisie
        self._signatures: list[dict] = []
        self._mode_aretes = False
        self._collage = True
        self._glisse = False              # une poignée de cote est tirée
        self._pos_reference: list[float] | None = None
        self._dim_apercu: list[float] = [1.0, 1.0, 1.0]   # taille de l'aperçu construit
        self._compagnons: list[int] = []   # pièces entraînées par le geste en cours
        self._plateau = PLATEAU_DEFAUT
        self._nom_imprimante = ""
        self._essais_envoi = 0
        # L'unité d'affichage est lue AVANT de construire l'interface : les
        # compteurs et les cotes doivent naître dans la bonne unité, sinon on
        # verrait les millimètres se changer en pouces juste après l'ouverture.
        U.definir(nfg.unite())

        self._construire_ui()
        # Les compteurs naissent avec les décimales et les bornes de l'unité lue :
        # au pouce, un dixième de millimètre exige trois décimales.
        self._proprietes.definir_unite(U.courante())
        self._demander_imprimante()
        _T.register(self.refresh_theme)
        self._surveiller_theme()
        self.refresh_theme()

        self._auto = QTimer(self)
        self._auto.setInterval(60)
        self._auto.setSingleShot(True)
        self._auto.timeout.connect(self._lancer_calcul)
        QTimer.singleShot(0, self._proposer_reprise)

    # ── Construction de l'interface ────────────────────────────────────────
    def _construire_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        racine = QVBoxLayout(central)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(0)
        racine.addWidget(self._barre_outils())
        _respirer()                 # la barre de l'écran de chargement continue

        self._pages = QStackedWidget()
        racine.addWidget(self._pages, 1)

        self._accueil = Accueil()
        self._accueil.nouveau.connect(self.nouveau)
        self._accueil.ouvrir.connect(self.ouvrir)
        self._accueil.ouvrir_fichier.connect(lambda p: self.ouvrir(Path(p)))
        self._pages.addWidget(self._accueil)

        travail = QSplitter(Qt.Horizontal)
        self._pile = Pile()
        _respirer()
        self._pile.selection_changee.connect(self._changer_selection)
        self._pile.ajouter_forme.connect(self._ajouter_forme)
        self._pile.ajouter_arrondi.connect(self._ajouter_arrondi)
        self._pile.ajouter_coupe.connect(self._ajouter_coupe)
        self._pile.action.connect(self._action_pile)
        self._pile.rattacher.connect(self._rattacher)
        _respirer()                 # l'écran de chargement continue de défiler
        self._viewer = Viewer()
        _respirer()                 # (la vue 3D est la partie la plus longue)
        self._viewer.arete_cliquee.connect(self._clic_arete)
        self._viewer.piece_cliquee.connect(self._clic_piece)
        self._viewer.fond_clique.connect(self._clic_fond)
        self._viewer.taille_modifiee.connect(self._taille_modifiee)
        self._viewer.deplacement.connect(self._deplacement)
        self._viewer.rotation.connect(self._rotation)
        self._viewer.geste_termine.connect(self._geste_fini)
        self._viewer.suppression_demandee.connect(self._supprimer_selection)
        self._viewer.plan_deplace.connect(self._plan_deplace)
        self._viewer.regle_demandee.connect(self._mode_regle)
        self._proprietes = Proprietes()
        self._proprietes.modifie.connect(lambda: self._sur_modification("panneau"))
        self._proprietes.geste.connect(self._geste)
        self._proprietes.choisir_aretes.connect(self._mode_choix)
        self._proprietes.est_premiere = self._est_premiere
        self._proprietes.peut_creuser = self._peut_creuser
        self._proprietes.rendre_creusable = self._rendre_creusable
        self._proprietes.collage_change.connect(self._changer_collage)
        self._proprietes.coupe_validee.connect(self._valider_coupe)
        travail.addWidget(self._pile)
        travail.addWidget(self._viewer)
        travail.addWidget(self._proprietes)
        travail.setStretchFactor(1, 1)
        travail.setSizes([260, 800, 280])
        self._pages.addWidget(travail)

        self._barre_etat = QWidget()
        etat = QHBoxLayout(self._barre_etat)
        etat.setContentsMargins(12, 6, 12, 6)
        self._message = QLabel("")
        self._message.setFont(QFont(FONT_MAIN, 9))
        self._mesures = QLabel("")
        self._mesures.setFont(QFont(FONT_MAIN, 9))
        self._imprimante_lbl = QLabel("")
        self._imprimante_lbl.setFont(QFont(FONT_MAIN, 8))
        etat.addWidget(self._message, 1)
        etat.addWidget(self._mesures)
        etat.addSpacing(16)
        etat.addWidget(self._imprimante_lbl)
        racine.addWidget(self._barre_etat)
        # La barre du haut n'a de sens que devant une pièce : sur la page
        # d'accueil, « Enregistrer », « Annuler », « Exporter » ou « Envoyer à
        # neoSlice » ne peuvent rien faire, et « Nouveau » et « Ouvrir » y sont
        # déjà, en grand, au milieu de la page (retour d'Emmanuel).
        self._pages.currentChanged.connect(lambda _i: self._maj_barre_outils())
        self._maj_barre_outils()
        self._raccourcis()

    def _maj_barre_outils(self):
        """Les boutons du haut ne s'affichent que sur l'établi, jamais sur la
        page d'accueil. Le titre, lui, reste : c'est l'identité de la fenêtre."""
        sur_accueil = self._pages.currentWidget() is self._accueil
        for bouton in self._boutons.values():
            bouton.setVisible(not sur_accueil)

    def _raccourcis(self):
        """Ctrl+Z et Ctrl+Y (demande d'Emmanuel), plus Ctrl+Maj+Z que beaucoup
        de logiciels utilisent aussi pour rétablir. Posés sur la FENÊTRE : ils
        marchent même quand le clavier est pris par la vue 3D."""
        for touches, action in (("Ctrl+Z", self.annuler),
                                ("Ctrl+Y", self.retablir),
                                ("Ctrl+Shift+Z", self.retablir)):
            raccourci = QShortcut(QKeySequence(touches), self)
            raccourci.setContext(Qt.ShortcutContext.WindowShortcut)
            raccourci.activated.connect(action)

    def _barre_outils(self) -> QWidget:
        barre = QWidget()
        barre.setObjectName("panneau")
        lay = QHBoxLayout(barre)
        # Réglages RECOPIÉS de la barre de neoSlice (ui/main_window.py) : mêmes
        # marges, même filet, même taille de titre, pour que les deux fenêtres
        # commencent exactement pareil (demande d'Emmanuel).
        lay.setContentsMargins(12, 0, 16, 1)
        lay.setSpacing(12)
        self._filet = QFrame()
        self._filet.setFixedWidth(3)
        self._filet.setFixedHeight(28)
        lay.addWidget(self._filet, 0, Qt.AlignVCenter)
        self._titre = QLabel("neoForge")
        self._titre.setFont(QFont(FONT_MAIN, 26, QFont.Bold))
        lay.addWidget(self._titre, 0, Qt.AlignVCenter)
        # Sous-titre : même police et même taille que « AI-POWERED 3D PRINT
        # OPTIMIZER », en capitales, et CENTRÉ sur le milieu visible du titre.
        # Centrer les deux libellés ne suffit pas : la hampe du « g » descend et
        # tire l'encre du titre vers le bas, si bien que le sous titre, tout en
        # capitales, paraissait 4 px trop haut (mesuré au pixel). On rattrape
        # l'écart avec les métriques, sans constante en dur.
        self._soustitre = QLabel(T("sous_titre").upper())
        self._soustitre.setFont(QFont(FONT_MAIN, 8))
        # Les deux libellés restent centrés verticalement, et le sous titre
        # reçoit une MARGE HAUTE : avec un centrage, une marge `t` descend le
        # texte de `t/2`, seul comportement que la mesure ait confirmé. Ni
        # hauteur fixe (elle gonflait la barre de 36 à 48 px), ni alignement en
        # haut (le label s'étirait quand même sur toute la ligne).
        mt = QFontMetrics(self._titre.font())
        ms = QFontMetrics(self._soustitre.font())
        milieu_titre = mt.ascent() + (mt.descent() - mt.capHeight()) / 2.0
        milieu_sous = (mt.height() - ms.height()) / 2.0 + ms.ascent() - ms.capHeight() / 2.0
        # Rendement de la marge MESURÉ, et non déduit : marge 0 → milieu d'encre
        # à 17,5 px ; marge 8 → 23,5. Soit 0,75 px gagné par pixel de marge, le
        # label grandissant lui même et son centrage absorbant le reste.
        self._soustitre.setContentsMargins(
            0, max(0, round((milieu_titre - milieu_sous) / 0.75)), 0, 0)
        lay.addWidget(self._soustitre, 0, Qt.AlignVCenter)
        lay.addSpacing(18)

        self._boutons = {}
        for nom, texte, action in (
                ("nouveau", T("nouveau"), self.nouveau),
                ("ouvrir", T("ouvrir"), self.ouvrir),
                ("enregistrer", T("enregistrer"), self.enregistrer),
                ("annuler", T("annuler"), self.annuler),
                ("retablir", T("retablir"), self.retablir)):
            b = QPushButton(texte)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False, a=action: a())
            touches = {"nouveau": "Ctrl+N", "ouvrir": "Ctrl+O",
                       "enregistrer": "Ctrl+S", "annuler": "Ctrl+Z",
                       "retablir": "Ctrl+Y"}.get(nom)
            if touches:
                b.setToolTip(f"{texte}   ({touches})")
            lay.addWidget(b)
            self._boutons[nom] = b
        lay.addStretch()

        # Unité d'affichage : un bouton à menu, comme l'export juste à côté. Une
        # liste déroulante aurait demandé sa propre flèche dessinée et risquait
        # d'élargir la barre ; ce motif est déjà en place et déjà habillé.
        self._btn_unite = QPushButton(U.symbole(U.courante()))
        self._btn_unite.setCursor(Qt.PointingHandCursor)
        self._btn_unite.setToolTip(T("unite"))
        menu_unite = QMenu(self._btn_unite)
        for cle in ("mm", "cm", "in"):
            menu_unite.addAction(T(f"unite_{cle}"),
                                 lambda c=cle: self._changer_unite(c))
        self._btn_unite.setMenu(menu_unite)
        self._menu_unite = menu_unite
        lay.addWidget(self._btn_unite)
        self._boutons["unite"] = self._btn_unite

        self._btn_export = QPushButton(T("exporter"))
        self._btn_export.setCursor(Qt.PointingHandCursor)
        menu = QMenu(self._btn_export)
        for libelle, suffixe in ((T("fichier_stl"), ".stl"), (T("fichier_3mf"), ".3mf"),
                                 (T("fichier_step"), ".step")):
            menu.addAction(libelle, lambda s=suffixe: self.exporter(s))
        self._btn_export.setMenu(menu)
        self._menu_export = menu
        lay.addWidget(self._btn_export)

        self._btn_envoyer = QPushButton(T("envoyer"))
        self._btn_envoyer.setCursor(Qt.PointingHandCursor)
        self._btn_envoyer.setToolTip(T("envoyer_info"))
        self._btn_envoyer.clicked.connect(self.envoyer_a_neoslice)
        lay.addWidget(self._btn_envoyer)
        self._boutons["exporter"] = self._btn_export
        self._boutons["envoyer"] = self._btn_envoyer
        return barre

    # ── Thème ───────────────────────────────────────────────────────────────
    def _surveiller_theme(self):
        """neoForge est un autre programme : on suit le thème choisi dans
        neoSlice en surveillant son fichier de préférences."""
        from PySide6.QtCore import QFileSystemWatcher
        fichier = Path.home() / ".neoslice" / "prefs.json"
        if not fichier.exists():
            return
        self._veille = QFileSystemWatcher([str(fichier)], self)

        def relire(*_a):
            import json
            try:
                nom = json.loads(fichier.read_text(encoding="utf-8")).get("theme")
            except Exception:
                return
            if nom in ("dark", "light") and nom != _T.name():
                _T.switch(nom)
            if str(fichier) not in self._veille.files():
                self._veille.addPath(str(fichier))       # réécriture = nouveau fichier
        self._veille.fileChanged.connect(relire)

    def refresh_theme(self):
        p = S.pal()
        self.setStyleSheet(S.qss_fenetre())
        self.centralWidget().setStyleSheet(f"background: {p['BG_VOID']};")
        for w in (self._pile, self._proprietes, self._accueil):
            w.refresh_theme()
        self._viewer.refresh_theme()
        self._barre_etat.setStyleSheet(f"background: {p['BG_PANEL']};")
        self._filet.setStyleSheet(f"background: {p['INACTIVE']}; border-radius: 1px;")
        self._titre.setStyleSheet(
            f"color: {p['TEXT_PRIMARY']}; background: transparent;"
            f" font-size: 26px; font-weight: bold; letter-spacing: 0px;")
        for lbl in (self._soustitre, self._mesures, self._imprimante_lbl):
            lbl.setStyleSheet(f"color: {p['TEXT_LABEL']}; background: transparent;")
        self._message.setStyleSheet(f"color: {p['TEXT_SECONDARY']}; background: transparent;")
        for nom, b in self._boutons.items():
            b.setStyleSheet(S.qss_bouton("accent" if nom == "envoyer" else "secondaire"))
        for m in (self._menu_export, self._menu_unite):
            m.setStyleSheet(S.qss_menu())
        self.setWindowIcon(icone())

    # ── Projet ──────────────────────────────────────────────────────────────
    def nouveau(self, projet: Projet | None = None):
        if not self._confirmer_abandon():
            return
        self._projet = projet if isinstance(projet, Projet) else Projet.nouveau()
        self._chemin = None
        self._historique.vider()
        self._constructeur = Constructeur()
        # Une scène neuve est VIDE : il n'y a donc rien à sélectionner.
        self._selection = 0 if self._projet.etapes else -1
        self._modifie = False
        self._pages.setCurrentIndex(1)
        self._maj_titre()
        self._lancer_calcul()

    def ouvrir(self, chemin: Path | None = None):
        if not self._confirmer_abandon():
            return
        if not isinstance(chemin, Path):
            nom, _f = QFileDialog.getOpenFileName(self, T("ouvrir"),
                                                  str(nfg.dossier_sortie(self._chemin)),
                                                  T("projet_neoforge"))
            if not nom:
                return
            chemin = Path(nom)
        try:
            self._projet = nfg.lire(chemin)
        except Exception:
            D.avertir(self, "neoForge", T("ouverture_impossible"))
            return
        self._chemin = chemin
        self._historique.vider()
        self._constructeur = Constructeur()
        self._selection = 0
        self._modifie = False
        self._pages.setCurrentIndex(1)
        self._maj_titre()
        self._lancer_calcul()

    def enregistrer(self) -> bool:
        if self._projet is None:
            return False
        chemin = self._chemin
        if chemin is None:
            nom, _f = QFileDialog.getSaveFileName(
                self, T("enregistrer"),
                str(nfg.dossier_sortie(self._chemin) / "piece.nfg"),
                T("projet_neoforge"))
            if not nom:
                return False
            chemin = Path(nom)
        try:
            self._chemin = nfg.ecrire(self._projet, chemin)
        except Exception as exc:
            D.avertir(self, "neoForge", T("enregistrement_impossible", err=exc))
            return False
        self._modifie = False
        self._maj_titre()
        self._statut(T("enregistre", nom=self._chemin.name))
        self._accueil.maj_recents(nfg.recents())
        return True

    def _proposer_reprise(self):
        """Après un arrêt brutal, on propose de reprendre la pièce en cours."""
        repris = nfg.auto_lire() if nfg.auto_disponible() else None
        if repris is None:
            self._accueil.maj_recents(nfg.recents())
            return
        projet, fichier = repris
        rep = D.demander(self, T("restaurer_titre"), T("restaurer_texte"),
                         [(T("restaurer_oui"), D.ACCEPTER),
                          (T("restaurer_non"), D.REFUSER)])
        if rep == 0:
            self.nouveau(projet)
            self._chemin = fichier if fichier and fichier.exists() else None
            self._modifie = True
            self._maj_titre()
        else:
            nfg.auto_effacer()
            self._accueil.maj_recents(nfg.recents())

    def _confirmer_abandon(self) -> bool:
        if self._projet is None or not self._modifie:
            return True
        # Boutons écrits PAR NOUS : les boutons standards de Qt sortent dans sa
        # propre langue (« Save », « Discard », « Cancel » même en français) et
        # ignorent le thème (retour d'Emmanuel sur la fenêtre de fermeture).
        rep = D.demander(self, T("quitter_titre"), T("quitter_texte"),
                         [(T("enregistrer"), D.ACCEPTER),
                          (T("quitter_sans"), D.DETRUIRE),
                          (T("quitter_annuler"), D.REFUSER)])
        if rep == 2:
            return False
        if rep == 0:
            return self.enregistrer()
        # « Ne pas enregistrer » : le travail est abandonné pour de bon, la
        # sauvegarde de secours n'a donc plus lieu d'être. Elle ne sert qu'à
        # reprendre après un arrêt BRUTAL, jamais après une sortie choisie.
        nfg.auto_effacer()
        return True

    def _maj_titre(self):
        nom = self._chemin.stem if self._chemin else T("accueil_nouveau")
        self.setWindowTitle(f"neoForge — {nom}{' *' if self._modifie else ''}")

    # ── Modifications ───────────────────────────────────────────────────────
    def _memoriser(self):
        if self._projet is not None:
            self._historique.memoriser(self._projet)

    def _sur_modification(self, origine: str = "interne"):
        if origine == "panneau":
            self._appliquer_collage()
        self._modifie = True
        self._maj_titre()
        self._planifier_calcul()

    def _appliquer_collage(self):
        """Quand les pièces se collent, une position saisie s'arrête au contact
        de la pièce voisine (comme sur la console). Si elles se traversent, la
        valeur passe telle quelle."""
        if self._projet is None or not (0 <= self._selection < len(self._projet.etapes)):
            return
        etape = self._projet.etapes[self._selection]
        if not isinstance(etape, Forme):
            return
        avant = self._pos_reference
        self._pos_reference = list(etape.pos)
        if not self._collage or avant is None:
            return
        colle = False
        for axe in range(3):
            demande = etape.pos[axe] - avant[axe]
            if abs(demande) < 1e-9:
                continue
            etape.pos[axe] = avant[axe]              # on repart d'avant…
            reel = E.limiter(self._projet, self._selection, axe, demande, self._collage)
            etape.pos[axe] = avant[axe] + reel       # …puis on avance du possible
            colle = colle or abs(reel - demande) > 1e-6
        if colle:
            self._pos_reference = list(etape.pos)
            self._proprietes.set_etape(etape, self._collage)
            self._statut(T("deplacement_colle"), "attention")

    def _planifier_calcul(self):
        self._auto.start()

    def _ajouter_forme(self, quoi: str):
        if self._projet is None:
            return
        self._memoriser()
        etapes = self._projet.etapes
        # Jamais en tête de pile : la première forme est toujours de la matière
        # pour le moteur, et la nouvelle n'aurait plus pu creuser.
        ou = E.position_insertion(etapes, self._selection)
        base = self._selection if 0 <= self._selection < len(etapes) else None
        if quoi.startswith("ecrou:"):
            forme = E.logement_ecrou(self._projet, quoi.split(":", 1)[1], base)
        elif quoi.startswith("taraudage:"):
            forme = E.trou_taraude(self._projet, quoi.split(":", 1)[1], base)
        else:
            forme = E.nouvelle_forme(self._projet, quoi, base)
        etapes.insert(ou, forme)
        self._selection = ou
        self._sur_modification()

    def _ajouter_arrondi(self):
        if self._projet is None:
            return
        self._memoriser()
        # TOUJOURS en fin de pile : un arrondi s'applique à la pièce ASSEMBLÉE.
        # Posé juste après l'objet visé, il passait AVANT les enfants qui le
        # percent : cliquer « arrondir les arêtes » sur un parent troué montrait
        # alors la pièce PLEINE, sans ses trous, et n'en proposait évidemment pas
        # les arêtes (retour d'Emmanuel). Même cause que la pièce qui redevenait
        # entière après une découpe. La cible, elle, continue de restreindre les
        # arêtes proposées à l'objet visé ET à sa descendance, donc aux bords des
        # trous que ses enfants ont creusés.
        etapes = self._projet.etapes
        ou = len(etapes)
        # L'arrondi VISE l'objet sélectionné (et ses enfants). Rien de
        # sélectionné : il porte sur toute la pièce, comme avant.
        vise = self._forme_selectionnee()
        etapes.insert(ou, Arrondi("conge", 2.0, "liste",
                                  cible=vise.ident if vise is not None else ""))
        self._selection = ou
        self._proprietes.set_etape(etapes[ou], self._collage)
        self._proprietes.entrer_dans_le_choix()
        self._sur_modification()

    def _ajouter_coupe(self):
        """Tranche la pièce par un plan. Le plan se pose à MI HAUTEUR par
        défaut, donc dans la matière : la coupe se voit tout de suite, au lieu
        de tomber dans le vide et de ne rien faire."""
        if self._projet is None:
            return
        self._memoriser()
        etapes = self._projet.etapes
        ou = E.position_insertion(etapes, self._selection)
        milieu = 0.0
        if self._forme_finale is not None:
            try:
                (_x0, _y0, z0), (_x1, _y1, z1) = O.boite(self._forme_finale)
                milieu = round((z0 + z1) / 2.0, 1)
            except Exception:
                milieu = 0.0
        etapes.insert(ou, Coupe(2, milieu, "dessous"))
        self._selection = ou
        self._sur_modification()

    def _supprimer_selection(self):
        """Touche Suppr : l'étape sélectionnée disparaît (demande d'Emmanuel)."""
        if self._projet is None or self._mode_aretes:
            return
        self._action_pile("supprimer", self._selection)

    def keyPressEvent(self, event):
        if (event.key() == Qt.Key_Delete
                and self._pages.currentWidget() is not self._accueil):
            self._supprimer_selection()
            event.accept()
            return
        super().keyPressEvent(event)

    def _action_pile(self, nom: str, index: int):
        if self._projet is None or not (0 <= index < len(self._projet.etapes)):
            return
        etapes = self._projet.etapes
        # Plus de garde sur la DERNIÈRE forme : une scène vide est désormais un
        # état normal, au démarrage comme après une suppression (demande
        # d'Emmanuel : « enlever le il faut au moins une forme dans la pièce »).
        self._memoriser()
        if nom == "monter" and index > 0:
            etapes[index - 1], etapes[index] = etapes[index], etapes[index - 1]
            self._selection = index - 1
        elif nom == "descendre" and index < len(etapes) - 1:
            etapes[index + 1], etapes[index] = etapes[index], etapes[index + 1]
            self._selection = index + 1
        elif nom == "dupliquer":
            copie = copy.deepcopy(etapes[index])
            if isinstance(copie, Forme):
                copie.ident = identifiant()    # une copie est une AUTRE pièce
            etapes.insert(index + 1, copie)
            self._selection = index + 1
        elif nom == "masquer":
            etapes[index].actif = not etapes[index].actif
        elif nom == "verrou":
            forme = etapes[index]
            if not isinstance(forme, Forme):
                return
            forme.verrou = not forme.verrou
            self._statut(T("verrouille") if forme.verrou else T("deverrouille"), "ok")
        elif nom == "supprimer":
            partie = etapes.pop(index)
            if isinstance(partie, Forme):      # ses enfants redeviennent libres
                for e in etapes:
                    if isinstance(e, Forme) and e.parent == partie.ident:
                        e.parent = ""
            self._selection = max(0, index - 1)
        self._sur_modification()

    def _rattacher(self, enfant: int, parent: int):
        """Une pièce déposée sur une autre lui est RATTACHÉE : elle la suivra
        partout, déplacement comme rotation (idée d'Emmanuel). Déposée dans le
        vide, elle est détachée. Elle vient se ranger sous son parent dans la
        liste, pour qu'on voie l'assemblage."""
        if self._projet is None or self._mode_aretes:
            return
        cible = None if parent < 0 else parent
        if cible is not None and not E.peut_recevoir(self._projet, enfant, cible):
            self._statut(T("lien_impossible"), "attention")
            return
        self._memoriser()
        if not E.rattacher(self._projet, enfant, cible):
            return
        forme = self._projet.etapes[enfant]
        # Rattachée, la pièce est VERROUILLÉE d'office : c'est bien « elles ne
        # font plus qu'une » qui est demandé. Un clic sur le cadenas la libère
        # si on veut la réajuster toute seule.
        forme.verrou = cible is not None
        # Toute la pile est remise en ordre, pas seulement la pièce déplacée :
        # sinon, en détachant un enfant du milieu, il restait coincé entre le
        # parent et ses autres enfants (retour d'Emmanuel).
        E.ranger_hierarchie(self._projet)
        self._selection = self._projet.etapes.index(forme)
        self._statut(T("detache") if cible is None else T("rattache"), "ok")
        self._sur_modification()

    def _changer_selection(self, index: int):
        self._selection = index
        # Les deux morceaux d'une coupe « garder les deux » pointent vers la MÊME
        # étape : la pile dit lequel des deux on tient.
        self._partie = self._pile.partie()
        if self._mode_aretes:
            self._proprietes.sortir_du_choix()
        etape = (self._projet.etapes[index]
                 if self._projet and 0 <= index < len(self._projet.etapes) else None)
        self._pos_reference = list(etape.pos) if isinstance(etape, Forme) else None
        self._proprietes.set_etape(etape, self._collage)
        self._planifier_calcul()

    # ── Gestes dans la vue 3D ───────────────────────────────────────────────
    def _clic_fond(self):
        """Clic dans le vide : plus rien n'est sélectionné, les poignées
        disparaissent (demande d'Emmanuel).

        Sur une DÉCOUPE en cours de réglage, ce clic l'abandonne : « si on décide
        de cliquer dans le vide, le coupage de plan doit s'annuler ». Une coupe
        se valide par son bouton, jamais en cliquant à côté."""
        if self._projet is None or self._mode_aretes:
            return
        i, etapes = self._selection, self._projet.etapes
        if 0 <= i < len(etapes) and isinstance(etapes[i], Coupe):
            self._memoriser()
            etapes.pop(i)
            self._selection = -1
            self._pile.deselectionner()
            self._sur_modification()
            return
        self._pile.deselectionner()

    def _clic_piece(self, point):
        """Clic sur la pièce : on sélectionne la forme dont on vient de toucher
        la surface (le bord d'un trou sélectionne le trou)."""
        if self._projet is None or self._mode_aretes:
            return
        from neoforge.noyau.selection import etape_au_point
        try:
            index = etape_au_point(self._projet, point)
        except Exception:
            return
        if index is not None and index != self._selection:
            self._pile.selectionner(index)

    def _forme_selectionnee(self) -> Forme | None:
        if self._projet is None or not (0 <= self._selection < len(self._projet.etapes)):
            return None
        etape = self._projet.etapes[self._selection]
        return etape if isinstance(etape, Forme) else None

    def _commencer_geste(self) -> Forme | None:
        etape = self._forme_selectionnee()
        if etape is None:
            return None
        if not self._glisse:                 # un seul point d'annulation par geste
            self._memoriser()
            self._glisse = True
        return etape

    def _changer_unite(self, choix: str):
        """L'unité d'AFFICHAGE change : la pièce, elle, ne bouge pas d'un cheveu.

        Demande d'Emmanuel : « que par défaut les mesures apparaissent en mm et
        non en cm, mais qu'on puisse avoir le choix dans les réglages ». Le choix
        est retenu pour la prochaine ouverture, dans les préférences que neoForge
        partage avec neoSlice."""
        unite = U.definir(choix)
        nfg.definir_unite(unite)
        self._btn_unite.setText(U.symbole(unite))
        self._proprietes.definir_unite(unite)
        # Les cotes gravées dans la vue et la ligne de mesure se refont au
        # recalcul, déjà groupé par la minuterie : rien à rafraîchir à la main.
        if self._projet is not None:
            self._planifier_calcul()

    def _poignees_partie(self, coupe, boite):
        """Des poignées sur le MORCEAU choisi, pour l'écarter de l'autre.

        Un morceau n'est pas une étape : on décrit sa boîte à la volée et on la
        donne au viewer comme s'il s'agissait d'une pièce, sans aperçu vert
        (le morceau est déjà visible dans la scène). Passer en mode Déplacer se
        fait à la main, comme pour n'importe quelle pièce."""
        import numpy as _np

        from neoforge.noyau.construction import ECART_COUPE

        bas = [float(v) for v in boite[0]]
        haut = [float(v) for v in boite[1]]
        axe = int(coupe.axe)
        if self._partie == "bas":
            haut[axe] = min(haut[axe], float(coupe.position))
        else:
            bas[axe] = max(bas[axe], float(coupe.position))
            for k in range(3):        # le morceau du haut est déjà écarté
                pas = (ECART_COUPE if k == axe else 0.0) + float(coupe.decalage[k])
                bas[k] += pas
                haut[k] += pas
        centre = [(bas[k] + haut[k]) / 2.0 for k in range(3)]
        demi = [max(0.5, (haut[k] - bas[k]) / 2.0) for k in range(3)]
        faux = Forme("cube", "matiere", centre, [d * 2.0 for d in demi])
        vide = (_np.zeros((0, 3), float), _np.zeros((0, 3), _np.int64))
        self._viewer.preparer_manipulation(faux, vide, [], False, [],
                                           [0.0, 0.0, 0.0], demi)

    def _deplacer_partie(self, axe: int, delta: float) -> bool:
        """Le morceau du HAUT se déplace, celui du bas reste en place : c'est lui
        qui tient la pièce. Renvoie vrai si le geste a été pris en charge."""
        if not self._partie or self._projet is None:
            return False
        i, etapes = self._selection, self._projet.etapes
        if not (0 <= i < len(etapes)) or not isinstance(etapes[i], Coupe):
            return False
        if self._partie == "bas":
            self._statut(T("partie_bas_fixe"), "attention")
            return True
        coupe = etapes[i]
        if not self._glisse:                 # un seul point d'annulation par geste
            self._memoriser()
            self._glisse = True
        coupe.decalage[axe] = round(float(coupe.decalage[axe]) + float(delta), 1)
        self._modifie = True
        self._maj_titre()
        return True

    def _valider_coupe(self):
        """Bouton Valider d'une découpe : on quitte le réglage, la coupe reste."""
        if self._projet is None:
            return
        self._pile.deselectionner()

    def _mesures_coupe(self, coupe):
        """Les mesures des morceaux PENDANT le réglage du plan.

        « J'aimerais qu'on voie les mesures de chaque côté si on choisit de garder
        les deux, sinon celles de la partie qu'on garde, et qu'on les voie se
        modifier EN MÊME TEMPS qu'on glisse, pas une fois le bouton relâché. »
        Simple arithmétique sur la boîte de la pièce : aucun appel au noyau, donc
        rien ne vient ralentir le geste."""
        boite = self._boite_coupe
        if boite is None or not isinstance(coupe, Coupe):
            return
        bas = [float(v) for v in boite[0]]
        haut = [float(v) for v in boite[1]]
        axe, position = int(coupe.axe), float(coupe.position)

        def morceau(dessous: bool):
            b, h = list(bas), list(haut)
            if dessous:
                h[axe] = min(h[axe], position)
            else:
                b[axe] = max(b[axe], position)
            return [h[k] - b[k] for k in range(3)]

        tailles = []
        if coupe.garder in ("dessous", "les_deux"):
            tailles.append(morceau(True))
        if coupe.garder in ("dessus", "les_deux"):
            tailles.append(morceau(False))
        unite = U.courante()
        textes = [T("taille_piece", x=U.texte(t[0], unite), y=U.texte(t[1], unite),
                    z=U.texte(t[2], unite), u=U.symbole(unite))
                  for t in tailles if min(t) > 1e-6]
        self._mesures.setText("   ·   ".join(textes))

    def _plan_deplace(self, delta: float):
        """Le plan de coupe est tiré à la souris : il suit tout de suite, et la
        pièce n'est retranchée qu'au relâchement (demande d'Emmanuel :
        « j'aimerais aussi qu'on puisse glisser le plan avec la souris »).

        Retrancher à chaque pas de souris demanderait un booléen du noyau par
        pas et le geste traînerait : seul le plan bouge pendant le glissement,
        exactement comme l'aperçu d'une pièce qu'on déplace."""
        if self._projet is None or not (0 <= self._selection < len(self._projet.etapes)):
            return
        coupe = self._projet.etapes[self._selection]
        if not isinstance(coupe, Coupe):
            return
        if not self._glisse:                 # un seul point d'annulation par geste
            self._memoriser()
            self._glisse = True
        coupe.position = round(float(coupe.position) + float(delta), 1)
        self._viewer.placer_plan(coupe.position)
        self._mesures_coupe(coupe)        # les cotes suivent la souris, en direct
        self._modifie = True
        self._maj_titre()

    def _taille_modifiee(self, axe: int, delta: float, sens: int):
        """Une poignée de cote est tirée : la taille suit la souris, la face
        opposée reste en place."""
        etape = self._commencer_geste()
        if etape is None:
            return
        applique = E.redimensionner(etape, axe, delta, sens)
        if abs(applique) < 1e-9 and abs(delta) > 1e-6:
            self._statut(T("cote_bloquee"), "attention")
        self._apercu(etape)

    def _deplacement(self, axe: int, delta: float):
        """La pièce est tirée par une flèche. Si les pièces se collent, elle
        s'arrête au contact de sa voisine."""
        # Un MORCEAU de découpe n'est pas une forme : le geste porte alors sur le
        # décalage rangé dans la coupe, pas sur une pièce de la pile.
        if self._deplacer_partie(axe, delta):
            return
        etape = self._commencer_geste()
        if etape is None:
            return
        # La flèche est l'axe PROPRE de la pièce : elle tourne avec elle. On
        # déplace donc le long de CETTE direction et non de l'axe du monde,
        # sinon une pièce orientée partait de travers (retour d'Emmanuel).
        # Une pièce VERROUILLÉE ne bouge pas seule : le geste s'applique à son
        # parent et c'est tout l'ensemble qui suit (demande d'Emmanuel).
        cible = E.cible_du_geste(self._projet, self._selection)
        reel = E.deplacer_selon(self._projet, cible,
                                E.direction_axe(etape, axe), delta, self._collage)
        if abs(reel - delta) > 1e-6:
            self._statut(T("deplacement_colle"), "attention")
        self._apercu(etape)

    def _rotation(self, axe: int, degres: float):
        """La pièce tourne, et tout ce qui lui est collé tourne avec elle : un
        trou percé dedans reste à sa place (demande d'Emmanuel)."""
        etape = self._commencer_geste()
        if etape is None:
            return
        E.tourner_groupe(self._projet,
                         E.cible_du_geste(self._projet, self._selection),
                         E.direction_axe(etape, axe), degres)
        self._apercu(etape)

    def _apercu(self, etape: Forme):
        """Pendant un geste : on REPLACE l'aperçu déjà construit, sans rien
        recalculer. C'est ce qui rend le geste instantané ; la pièce complète
        est recalculée au relâchement."""
        self._pos_reference = list(etape.pos)
        self._modifie = True
        # Le panneau de droite n'est PAS réécrit à chaque pixel (neuf compteurs
        # à remplir, c'est la moitié du temps d'un pas) : il se remet à jour au
        # relâchement. Seule la mesure du bas suit le geste.
        # Les chiffres des cotes suivent le geste (mise à jour EN PLACE, sans
        # recréer d'acteur : la reconstruction coûtait 36 ms par pas).
        from neoforge.projet.mesures import cotes as _cotes, echelle_apercu
        libelles = [c.libelle for c in _cotes(etape) if c.libelle]
        echelle = echelle_apercu(etape, self._dim_apercu)
        if echelle is None:
            # Un cône dont les diamètres changent ne se met pas à l'échelle :
            # on refabrique son aperçu (quelques millisecondes).
            self._preparer_manipulation()
            return
        poses = [(list(self._projet.etapes[k].pos), list(self._projet.etapes[k].rot))
                 for k in self._compagnons
                 if 0 <= k < len(self._projet.etapes)]
        self._viewer.placer_apercu(etape.pos, etape.rot, echelle, libelles, poses)
        unite = U.courante()
        self._mesures.setText(T("taille_piece", x=U.court(etape.dim[0], unite),
                                y=U.court(etape.dim[1], unite),
                                z=U.court(etape.dim[2], unite),
                                u=U.symbole(unite)))

    def _geste_fini(self):
        """Bouton relâché : le panneau se remet à jour et la pièce entière est
        enfin recalculée."""
        if not self._glisse:
            return
        self._glisse = False
        self._maj_titre()
        etape = self._forme_selectionnee()
        if etape is not None:
            self._proprietes.set_etape(etape, self._collage)
        self._planifier_calcul()

    def _preparer_manipulation(self):
        """Construit UNE fois l'aperçu de la forme sélectionnée (dans son repère
        propre) et ses poignées ; les gestes ne feront que les replacer."""
        # Le plan de coupe ne se montre que quand la découpe elle-même est
        # sélectionnée : posé en permanence, il masquerait la pièce.
        choisie = (self._projet.etapes[self._selection]
                   if self._projet is not None
                   and 0 <= self._selection < len(self._projet.etapes) else None)
        if isinstance(choisie, Coupe) and choisie.actif:
            boite = self._boite
            try:
                # La boîte d'AVANT la coupe : le plan couvre alors toute la
                # matière qu'il tranche, et non le seul morceau qui reste.
                avant = (self._resultats[self._selection - 1].forme
                         if self._selection > 0 else None)
                if avant is not None:
                    boite = O.boite(avant)
            except Exception:
                pass
            self._boite_coupe = boite
            self._mesures_coupe(choisie)
            if self._partie:
                # Un MORCEAU est choisi : il n'y a pas de plan à régler, mais des
                # poignées pour l'écarter de l'autre (choix d'Emmanuel : deux
                # lignes dans la liste, déplaçables séparément).
                self._viewer.cacher_plan_coupe()
                self._poignees_partie(choisie, boite)
                return
            self._viewer.montrer_plan_coupe(choisie.axe, choisie.position, boite)
        else:
            self._boite_coupe = None
            self._viewer.cacher_plan_coupe()
        etape = self._forme_selectionnee()
        if etape is None or not etape.actif:
            self._dim_apercu = [1.0, 1.0, 1.0]
            self._compagnons = []
            self._viewer.preparer_manipulation(None, (None, None), [], False)
            return
        self._dim_apercu = list(etape.dim)      # taille de référence de l'aperçu
        from neoforge.projet.decoupes import coupes_apres, plans_locaux
        from neoforge.projet.mesures import geometrie_cotes_locale
        from neoforge.ui.apercu import couper_maillage, maillage_local
        repere = Forme(etape.forme, etape.op, [0.0, 0.0, 0.0], list(etape.dim),
                       [0.0, 0.0, 0.0])
        # ⚠️ TOUS les réglages de forme doivent être recopiés, pas seulement les
        # côtés : un cadre sans son épaisseur de bord, un engrenage sans son
        # profil de dents ne sont plus la même pièce à l'écran.
        for reglage in ("cotes", "bord", "pas", "variante"):
            setattr(repere, reglage, getattr(etape, reglage))
        try:
            # Sans passer par le noyau : quelques dixièmes de milliseconde, ce
            # qui permet de REFAIRE l'aperçu en plein geste (cône, voir _apercu).
            # Une découpe placée APRÈS cette forme en retire une moitié : sans ce
            # rognage, la surbrillance montrait encore la moitié disparue.
            maillage = couper_maillage(
                *maillage_local(repere),
                plans_locaux(etape, coupes_apres(self._projet, self._selection)))
        except Exception:
            # Sortir en laissant l'aperçu précédent AFFICHÉ montrait la forme
            # d'avant, en surbrillance, par dessus la bonne : on efface.
            logger.exception("neoForge : aperçu impossible")
            self._viewer.preparer_manipulation(None, (None, None), [], False)
            return
        premiere = next((k for k, e in enumerate(self._projet.etapes)
                         if isinstance(e, Forme) and e.actif), None)
        creux = (self._selection != premiere and etape.op != "matiere")
        # Toutes les pièces que le geste va emmener : le parent si la pièce est
        # verrouillée, et dans tous les cas la descendance. Elles sont montrées
        # en aperçu elles aussi, sinon l'assemblage paraît se disloquer pendant
        # le glissement (retour d'Emmanuel).
        cible = E.cible_du_geste(self._projet, self._selection)
        compagnons = []
        self._compagnons = []
        for k in E.groupe(self._projet, cible):
            f = self._projet.etapes[k]
            if k == self._selection or not isinstance(f, Forme) or not f.actif:
                continue
            try:
                voisine = Forme(f.forme, f.op, [0.0, 0.0, 0.0], list(f.dim),
                                [0.0, 0.0, 0.0])
                for reglage in ("cotes", "bord", "pas", "variante"):
                    setattr(voisine, reglage, getattr(f, reglage))
                compagnons.append({
                    "maillage": couper_maillage(
                        *maillage_local(voisine),
                        plans_locaux(f, coupes_apres(self._projet, k))),
                    "pos": list(f.pos), "rot": list(f.rot),
                    "creux": (k != premiere and f.op != "matiere")})
                self._compagnons.append(k)
            except Exception:
                continue
        # La matière qui RESTE après les découpes donne le vrai centre et la
        # vraie étendue. Sans elles, les poignées se posaient autour de la forme
        # d'origine : sur un socle coupé à 10 mm, le point d'origine restait à
        # 15 mm, soit 10 mm au dessus de la matière (mesuré au pilote). Si une
        # coupe ne laisse plus rien, l'aperçu est vide et on retombe sur la
        # forme entière plutôt que sur une étendue nulle.
        centre_local = demi_local = None
        sommets = maillage[0] if maillage is not None else None
        if sommets is not None and len(sommets):
            import numpy as _np
            bas, haut = _np.min(sommets, axis=0), _np.max(sommets, axis=0)
            centre_local = ((bas + haut) / 2.0).tolist()
            demi_local = ((haut - bas) / 2.0).tolist()
        self._viewer.preparer_manipulation(
            etape, maillage,
            geometrie_cotes_locale(etape, demi=demi_local, centre=centre_local),
            creux, compagnons, centre_local, demi_local)

    def _geste(self, nom: str):
        if self._projet is None or not (0 <= self._selection < len(self._projet.etapes)):
            return
        if not isinstance(self._projet.etapes[self._selection], Forme):
            return
        self._memoriser()
        if nom == "poser":
            E.poser(self._projet, self._selection)
        elif nom == "centrer_plateau":
            E.centrer_plateau(self._projet, self._selection)
        else:
            E.centrer(self._projet, self._selection)
        self._proprietes.set_etape(self._projet.etapes[self._selection], self._collage)
        self._sur_modification()

    def _est_premiere(self, etape) -> bool:
        """Cette forme est elle la PREMIÈRE active ? Celle là est toujours de la
        matière : il n'y a rien à creuser avant elle (règle du moteur, héritée
        de la console)."""
        if self._projet is None or not isinstance(etape, Forme):
            return False
        premiere = next((e for e in self._projet.etapes
                         if isinstance(e, Forme) and e.actif), None)
        return premiere is etape

    def _autre_forme_active(self, etape) -> int | None:
        """Index de la première AUTRE forme active de la pièce, s'il y en a une."""
        if self._projet is None:
            return None
        return next((k for k, e in enumerate(self._projet.etapes)
                     if e is not etape and isinstance(e, Forme) and e.actif), None)

    def _peut_creuser(self, etape) -> bool:
        """Cette forme peut elle creuser ou intersecter ?

        Oui dès qu'il y a de la matière à entamer, même si elle est posée AVANT
        elle dans la pile : dans ce cas on la descendra au moment du clic. Non
        quand elle est toute seule, et là le bouton reste grisé avec sa bulle,
        parce qu'il n'y a réellement rien à creuser."""
        if not isinstance(etape, Forme):
            return False
        if not (self._est_premiere(etape)):
            return True
        return self._autre_forme_active(etape) is not None

    def _rendre_creusable(self, etape) -> bool:
        """Descend la forme juste après la première autre forme active, pour
        qu'elle ait enfin quelque chose à creuser. Renvoie False s'il n'y a
        rien à creuser du tout."""
        autre = self._autre_forme_active(etape)
        if autre is None:
            return False
        etapes = self._projet.etapes
        self._memoriser()
        depart = etapes.index(etape)
        etapes.pop(depart)
        # Retirer notre forme décale d'un cran tout ce qui la suivait : la
        # forme à creuser est donc en `autre - 1` si elle était après nous.
        voisine = autre - 1 if autre > depart else autre
        etapes.insert(voisine + 1, etape)      # juste APRÈS elle
        self._selection = etapes.index(etape)
        # Pas besoin de redessiner la liste ici : le changement d'opération
        # déclenche un recalcul, et c'est lui qui la remplit.
        self._statut(T("descendue_pour_creuser"), "info")
        return True

    def _coupe_sans_effet(self) -> bool:
        """Le plan de coupe tombe hors de la pièce, donc rien n'est retiré : cela
        ressemble à une panne, on le DIT plutôt que de déplacer le plan à la
        place de l'utilisateur. « Garder les deux » est exclu : là, conserver
        tout le volume est justement le but."""
        i = self._selection
        if not (0 <= i < len(self._projet.etapes)) or i >= len(self._resultats):
            return False
        etape = self._projet.etapes[i]
        if not isinstance(etape, Coupe) or not etape.actif \
                or etape.garder == "les_deux":
            return False
        apres = self._resultats[i].forme
        avant = self._resultats[i - 1].forme if i > 0 else None
        if apres is None or avant is None:
            return False
        try:
            return abs(O.volume(apres) - O.volume(avant)) < 1e-6
        except Exception:
            return False

    def _forme_isolee(self) -> bool:
        """La forme sélectionnée creuse ou intersecte, mais ne touche AUCUNE
        autre pièce : l'opération ne changera donc rien. On le signale sans
        jamais déplacer la forme (« je ne veux pas que la forme bouge »)."""
        i = self._selection
        if not (0 <= i < len(self._projet.etapes)):
            return False
        forme = self._projet.etapes[i]
        if not isinstance(forme, Forme) or not forme.actif or forme.op == "matiere":
            return False
        ensemble = set(E.groupe(self._projet, i))
        return not any(isinstance(e, Forme) and e.actif and E.se_touchent(forme, e)
                       for k, e in enumerate(self._projet.etapes) if k not in ensemble)

    def _changer_collage(self, actif: bool):
        self._collage = bool(actif)

    def annuler(self):
        if self._projet is None:
            return
        avant = self._historique.annuler(self._projet)
        if avant is None:
            return
        self._projet = avant
        self._selection = min(self._selection, len(self._projet.etapes) - 1)
        self._sur_modification()

    def retablir(self):
        if self._projet is None:
            return
        apres = self._historique.retablir(self._projet)
        if apres is None:
            return
        self._projet = apres
        self._selection = min(self._selection, len(self._projet.etapes) - 1)
        self._sur_modification()

    # ── Choix d'arêtes ──────────────────────────────────────────────────────
    def _rafraichir_regle(self):
        """La pièce a changé pendant qu'on mesure : les arêtes visées ne sont
        plus les bonnes. Sans cela, la souris s'accrocherait aux fantômes des
        arêtes d'avant."""
        if getattr(self._viewer, "_mode_regle", False):
            self._mode_regle(True)

    def _mode_regle(self, actif: bool):
        """La règle s'allume : on lui donne TOUTES les arêtes de la pièce, en
        millimètres. C'est sur elles que la souris s'accroche, et c'est assez
        léger pour être calculé à l'allumage plutôt qu'à chaque recalcul."""
        lignes = []
        if actif and self._forme_finale is not None:
            try:
                from neoforge.noyau.aretes import toutes_les_aretes
                lignes = [polyligne(e) for e in toutes_les_aretes(self._forme_finale)]
            except Exception:
                logger.exception("neoForge : arêtes de la règle illisibles")
                lignes = []
        self._viewer.mode_regle(actif, lignes)
        self._statut(T("regle_aide") if actif else "")

    def _mode_choix(self, actif: bool):
        self._mode_aretes = bool(actif)
        self._viewer.mode_choix_aretes(self._mode_aretes)
        self._planifier_calcul()

    def _clic_arete(self, index: int):
        if self._projet is None or not self._mode_aretes:
            return
        etape = self._projet.etapes[self._selection]
        if not isinstance(etape, Arrondi) or index >= len(self._signatures):
            return
        sig = self._signatures[index]
        self._memoriser()
        deja = [s for s in etape.aretes if s.get("milieu") == sig.get("milieu")
                and s.get("genre") == sig.get("genre")]
        if deja:
            etape.aretes = [s for s in etape.aretes if s not in deja]
        else:
            etape.aretes = list(etape.aretes) + [sig]
        self._proprietes.maj_compte_aretes(len(etape.aretes))
        self._sur_modification()

    # ── Calcul ──────────────────────────────────────────────────────────────
    def _lancer_calcul(self):
        if self._projet is None:
            return
        if self._calcul is not None and self._calcul.isRunning():
            self._recalcul_demande = True
            return
        self._statut(T("calcul"))
        self._calcul = _Calcul(self._constructeur, self._projet, self._selection,
                               self._mode_aretes, self)
        self._calcul.fini.connect(self._calcul_fini)
        self._calcul.start()

    def _calcul_fini(self, sortie: dict):
        self._calcul = None
        # La fenêtre est fermée : ne rien écrire et ne rien peindre. Sans cette
        # garde, un résultat en retard réécrivait la sauvegarde de secours, et
        # repeindre une vue 3D déjà fermée levait une erreur (caméra invalide,
        # « cannot convert float NaN to integer », vu au pilote).
        if self._ferme:
            return
        if sortie.get("erreur"):
            self._statut(T("err_geometrie"))
        self._resultats = sortie["resultats"]
        self._forme_finale = sortie["forme"]
        self._V, self._F = sortie["V"], sortie["F"]
        self._signatures = sortie["signatures"]
        self._boite = sortie.get("boite")
        if self._projet is not None:
            self._pile.remplir(self._projet.etapes, self._resultats, self._selection)
            etape = (self._projet.etapes[self._selection]
                     if 0 <= self._selection < len(self._projet.etapes) else None)
            self._proprietes.set_etape(etape, self._collage)
        # UNE seule image quand tout est à jour : la pièce, les arêtes et les
        # poignées changent ensemble. Sinon on aperçoit la nouvelle pièce avec
        # l'ancien aperçu et l'objet semble sauter (retour d'Emmanuel).
        self._viewer.geler()
        try:
            if self._V is not None:
                self._viewer.afficher_piece(
                    sortie["Va"] if sortie["Va"] is not None else self._V,
                    sortie["Fa"] if sortie["Fa"] is not None else self._F)
            else:
                # ⚠️ Scène VIDE : il faut le DIRE au viewer. Sans ce cas, on ne
                # l'appelait tout simplement pas, et l'ancienne pièce restait
                # affichée après une suppression, « jusqu'à ce qu'on ajoute une
                # nouvelle pièce » (retour d'Emmanuel, deux fois). Ma première
                # vérification comptait les ACTEURS de la vue, identiques avant
                # et après, et concluait à tort que tout allait bien : c'est la
                # MATIÈRE affichée qu'il fallait mesurer.
                self._viewer.afficher_piece(np.zeros((0, 3)),
                                            np.zeros((0, 3), dtype=int))
            # Visibles aussi hors du mode de choix, quand l'étape sélectionnée
            # retient des arêtes : c'est la mémoire de ce qu'elle arrondit.
            self._viewer.afficher_aretes(
                sortie["aretes"], sortie["choisies"],
                visibles=self._mode_aretes or bool(sortie["aretes"]))
            self._preparer_manipulation()
        finally:
            self._viewer.degeler()
        self._maj_mesures(sortie)
        # Les deux avertissements sont posés APRÈS la mesure : sinon elle les
        # efface aussitôt et on ne les voit jamais (constaté au pilote). Ils
        # expliquent pourquoi creuser ne retire rien, plutôt que de laisser le
        # silence faire croire à une panne.
        if self._projet is not None:
            tete = next((e for e in self._projet.etapes
                         if isinstance(e, Forme) and e.actif), None)
            if tete is not None and tete.op != "matiere":
                # Forme de tête : le moteur la traite en matière, quoi qu'on
                # demande, puisqu'il n'y a rien à creuser avant elle.
                self._statut(T("premiere_matiere"), "attention")
            elif self._forme_isolee():
                self._statut(T("ne_touche_rien"), "attention")
            elif self._coupe_sans_effet():
                self._statut(T("coupe_sans_effet"), "attention")
        if self._projet is not None:
            nfg.auto_enregistrer(self._projet, self._chemin)
        if self._recalcul_demande:
            self._recalcul_demande = False
            self._planifier_calcul()
        self._rafraichir_regle()

    def _cotes_de_la_selection(self) -> list[dict]:
        """Les cotes vertes à tracer sur la forme sélectionnée : une ligne par
        côté réglable, avec ses deux poignées, et le chiffre une seule fois
        quand deux côtés mesurent la même chose."""
        if self._projet is None or self._mode_aretes:
            return []
        if not (0 <= self._selection < len(self._projet.etapes)):
            return []
        etape = self._projet.etapes[self._selection]
        if not isinstance(etape, Forme) or not etape.actif:
            return []
        from neoforge.projet.mesures import geometrie_cotes
        return geometrie_cotes(etape)

    def _maj_mesures(self, sortie: dict):
        boite = sortie.get("boite")
        if boite is None or self._V is None:
            self._mesures.setText("")
            self._statut("")
            return
        (x0, y0, z0), (x1, y1, z1) = boite
        unite = U.courante()
        self._mesures.setText(
            T("taille_piece", x=U.texte(x1 - x0, unite), y=U.texte(y1 - y0, unite),
              z=U.texte(z1 - z0, unite), u=U.symbole(unite))
            + "   ·   " + T("volume", v=U.volume(sortie["volume"], unite),
                            u=U.symbole_volume(unite)))
        # Une DÉCOUPE sélectionnée parle d'elle même : on montre la taille des
        # MORCEAUX plutôt que celle de la pièce entière. Posé ici et non plus
        # tôt, sinon la mesure du recalcul l'écrase aussitôt (même piège que les
        # avertissements de la barre d'état, mesuré au pilote).
        i = self._selection
        etapes = self._projet.etapes if self._projet is not None else []
        if 0 <= i < len(etapes) and isinstance(etapes[i], Coupe) and etapes[i].actif:
            self._mesures_coupe(etapes[i])
        # Une étape en erreur passe AVANT l'imprimabilité : la pièce affichée est
        # la dernière valide, dire « prête à imprimer » masquerait le problème.
        rate = next(((i, r) for i, r in enumerate(self._resultats) if r.erreur), None)
        if rate is not None:
            i, r = rate
            detail = r.detail or {}
            if r.erreur == "trop_grand" and detail.get("max"):
                texte = T("err_trop_grand_max", max=detail["max"])
            else:
                from neoforge.ui.pile import MESSAGES
                texte = T(MESSAGES.get(r.erreur, "err_geometrie"))
            self._statut(f"{i + 1}. {texte}", "attention")
            return
        constats = X.verifier(self._V, self._F, self._plateau)
        if not constats:
            self._statut(T("verif_ok"), "ok")
        else:
            grave = next((c for c in constats if c.gravite == X.BLOQUANT), constats[0])
            self._statut(self._texte_constat(grave),
                         "erreur" if grave.gravite == X.BLOQUANT else "attention")

    def _texte_constat(self, c) -> str:
        if c.code == "trop_grande":
            t, p = c.detail["taille"], c.detail["plateau"]
            return T("verif_trop_grande", x=t[0], y=t[1], z=t[2],
                     px=p[0], py=p[1], pz=p[2])
        if c.code == "morceaux":
            return T("verif_morceaux", n=c.detail["n"])
        if c.code == "trop_fine":
            return T("verif_trop_fine", mm=c.detail["mm"])
        return T("verif_ouverte" if c.code == "ouverte" else "err_vide")

    def _statut(self, texte: str, genre: str = "info"):
        p = S.pal()
        couleur = {"ok": p["TELE_GREEN"], "attention": p["AMBER"],
                   "erreur": p["ERROR_RED"]}.get(genre, p["TEXT_SECONDARY"])
        self._message.setText(texte)
        self._message.setStyleSheet(f"color: {couleur}; background: transparent;")

    # ── Imprimante (demandée à neoSlice) ────────────────────────────────────
    def _demander_imprimante(self):
        rep = P.envoyer(P.NOM_PONT, P.emballer({"type": "imprimante"}), delai_ms=1500)
        if not rep or rep.get("type") != "imprimante":
            return
        plateau = rep.get("plateau") or list(PLATEAU_DEFAUT)
        self._plateau = tuple(float(v) for v in plateau[:3])
        self._nom_imprimante = str(rep.get("nom", ""))
        self._imprimante_lbl.setText(T("imprimante", nom=self._nom_imprimante))
        self._viewer.taille_plateau(self._plateau[0], self._plateau[1])

    # ── Export et envoi ─────────────────────────────────────────────────────
    def _pret_a_sortir(self) -> bool:
        """Vrai si on peut sortir la pièce, après avertissement clair au besoin."""
        if self._V is None or self._F is None or not len(self._F):
            D.informer(self, "neoForge", T("envoi_vide"))
            return False
        constats = X.verifier(self._V, self._F, self._plateau)
        if not constats:
            return True
        bloquants = [c for c in constats if c.gravite == X.BLOQUANT]
        texte = "\n".join("• " + self._texte_constat(c) for c in constats)
        if not bloquants:
            D.informer(self, T("avert_titre"), texte)
            return True
        boite = QMessageBox(QMessageBox.Warning, T("avert_titre"), texte, parent=self)
        boite.setStyleSheet(S.qss_dialogue())
        quand_meme = boite.addButton(T("exporter_quand_meme"), QMessageBox.AcceptRole)
        boite.addButton(T("corriger"), QMessageBox.RejectRole)
        boite.exec()
        return boite.clickedButton() is quand_meme

    def exporter(self, suffixe: str):
        if self._projet is None or not self._pret_a_sortir():
            return
        filtre = {".stl": T("fichier_stl"), ".3mf": T("fichier_3mf"),
                  ".step": T("fichier_step")}[suffixe]
        defaut = (self._chemin.stem if self._chemin else "piece") + suffixe
        nom, _f = QFileDialog.getSaveFileName(
            self, T("exporter"),
            str(nfg.dossier_sortie(self._chemin) / defaut), filtre)
        if not nom:
            return
        chemin = Path(nom)
        try:
            if suffixe == ".step":
                X.exporter_step(self._forme_finale, chemin)
            else:
                V = X.poser_au_sol(self._V)
                if suffixe == ".stl":
                    X.exporter_stl(V, self._F, chemin)
                else:
                    X.exporter_3mf(V, self._F, chemin, chemin.stem)
        except Exception as exc:
            D.avertir(self, "neoForge", T("enregistrement_impossible", err=exc))
            return
        self._statut(T("exporte", nom=chemin.name), "ok")

    def envoyer_a_neoslice(self):
        if self._projet is None or not self._pret_a_sortir():
            return
        nom = self._chemin.stem if self._chemin else "neoforge"
        message = P.piece_vers_message(nom, X.poser_au_sol(self._V), self._F)
        if P.envoyer(P.NOM_PONT, message) is not None:
            self._statut(T("envoi_ok"), "ok")
            return
        # neoSlice n'est pas ouvert : on l'ouvre et on réessaie sans bloquer.
        self._statut(T("envoi_lancement"))
        P.lancer_neoslice()
        self._essais_envoi = 0
        minuteur = QTimer(self)
        minuteur.setInterval(1000)

        def reessayer():
            self._essais_envoi += 1
            if P.envoyer(P.NOM_PONT, message, delai_ms=800) is not None:
                minuteur.stop()
                self._statut(T("envoi_ok"), "ok")
            elif self._essais_envoi > 90:
                minuteur.stop()
                self._statut(T("envoi_echec"), "erreur")
        minuteur.timeout.connect(reessayer)
        minuteur.start()
        self._minuteur_envoi = minuteur

    # ── Fermeture ───────────────────────────────────────────────────────────
    def closeEvent(self, event):
        if not self._confirmer_abandon():
            event.ignore()
            return
        # On ferme : plus aucun calcul ne doit repartir ni se terminer derrière
        # nous. Un calcul déjà en vol réécrivait la sauvegarde de secours APRÈS
        # son effacement, et « Reprendre votre pièce » revenait au lancement
        # suivant alors que la sortie avait été propre (retour d'Emmanuel).
        self._ferme = True
        self._auto.stop()
        nfg.auto_effacer()
        try:
            _T.unregister(self.refresh_theme)
            self._viewer.fermer()
        except Exception:
            pass
        event.accept()
