"""Fenêtre « glass » façon Apple Intelligence pour l'assistant IA (Pro).

Sans barre de titre, coins arrondis, flou natif du fond (acrylic Windows 11 /
vibrancy macOS à venir), teinte rose→orange→violet + halo, animation d'ouverture
depuis la sphère. Le contenu (chat) viendra ensuite ; ici = coquille visuelle.
"""
from __future__ import annotations
import sys
import math
import re

from PySide6.QtCore import (Qt, QRect, QRectF, QPoint, QPointF, QPropertyAnimation,
                            QEasingCurve, QParallelAnimationGroup, QTimer, QThread, Signal)
from PySide6.QtGui import (QPainter, QLinearGradient, QColor, QFont, QFontMetrics,
                           QGuiApplication)
from PySide6.QtWidgets import (QWidget, QLabel, QLineEdit, QVBoxLayout, QHBoxLayout,
                               QPushButton, QScrollArea, QFrame)


def _plain_text(text: str) -> str:
    """Retire la mise en forme Markdown pour un rendu propre dans la bulle (texte
    simple). Sûr en streaming (idempotent, marche sur du texte partiel)."""
    text = text.replace("**", "").replace("__", "")      # gras
    text = re.sub(r"`{1,3}", "", text)                    # code
    # Liens Markdown vers une URL -> on garde le libellé, on retire l'URL. Oen est
    # hors-ligne et un 7B fabrique parfois des URLs : ne jamais afficher de lien.
    text = re.sub(r"\[([^\]]+)\]\((?:https?://|www\.)[^)]*\)", r"\1", text)
    # URL brute : Oen est HORS-LIGNE et ne doit JAMAIS afficher d'adresse web
    # (un LLM en fabrique) -> on la retire, on garde le reste de la phrase.
    text = re.sub(r"\(?(?:https?://|www\.)\S+\)?", "", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)     # titres #
    text = re.sub(r"(?m)^(\s*)[\*\-]\s+", r"\1• ", text)  # puces -> •
    return text


# Marqueur de questions a choix cliquables : [[OPTIONS: a | b | c]]
_OPT_RE = re.compile(r"\[\[\s*OPTIONS?\s*:\s*(.+?)\]\]", re.IGNORECASE | re.DOTALL)


def _split_options(text: str):
    """Separe le texte du marqueur [[OPTIONS: a | b | c]]. Renvoie
    (texte_sans_marqueur, [options])."""
    m = _OPT_RE.search(text)
    if not m:
        return text, []
    clean = (text[:m.start()] + text[m.end():]).strip()
    opts = [o.strip() for o in m.group(1).split("|") if o.strip()]
    return clean, opts[:5]


# Formules creuses de fin de reponse (offres d'aide) : le 7B en ajoute malgre la
# consigne -> on les retire de facon garantie en post-traitement.
_FILLER_RE = re.compile(
    r"(?iu)^\s*(?:[-•*]\s*)?(?:"
    r"n['’]h[ée]sit\w*"                                   # n'hésite(z) pas
    r"|si (?:tu|vous) (?:as|avez|en as|en avez)"          # si tu as (des questions/besoin)
    r"|si (?:tu|vous) (?:rencontr|souhait|veu|voul)\w*"   # si tu rencontres/souhaites/veux
    r"|j['’]esp[èe]re que"                                # j'espère que ça aide
    r"|je (?:peux|reste|suis) (?:t['’]|vous |l[àa])"       # je peux/suis là / t'aider
    r"|dis[- ]moi si|fais[- ]moi savoir|tiens[- ]moi"     # dis-moi si / fais-moi savoir
    r"|envoie[- ]?(?:moi)?\b|n['’]?h[ée]site"             # envoie(-moi) une photo
    r"|pour (?:toute|plus|d['’]autres) (?:question|info|aide|d[ée]tail)"
    r").*$")


def _strip_filler(text: str) -> str:
    """Retire les formules de remplissage / offres d'aide en FIN de reponse, que ce
    soit une LIGNE entiere ou une PHRASE en fin de derniere ligne (le 7B ajoute
    souvent 'N'hesitez pas...' apres une phrase de contenu, sur la meme ligne)."""
    lines = text.rstrip().split("\n")
    # 1) Lignes entieres de filler (ou vides) en fin de reponse.
    while lines and (not lines[-1].strip() or _FILLER_RE.match(lines[-1])):
        lines.pop()
    # 2) Phrase(s) de filler en fin de la derniere ligne de contenu.
    if lines and lines[-1].strip():
        parts = re.split(r"(?<=[.!?…])\s+", lines[-1].rstrip())
        while len(parts) > 1 and _FILLER_RE.match(parts[-1].strip()):
            parts.pop()
        lines[-1] = " ".join(parts).rstrip()
    return "\n".join(lines).rstrip() or text.strip()


def _display_text(text: str) -> str:
    """Texte a afficher pendant le streaming : masque les marqueurs [[OPTIONS: …]]
    et [[ACTION: …]] meme partiels (pas encore fermes)."""
    low = text.lower()
    cut = len(text)
    for marker in ("[[option", "[[action"):
        i = low.find(marker)
        if i != -1:
            cut = min(cut, i)
    if cut < len(text):
        text = text[:cut].rstrip()
    return _plain_text(text)


_WELCOME = (
    "Bonjour, je suis Oen, l'assistant de neoSlice.\n\n"
    "Je peux t'aider sur :\n"
    "• Impression 3D : réglages, matériaux, défauts (warping, stringing, "
    "sous-extrusion), choix de profil.\n"
    "• Ta machine : entretien, calibration, dépannage (extrusion, adhérence, "
    "capteurs).\n"
    "• Ton atelier : stock de bobines, devis, coûts, rentabilité, commandes.\n\n"
    "Pose ta question, je suis là pour ça."
)


# ──────────────────────────────────────────────────────────────────────────────
# Flou natif du fond (Windows). macOS (NSVisualEffectView) : à câbler au build Mac.
# ──────────────────────────────────────────────────────────────────────────────
def _enable_windows_acrylic(hwnd: int, tint_abgr: int = 0x21100C14) -> bool:
    """Active l'acrylic (flou du fond) sur une fenêtre Windows 10 1803+/11.
    tint_abgr = AABBGGRR : teinte sombre légère pour la lisibilité."""
    try:
        import ctypes
        from ctypes import wintypes

        class ACCENTPOLICY(ctypes.Structure):
            _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                        ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]

        class WINCOMPATTRDATA(ctypes.Structure):
            _fields_ = [("Attribute", ctypes.c_int),
                        ("Data", ctypes.POINTER(ACCENTPOLICY)),
                        ("SizeOfData", ctypes.c_size_t)]

        accent = ACCENTPOLICY()
        accent.AccentState = 4          # ACCENT_ENABLE_ACRYLICBLURBEHIND
        accent.AccentFlags = 0
        accent.GradientColor = tint_abgr
        data = WINCOMPATTRDATA()
        data.Attribute = 19             # WCA_ACCENT_POLICY
        data.Data = ctypes.pointer(accent)
        data.SizeOfData = ctypes.sizeof(accent)
        ctypes.windll.user32.SetWindowCompositionAttribute(
            wintypes.HWND(int(hwnd)), ctypes.byref(data))
        return True
    except Exception:
        return False


def _round_windows_corners(hwnd: int, radius_pref: int = 2):
    """Coins arrondis natifs Win11 (DWMWA_WINDOW_CORNER_PREFERENCE=33, ROUND=2)."""
    try:
        import ctypes
        val = ctypes.c_int(radius_pref)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            int(hwnd), 33, ctypes.byref(val), ctypes.sizeof(val))
    except Exception:
        pass


def _apply_win11_glass(hwnd: int) -> bool:
    """Windows 11 : backdrop système (flou dessiné DANS le cadre arrondi → coins
    parfaitement nets, contrairement à l'acrylic ACCENT rectangulaire). Renvoie
    False si indisponible (Win10) → l'appelant fait un repli sur l'acrylic ACCENT."""
    try:
        import ctypes
        dwm = ctypes.windll.dwmapi
        # DWMWA_SYSTEMBACKDROP_TYPE = 38, DWMSBT_TRANSIENTWINDOW = 3 (acrylic popups)
        bt = ctypes.c_int(3)
        if dwm.DwmSetWindowAttribute(int(hwnd), 38, ctypes.byref(bt), 4) != 0:
            return False   # pas Win11 → repli

        class MARGINS(ctypes.Structure):
            _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int),
                        ("t", ctypes.c_int), ("b", ctypes.c_int)]
        # Étend le cadre (backdrop) à toute la fenêtre
        dwm.DwmExtendFrameIntoClientArea(int(hwnd), ctypes.byref(MARGINS(-1, -1, -1, -1)))
        # Coins arrondis (DWMWCP_ROUND = 2) → clippe TOUTE la fenêtre proprement
        dwm.DwmSetWindowAttribute(int(hwnd), 33, ctypes.byref(ctypes.c_int(2)), 4)
        return True
    except Exception:
        return False


class _ChatWorker(QThread):
    """Execute l'inference du modele local dans un thread (UI non bloquee).
    Emet chaque morceau au fur et a mesure : `token` = reponse, `thinking` =
    raisonnement (uniquement si le mode Reflexion est actif)."""
    token = Signal(str)
    thinking = Signal(str)
    done = Signal()
    failed = Signal(str)

    def __init__(self, history: list, think: bool = False):
        super().__init__()
        self._history = history
        self._think = think

    def run(self):
        try:
            from core.assistant.engine import AssistantEngine
            for kind, txt in AssistantEngine.instance().stream(self._history, think=self._think):
                if kind == "thinking":
                    self.thinking.emit(txt)
                else:
                    self.token.emit(txt)
            self.done.emit()
        except Exception as e:
            self.failed.emit(str(e))


class _TypingDots(QWidget):
    """Trois points animés facon iMessage (« en train d'écrire »)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(44, 16)
        self._t = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(55)

    def _tick(self):
        self._t += 0.16
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.NoPen)
        n, gap, rad = 3, 10, 3.0
        x0 = (self.width() - (n - 1) * gap) / 2.0
        cy = self.height() / 2.0
        for i in range(n):
            a = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(self._t - i * 0.9))
            p.setBrush(QColor(255, 255, 255, int(a * 225)))
            p.drawEllipse(QPointF(x0 + i * gap, cy), rad, rad)


class GlassPanel(QWidget):
    """Coquille visuelle de la fenêtre assistant (glass translucide, sans barre)."""

    busy_changed = Signal(bool)   # True quand l'IA « réfléchit / rédige »
    _RADIUS = 11

    def __init__(self, parent=None, w=430, h=560):
        super().__init__(parent)
        self._W, self._H = w, h
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool
                            | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)   # pas de pinceau système (anti flash blanc)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.resize(w, h)
        self._native_done = False
        self._drag_off = None
        self._anim = None
        self._build_content()

    # ── Contenu (placeholder pour l'instant) ─────────────────────────────────
    def _build_content(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        # En-tête
        header = QHBoxLayout(); header.setContentsMargins(4, 0, 0, 0)
        title = QLabel("Oen · Assistant neoSlice")
        title.setFont(QFont("Segoe UI", 12, QFont.DemiBold))
        title.setStyleSheet("color: rgba(255,255,255,235); background: transparent;")
        header.addWidget(title)
        header.addStretch()
        close = QPushButton("✕")
        close.setCursor(Qt.PointingHandCursor)
        close.setFixedSize(26, 26)
        close.setStyleSheet(
            "QPushButton { color: rgba(255,255,255,180); background: rgba(255,255,255,25); "
            "border: none; border-radius: 13px; font-size: 12px; }"
            "QPushButton:hover { background: rgba(255,120,150,160); color: #fff; }")
        close.clicked.connect(self.close_anim)
        header.addWidget(close)
        lay.addLayout(header)

        # Zone de conversation (scrollable)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 6px; background: transparent; margin: 2px; }"
            "QScrollBar::handle:vertical { background: rgba(255,255,255,55); border-radius: 3px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }")
        host = QWidget(); host.setStyleSheet("background: transparent;")
        self._msgs_lay = QVBoxLayout(host)
        self._msgs_lay.setContentsMargins(2, 2, 2, 2)
        self._msgs_lay.setSpacing(10)
        self._msgs_lay.addStretch()
        self._scroll.setWidget(host)
        lay.addWidget(self._scroll, 1)

        # Champ de saisie
        self._input = QLineEdit()
        self._input.setPlaceholderText("Écrire un message…")
        self._input.setFont(QFont("Segoe UI", 10))
        self._input.setFixedHeight(40)
        self._input.setStyleSheet(
            "QLineEdit { background: rgba(255,255,255,28); color: #fff; "
            "border: 1px solid rgba(255,255,255,45); border-radius: 20px; "
            "padding: 0 16px; }"
            "QLineEdit:focus { border-color: rgba(255,180,220,150); }")
        self._input.returnPressed.connect(self._on_send)

        # Plus de bouton « Réflexion » : la reflexion (Qwen3 thinking) s'active
        # AUTOMATIQUEMENT sur les questions difficiles (voir engine.should_auto_think),
        # instantanee sinon. UI epuree, Oen decide seul quand raisonner.
        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(6)
        input_row.addWidget(self._input, 1)
        lay.addLayout(input_row)

        self._greeted = False
        self._typing_wrap = None
        self._history = []          # [{role, content}] de la conversation
        self._worker = None
        self._stream_bubble = None
        self._stream_text = ""
        self._option_wrap = None      # bloc de boutons de reponse cliquables


    def _on_thinking(self, tok: str):
        """Affiche le raisonnement (mode Réflexion) dans une bulle grisee distincte,
        au-dessus de la reponse."""
        if getattr(self, "_think_bubble", None) is None:
            self._remove_typing()
            self._think_text = ""
            self._think_bubble = self._add_message("", "assistant")
            self._think_bubble.setFont(QFont("Segoe UI", 9))
            self._think_bubble.setStyleSheet(
                "color: rgba(255,255,255,150); background: rgba(255,255,255,14); "
                "border: 1px solid rgba(255,255,255,26); border-radius: 12px; "
                "padding: 8px 12px; font-style: italic;")
        self._think_text += tok
        self._think_bubble.setText("Réflexion — " + self._think_text)
        self._scroll_bottom()

    def _add_message(self, text: str, role: str = "assistant"):
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setFont(QFont("Segoe UI", 10))
        maxw = int(self._W * 0.80)
        bubble.setMaximumWidth(maxw)
        bubble.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # Ajuste la largeur de la bulle a son contenu : sans ca, une bulle avec
        # retour a la ligne alignee a droite se reduit a la largeur du mot le plus
        # long (colonne etroite). On calcule la largeur reellement utilisee par le
        # texte (jusqu'a maxw) et on la fixe. Ignore pour la bulle de streaming
        # (texte vide au depart, grandit ensuite via setText).
        if text:
            fm = QFontMetrics(bubble.font())
            _inner = fm.boundingRect(0, 0, maxw - 30, 100000,
                                     int(Qt.TextFlag.TextWordWrap), text)
            bubble.setFixedWidth(min(maxw, _inner.width() + 32))
        if role == "assistant":
            bubble.setStyleSheet(
                "color: rgba(255,255,255,238); background: rgba(255,255,255,26); "
                "border: 1px solid rgba(255,255,255,30); border-radius: 14px; padding: 9px 13px;")
        else:
            bubble.setStyleSheet(
                "color: #fff; background: rgba(255,140,175,70); "
                "border: 1px solid rgba(255,180,210,90); border-radius: 14px; padding: 9px 13px;")
        row = QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0)
        if role == "assistant":
            row.addWidget(bubble); row.addStretch()
        else:
            row.addStretch(); row.addWidget(bubble)
        wrap = QWidget(); wrap.setLayout(row); wrap.setStyleSheet("background: transparent;")
        self._msgs_lay.insertWidget(self._msgs_lay.count() - 1, wrap)
        QTimer.singleShot(20, self._scroll_bottom)
        return bubble

    def _scroll_bottom(self):
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── Indicateur « en train d'écrire » (bulle + 3 points animés) ───────────
    def _show_typing(self):
        if self._typing_wrap is not None:
            return
        holder = QFrame()
        holder.setStyleSheet(
            "background: rgba(255,255,255,26); border: 1px solid rgba(255,255,255,30); "
            "border-radius: 14px;")
        hl = QHBoxLayout(holder); hl.setContentsMargins(14, 9, 14, 9)
        hl.addWidget(_TypingDots())
        row = QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(holder); row.addStretch()
        wrap = QWidget(); wrap.setLayout(row); wrap.setStyleSheet("background: transparent;")
        self._msgs_lay.insertWidget(self._msgs_lay.count() - 1, wrap)
        self._typing_wrap = wrap
        QTimer.singleShot(20, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()))

    def _remove_typing(self):
        if self._typing_wrap is not None:
            self._typing_wrap.setParent(None)
            self._typing_wrap.deleteLater()
            self._typing_wrap = None

    # ── Accueil au premier affichage (typing puis message) ───────────────────
    def _greet_if_needed(self):
        if self._greeted:
            return
        self._greeted = True
        self._show_typing()
        self.busy_changed.emit(True)
        QTimer.singleShot(1300, self._deliver_welcome)

    def _deliver_welcome(self):
        self._remove_typing()
        self._add_message(_WELCOME, "assistant")
        self.busy_changed.emit(False)

    def _on_send(self):
        t = self._input.text().strip()
        if not t or (self._worker is not None and self._worker.isRunning()):
            return
        self._input.clear()
        self._clear_options()          # retire d'eventuels boutons de reponse restants
        self._add_message(t, "user")
        self._history.append({"role": "user", "content": t})

        # Demande de changer de langue -> Oen reste en francais (le modele obeit mal a
        # cette regle) : reponse canned deterministe, sans appeler le modele.
        try:
            from core.assistant.engine import is_language_switch_request
            if is_language_switch_request(t):
                _fr = ("Je réponds toujours en français 🙂 — mais je suis là pour tout ce "
                       "qui touche l'impression 3D et ton atelier. Que veux-tu savoir ?")
                self._add_message(_fr, "assistant")
                self._history.append({"role": "assistant", "content": _fr})
                return
        except Exception:
            pass

        from core.assistant.engine import AssistantEngine
        if not AssistantEngine.available():
            self._show_typing()
            self.busy_changed.emit(True)
            QTimer.singleShot(900, self._reply_not_installed)
            return

        # Les 3 points restent affiches pendant l'inference (temps reel du modele).
        self._show_typing()
        self.busy_changed.emit(True)
        self._stream_text = ""
        self._stream_bubble = None
        self._think_bubble = None
        self._think_text = ""
        # Reflexion AUTO : active sur les questions difficiles (diagnostics/how-to),
        # OFF sur les commandes/lectures (reponse instantanee). Oen decide seul.
        try:
            from core.assistant.engine import should_auto_think
            think = should_auto_think(t)
        except Exception:
            think = False
        self._worker = _ChatWorker(list(self._history), think=think)
        self._worker.token.connect(self._on_token)
        self._worker.thinking.connect(self._on_thinking)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _reply_not_installed(self):
        self._remove_typing()
        self.busy_changed.emit(False)
        self._add_message(
            "L'assistant IA n'est pas encore installé sur cette machine. "
            "Tu pourras l'installer depuis les réglages (version Pro).",
            "assistant")

    def _on_token(self, tok: str):
        if self._stream_bubble is None:
            self._remove_typing()
            self._stream_bubble = self._add_message("", "assistant")
        self._stream_text += tok
        # Masque le marqueur d'options tant que la reponse arrive.
        self._stream_bubble.setText(_display_text(self._stream_text))
        self._scroll_bottom()

    def _on_done(self):
        clean, opts = _split_options(self._stream_text)
        # Actions atelier ([[ACTION: …]]) : EXÉCUTE réellement contre le store et
        # retire les marqueurs du texte affiché. Les confirmations viennent du store.
        try:
            from core.assistant import actions
            _utxt = (self._history[-1]["content"]
                     if self._history and self._history[-1].get("role") == "user" else "")
            clean, confirmations = actions.parse_and_execute(clean, _utxt)
        except Exception:
            confirmations = []
        clean = _strip_filler(clean)     # retire les formules creuses de fin
        if clean.strip():
            if self._stream_bubble is not None:
                self._stream_bubble.setText(_plain_text(clean))
            if opts:
                self._add_option_chips(opts)      # boutons de reponse cliquables
        else:
            # Rien a afficher (reponse = uniquement un marqueur [[ACTION/OPTIONS]]) :
            # retirer la bulle de streaming VIDE, sinon elle reste affichee vide.
            self._remove_typing()
            if self._stream_bubble is not None:
                _wrap = self._stream_bubble.parentWidget()
                if _wrap is not None:
                    _wrap.setParent(None)
                    _wrap.deleteLater()
        # Oen est en LECTURE SEULE (voir actions.WRITE_ENABLED) : il n'exécute aucune
        # action, donc `confirmations` est toujours vide. On garde la boucle par sûreté
        # (compat) mais plus d'alerte « rien n'a été enregistré » — Oen guide vers l'onglet.
        for _c in confirmations:
            self._add_message(_c, "assistant")
        # HISTORIQUE : on enregistre le tour d'Oen AVEC les confirmations d'action.
        # CRUCIAL : sans les confirmations, un tour "marqueur seul" laissait un
        # historique VIDE cote assistant -> Oen "oubliait" ce qu'il venait de faire
        # et REJOUAIT toutes les actions au tour suivant. Le resultat reel de l'action
        # est donc trace comme reponse assistant.
        _hist = "\n".join(([clean] if clean.strip() else []) + confirmations).strip()
        if _hist:
            self._history.append({"role": "assistant", "content": _hist})
        self._stream_bubble = None
        self._think_bubble = None
        self.busy_changed.emit(False)

    # ── Réponses cliquables (questions à choix) ──────────────────────────────
    def _clear_options(self):
        if getattr(self, "_option_wrap", None) is not None:
            self._option_wrap.setParent(None)
            self._option_wrap.deleteLater()
            self._option_wrap = None

    def _add_option_chips(self, options: list):
        holder = QWidget(); holder.setStyleSheet("background: transparent;")
        vl = QVBoxLayout(holder); vl.setContentsMargins(0, 2, 0, 0); vl.setSpacing(6)
        for opt in options:
            b = QPushButton(opt)
            b.setCursor(Qt.PointingHandCursor)
            b.setFont(QFont("Segoe UI", 10))
            b.setStyleSheet(
                "QPushButton { text-align: left; color: #fff; background: rgba(255,140,175,55); "
                "border: 1px solid rgba(255,180,210,110); border-radius: 13px; padding: 8px 14px; }"
                "QPushButton:hover { background: rgba(255,140,175,120); }")
            b.clicked.connect(lambda _c=False, o=opt: self._on_option_clicked(o))
            vl.addWidget(b)
        row = QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(holder); row.addStretch()
        wrap = QWidget(); wrap.setLayout(row); wrap.setStyleSheet("background: transparent;")
        self._msgs_lay.insertWidget(self._msgs_lay.count() - 1, wrap)
        self._option_wrap = wrap
        QTimer.singleShot(20, self._scroll_bottom)

    def _on_option_clicked(self, option: str):
        if self._worker is not None and self._worker.isRunning():
            return
        self._input.setText(option)
        self._on_send()          # _on_send retire les boutons puis envoie

    def _on_failed(self, err: str):
        self._remove_typing()
        self.busy_changed.emit(False)
        self._stream_bubble = None
        self._add_message("Désolé, une erreur est survenue pendant la réponse.", "assistant")
        from loguru import logger
        logger.warning(f"[Assistant] inference failed: {err}")

    # ── Effets natifs (flou + coins arrondis) ────────────────────────────────
    def _ensure_native(self):
        """Applique le flou/transparence natifs sur le HWND. Appelé AVANT le premier
        show() : winId() crée la fenêtre native même cachée, donc la toute première
        image est déjà translucide → aucun flash blanc à l'ouverture."""
        if self._native_done:
            return
        self._native_done = True
        hwnd = int(self.winId())
        if sys.platform == "win32":
            # Win11 : backdrop système (coins nets). Sinon repli sur l'acrylic ACCENT.
            if not _apply_win11_glass(hwnd):
                _enable_windows_acrylic(hwnd)
                _round_windows_corners(hwnd)
        # macOS : vibrancy NSVisualEffectView → à câbler au build Mac.

    def showEvent(self, event):
        super().showEvent(event)
        self._ensure_native()

    # ── Rendu glass (teinte + halo + bord) par-dessus le flou ────────────────
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Remplissage PLEIN jusqu'aux bords : la teinte couvre tout le rectangle de
        # l'acrylic, donc aucun coin gris. Windows arrondit ensuite la fenêtre
        # entière (DWMWA corner preference), coins propres.
        full = QRectF(self.rect())

        # Base légèrement teintée : plus faible qu'avant → plus transparent, on voit
        # davantage le flou derrière (effet verre).
        p.fillRect(full, QColor(18, 14, 24, 96))

        # Teinte glass chaude (allégée pour rester translucide)
        g = QLinearGradient(full.topLeft(), full.bottomRight())
        g.setColorAt(0.0, QColor(249, 115, 22, 34))    # orange
        g.setColorAt(0.5, QColor(255, 107, 157, 30))   # rose
        g.setColorAt(1.0, QColor(124, 58, 237, 40))    # violet
        p.fillRect(full, g)

        # Halo lumineux en haut
        hg = QLinearGradient(full.topLeft(), QPointF(full.left(), full.top() + 120))
        hg.setColorAt(0.0, QColor(255, 255, 255, 46))
        hg.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillRect(full, hg)

        # Lueur rosée diffuse en bas
        bg = QLinearGradient(QPointF(full.left(), full.bottom() - 160), full.bottomLeft())
        bg.setColorAt(0.0, QColor(255, 120, 190, 0))
        bg.setColorAt(1.0, QColor(255, 120, 190, 34))
        p.fillRect(full, bg)


    # ── Déplacement (pas de barre → on drague la fenêtre) ────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_off = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_off is not None and (e.buttons() & Qt.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag_off)
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag_off = None

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close_anim()
        else:
            super().keyPressEvent(e)

    # ── Animations d'ouverture / fermeture ───────────────────────────────────
    def _final_rect(self, anchor: QPoint | None) -> QRect:
        scr = QGuiApplication.primaryScreen().availableGeometry()
        w, h = self._W, self._H
        if anchor is None:
            x = scr.x() + (scr.width() - w) // 2
            y = scr.y() + (scr.height() - h) // 2
        else:
            # Juste au-dessus / à droite de la sphère, borné à l'écran
            x = min(max(anchor.x(), scr.left() + 8), scr.right() - w - 8)
            y = min(max(anchor.y() - h - 12, scr.top() + 8), scr.bottom() - h - 8)
        return QRect(x, y, w, h)

    def open_from(self, anchor: QPoint | None = None):
        """Ouverture SANS flash blanc : la fenêtre est d'abord invisible (opacité 0)
        le temps qu'elle se peigne en translucide et que le flou DWM s'applique, puis
        elle apparaît en fondu + léger agrandissement. Aucune frame blanche ne peut
        donc être vue. La garantie opacité=1 à la fin évite tout gel."""
        end = self._final_rect(anchor)
        start = QRect(end)
        start.setWidth(int(end.width() * 0.93))
        start.setHeight(int(end.height() * 0.93))
        start.moveCenter(end.center())
        self.setWindowOpacity(0.0)          # invisible tant que non peint
        self.setGeometry(start)
        self._ensure_native()               # flou/transparence natifs avant show
        self.show()
        self.raise_()
        self.activateWindow()
        # On laisse quelques ms la 1re peinture translucide se faire (fenêtre invisible),
        # PUIS on révèle → l'utilisateur ne voit jamais de blanc.
        QTimer.singleShot(24, lambda: self._reveal(start, end))
        self._greet_if_needed()

    def _reveal(self, start: QRect, end: QRect):
        ga = QPropertyAnimation(self, b"geometry", self)
        ga.setDuration(190); ga.setStartValue(start); ga.setEndValue(end)
        ga.setEasingCurve(QEasingCurve.OutCubic)
        oa = QPropertyAnimation(self, b"windowOpacity", self)
        oa.setDuration(190); oa.setStartValue(0.0); oa.setEndValue(1.0)
        oa.setEasingCurve(QEasingCurve.OutCubic)
        grp = QParallelAnimationGroup(self)
        grp.addAnimation(ga); grp.addAnimation(oa)
        grp.finished.connect(lambda: self.setWindowOpacity(1.0))  # garantie anti-gel
        grp.start()
        self._anim = grp

    def close_anim(self):
        # Fermeture simple et sûre (pas d'animation d'opacité fragile).
        self.hide()
