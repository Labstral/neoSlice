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
)

_BODY_COLOR = "#8AAABF"


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


_STEPS: list[_Step] = [
    _Step(
        None,
        "Bienvenue dans neoSlice",
        "neoSlice analyse votre fichier STL, OBJ ou 3MF et génère automatiquement "
        "les paramètres d'impression optimaux pour vos imprimantes Bambu Lab.\n\n"
        "Ce guide vous présente les 4 étapes du workflow.\n"
        "Cliquez sur <b>Suivant</b> pour commencer.",
    ),
    _Step(
        "config",
        "① Configuration — Imprimante & Filament",
        "Sélectionnez votre <b>imprimante cible</b> et votre <b>diamètre de buse</b>, "
        "puis cliquez sur <b>VALIDER →</b>.\n"
        "Faites de même pour votre <b>filament</b>.\n\n"
        "neoSlice adapte automatiquement les paramètres selon le matériau choisi.",
        pad=12,
    ),
    _Step(
        "drop",
        "② Import STL / OBJ / 3MF",
        "Glissez votre <b>fichier STL, OBJ ou 3MF</b> dans cette zone, "
        "ou cliquez pour ouvrir l'explorateur de fichiers.\n\n"
        "neoSlice analyse automatiquement la géométrie :\n"
        "<b>surplombs · stabilité · zones fragiles</b>\n"
        "<b>volume & dimensions · orientation optimale</b>\n\n"
        "Une suggestion de rotation est affichée si elle améliore "
        "significativement l'imprimabilité.",
        pad=12,
    ),
    _Step(
        "intent",
        "③ Instruction Mission",
        "Ouvrez chaque accordéon pour choisir vos critères :\n"
        "<b>Qualité · Résistance · Vitesse · Adhérence · Usage · Mode</b>\n\n"
        "Le groupe <b>Mode</b> permet d'activer :\n"
        "— <b>Silencieux</b> : vitesses –40 % pour moins de bruit\n"
        "— <b>Multicolore AMS</b> : active la <b>prime tower</b> (tour de purge "
        "qui stabilise les changements de couleur) et le <b>flush</b> "
        "(purge automatique de la buse entre chaque filament)\n\n"
        "Sauvegardez vos combinaisons favorites en présets, "
        "puis cliquez sur <b>GÉNÉRER CONFIGURATION →</b>.",
        pad=12,
    ),
    _Step(
        "statusbar",
        "④ Export vers Bambu Studio",
        "Une fois la configuration générée, le <b>bouton d'export</b> s'active.\n\n"
        "neoSlice génère un fichier <b>.3MF</b> avec tous les paramètres "
        "optimisés selon votre matériau et la géométrie de la pièce.\n\n"
        "Des <b>alertes matériau</b> peuvent apparaître dans le panneau d'analyse : "
        "risque de warping, séchage recommandé, incompatibilité AMS…",
        pad=6,
    ),
    _Step(
        "topbar",
        "⑤ Barre de titre",
        "Trois raccourcis sont disponibles à tout moment :"
        "<br><br>"
        "<table cellspacing='0' cellpadding='0' width='100%'>"
        "<tr>"
        "<td width='28' valign='top' style='padding-top:1px;'>"
        "<span style='font-family:\"Segoe MDL2 Assets\";font-size:11pt;color:#E8F4FF;'>&#xE8BD;</span>"
        "</td>"
        "<td valign='top'>Signaler un bug ou partager votre expérience."
        " Ouvre un formulaire en ligne&nbsp;; vos retours sont lus personnellement.</td>"
        "</tr>"
        "<tr><td colspan='2' height='10'></td></tr>"
        "<tr>"
        "<td width='28' valign='top' style='padding-top:1px;'>"
        "<b style='color:#E8F4FF;font-size:11pt;'>?</b>"
        "</td>"
        "<td valign='top'>Relancer ce tutoriel.</td>"
        "</tr>"
        "<tr><td colspan='2' height='10'></td></tr>"
        "<tr>"
        "<td width='28' valign='top' style='padding-top:2px;'>&#x2615;</td>"
        "<td valign='top'>Soutenir le développement du logiciel via un don volontaire.</td>"
        "</tr>"
        "</table>",
        pad=12,
    ),
]

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

    def __init__(self, parent: QWidget, targets: dict[str, QWidget]):
        # FramelessWindowHint : pas de barre de titre
        # WindowStaysOnTopHint : toujours devant la fenêtre principale
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        # WA_TranslucentBackground : les pixels transparents laissent voir la fenêtre parent
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)

        self._targets = targets
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
        if self._idx < len(_STEPS) - 1:
            self._go_to(self._idx + 1)
        else:
            self._finish()

    def _finish(self):
        _mark_done()
        self.finished.emit()
        self.close()

    # ── Spotlight ────────────────────────────────────────────────────────────

    def _spotlight(self) -> QRect | None:
        step = _STEPS[self._idx]
        if step.target is None:
            return None
        w = self._targets.get(step.target)
        if w is None or not w.isVisible():
            return None
        # mapTo(parentWidget()) donne la position dans la fenêtre principale,
        # qui coïncide avec la position dans ce dialog (même origine).
        tl = w.mapTo(self.parent(), QPoint(0, 0))
        return QRect(tl, w.size()).adjusted(-step.pad, -step.pad, step.pad, step.pad)

    # ── Layout ───────────────────────────────────────────────────────────────

    def _body_html(self) -> str:
        icon_color = _T.palette()["TEXT_SECONDARY"]
        return (_STEPS[self._idx].body
                .replace("\n", "<br>")
                .replace("#E8F4FF", icon_color))

    def _measure_card_height(self) -> int:
        text_w = _CARD_W - 2 * _PAD_H
        h = _PAD_V + 18 + 14  # top pad + dots row + spacing

        td = QTextDocument()
        td.setDefaultFont(QFont("Segoe UI", 13, QFont.Bold))
        td.setPlainText(_STEPS[self._idx].title)
        td.setTextWidth(text_w)
        h += int(td.size().height()) + 12 + 1 + 12  # title + sep

        bd = QTextDocument()
        bd.setDefaultFont(QFont("Segoe UI", 9))
        bd.setHtml(
            f"<body style='font-family:Segoe UI;font-size:9pt;color:{_BODY_COLOR};'>"
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
        dim  = QColor(4, 8, 16, 215)
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

            glow = QColor(ACCENT)
            glow.setAlpha(40)
            painter.setPen(QPen(glow, 8))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(spot), 6, 6)
            painter.setPen(QPen(QColor(ACCENT), 2))
            painter.drawRoundedRect(QRectF(spot), 6, 6)

    def _paint_card(self, painter: QPainter):
        idx   = self._idx
        step  = _STEPS[idx]
        total = len(_STEPS)
        cr    = QRectF(self._card_rect)
        cx    = float(self._card_rect.x())
        cy    = float(self._card_rect.y())
        tw    = float(_CARD_W - 2 * _PAD_H)

        # Fond de carte
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(10, 20, 36))
        painter.drawRoundedRect(cr, 8.0, 8.0)

        # Bordure
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(ACCENT), 1))
        painter.drawRoundedRect(cr.adjusted(0, 0, -1, -1), 8.0, 8.0)

        # Barre gauche accent
        painter.setBrush(QColor(ACCENT))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(cx, cy + 8, 3, cr.height() - 16), 2.0, 2.0)

        y = cy + _PAD_V

        # ── Points de progression ──
        dot_font = QFont("Segoe UI", 9)
        fm = QFontMetrics(dot_font)
        painter.setFont(dot_font)
        dx = cx + _PAD_H
        for i in range(total):
            ch_str = "●" if i <= idx else "○"
            color  = TELE_GREEN if i < idx else (ACCENT_BRIGHT if i == idx else "#1A3550")
            painter.setPen(QColor(color))
            painter.drawText(QPointF(dx, y + fm.ascent()), ch_str)
            dx += fm.horizontalAdvance(ch_str) + 8

        painter.setPen(QColor(TEXT_SECONDARY))
        painter.setFont(QFont(FONT_MONO, 7))
        painter.drawText(QRectF(cx + _PAD_H, y, tw, float(fm.height())),
                         Qt.AlignRight | Qt.AlignVCenter,
                         f"{idx + 1} / {total}")
        y += 18 + 14

        # ── Titre ──
        td = QTextDocument()
        td.setDefaultFont(QFont("Segoe UI", 13, QFont.Bold))
        td.setDefaultStyleSheet(f"body {{ color: {TEXT_PRIMARY}; }}")
        td.setPlainText(step.title)
        td.setTextWidth(tw)
        painter.save()
        painter.translate(cx + _PAD_H, y)
        td.drawContents(painter)
        painter.restore()
        y += td.size().height() + 12

        # ── Séparateur ──
        painter.setPen(QPen(QColor(30, 60, 90), 1))
        painter.drawLine(QPointF(cx + _PAD_H, y), QPointF(cx + _CARD_W - _PAD_H, y))
        y += 1 + 12

        # ── Corps ──
        bd = QTextDocument()
        bd.setDefaultFont(QFont("Segoe UI", 9))
        _bold_color = _tp['TELE_GREEN'] if not _T.is_dark() else _tp['ACCENT_BRIGHT']
        bd.setDefaultStyleSheet(
            f"body {{ color:{_BODY_COLOR}; }} b {{ color:{_bold_color}; font-weight:bold; }}"
        )
        bd.setHtml(
            f"<body style='font-family:Segoe UI;font-size:9pt;color:{_BODY_COLOR};'>"
            f"{self._body_html()}</body>"
        )
        bd.setTextWidth(tw)
        painter.save()
        painter.translate(cx + _PAD_H, y)
        bd.drawContents(painter)
        painter.restore()

        # ── Boutons ──
        self._paint_btn(painter, self._btn_skip, "Passer le guide",
                        "secondary", self._hovered == _HOVER_SKIP, idx < total - 1)
        self._paint_btn(painter, self._btn_prev, "← Précédent",
                        "outline", self._hovered == _HOVER_PREV, idx > 0)
        self._paint_btn(painter, self._btn_next,
                        "Terminer  ✓" if idx == total - 1 else "Suivant →",
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
            p.setFont(QFont("Segoe UI", 9, QFont.Bold))
        elif variant == "outline":
            _ac = QColor(_accent)
            _ac.setAlpha(40)
            p.setBrush(_ac if hovered else Qt.NoBrush)
            p.drawRoundedRect(rf, 4.0, 4.0)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(_accent), 1))
            p.drawRoundedRect(rf.adjusted(.5, .5, -.5, -.5), 4.0, 4.0)
            p.setPen(QColor(_accent))
            p.setFont(QFont("Segoe UI", 8, QFont.Bold))
        else:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(_tp["TEXT_SECONDARY"] if hovered else _tp["INACTIVE"]), 1))
            p.drawRoundedRect(rf.adjusted(.5, .5, -.5, -.5), 4.0, 4.0)
            p.setPen(QColor(_tp["TEXT_PRIMARY"] if hovered else _tp["TEXT_SECONDARY"]))
            p.setFont(QFont("Segoe UI", 8))

        p.drawText(rf, Qt.AlignCenter, text)

    # ── Souris ───────────────────────────────────────────────────────────────

    def mouseMoveEvent(self, event):
        pos   = event.pos()
        total = len(_STEPS)
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
            total = len(_STEPS)
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
