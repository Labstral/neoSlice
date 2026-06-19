"""Fenêtre de déblocage neoSlice Pro.

Affichée quand l'utilisateur a épuisé ses diagnostics photo gratuits. Propose
l'achat (paiement unique via Gumroad, ouvert dans le navigateur) et un
champ pour coller/activer une clé de licence déjà achetée.

Retourne QDialog.Accepted si l'activation a réussi pendant la session.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QPoint, QUrl, QTimer
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from ui.styles.theme import MANAGER as _T, FONT_MAIN
from ui.components.pro_badge import ProBadge
from ui.components.confetti import ConfettiOverlay
from core import licensing
from core.i18n import _


def _sep() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFixedHeight(1)
    return line


class ProThankYouDialog(QDialog):
    """Fenêtre de remerciement affichée après l'activation réussie d'une clé."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(440)
        self._setup_ui()
        self._apply_theme()
        _T.register(self._apply_theme)
        self._confetti = ConfettiOverlay(self)

    def closeEvent(self, event):
        _T.unregister(self._apply_theme)
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        scr = self.parent().screen() if self.parent() else self.screen()
        if scr is not None:
            geo = scr.availableGeometry()
            self.move(geo.center().x() - self.width() // 2,
                      geo.center().y() - self.height() // 2)
        # Confettis : court délai pour que la fenêtre soit affichée avant le canon
        QTimer.singleShot(140, self._confetti.burst)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._card = QWidget()
        self._card.setObjectName("thankyou_card")
        lay = QVBoxLayout(self._card)
        lay.setContentsMargins(30, 26, 30, 26)
        lay.setSpacing(0)
        root.addWidget(self._card)

        self._icon_lbl = QLabel("🎉")
        self._icon_lbl.setFont(QFont(FONT_MAIN, 34))
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._icon_lbl)
        lay.addSpacing(10)

        # Ligne titre : neoSlice [PRO] activé
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.addStretch()
        self._title_lbl = QLabel("neoSlice")
        self._title_lbl.setFont(QFont(FONT_MAIN, 15, QFont.Bold))
        title_row.addWidget(self._title_lbl)
        self._title_pro = ProBadge("PRO", point_size=15, letter_spacing=2.0)
        title_row.addWidget(self._title_pro)
        self._title_end = QLabel(_("pro.thanks_title_end"))
        self._title_end.setFont(QFont(FONT_MAIN, 15, QFont.Bold))
        title_row.addWidget(self._title_end)
        title_row.addStretch()
        lay.addLayout(title_row)
        lay.addSpacing(8)

        self._subtitle_lbl = QLabel(_("pro.thanks_subtitle"))
        self._subtitle_lbl.setFont(QFont(FONT_MAIN, 8))
        self._subtitle_lbl.setAlignment(Qt.AlignCenter)
        self._subtitle_lbl.setWordWrap(True)
        lay.addWidget(self._subtitle_lbl)
        lay.addSpacing(16)

        self._benefit_lbls = []
        benefits = [
            _("pro.benefit_unlimited"),
            _("pro.benefit_corrections"),
            _("pro.benefit_lifetime"),
            _("pro.benefit_support"),
        ]
        for text in benefits:
            row = QHBoxLayout()
            row.setSpacing(10)
            check = QLabel("✓")
            check.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
            check.setFixedWidth(16)
            txt = QLabel(text)
            txt.setFont(QFont(FONT_MAIN, 8))
            txt.setWordWrap(True)
            row.addWidget(check)
            row.addWidget(txt, 1)
            wrap = QWidget()
            wrap.setStyleSheet("background: transparent;")
            wrap.setLayout(row)
            lay.addWidget(wrap)
            lay.addSpacing(4)
            self._benefit_lbls.append((check, txt))

        lay.addSpacing(14)
        self._ok_btn = QPushButton(_("pro.thanks_btn"))
        self._ok_btn.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._ok_btn.setFixedHeight(36)
        self._ok_btn.setCursor(Qt.PointingHandCursor)
        self._ok_btn.clicked.connect(self.accept)
        lay.addWidget(self._ok_btn)

    def _apply_theme(self):
        pal = _T.palette()
        self._card.setStyleSheet(f"""
            QWidget#thankyou_card {{
                background: {pal['BG_PANEL']};
                border: 1px solid {pal['ACCENT']};
                border-radius: 8px;
            }}
        """)
        self._icon_lbl.setStyleSheet("background: transparent;")
        for w in (self._title_lbl, self._title_end):
            w.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        self._subtitle_lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        for check, txt in self._benefit_lbls:
            check.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")
            txt.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        self._ok_btn.setStyleSheet(f"""
            QPushButton {{
                background: {pal['TELE_GREEN']};
                color: {pal['EXPORT_FG']};
                border: none;
                border-radius: 4px;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{ background: #00D080; }}
        """)


class PaywallDialog(QDialog):
    """Mur de paiement neoSlice Pro (frameless, thème-aware, déplaçable)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(460)
        self._drag_pos: QPoint | None = None
        self._setup_ui()
        self._apply_theme()
        _T.register(self._apply_theme)

    def closeEvent(self, event):
        _T.unregister(self._apply_theme)
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._center_on_screen()

    def _center_on_screen(self):
        """Centre la fenêtre sur l'écran (sinon elle se colle en haut)."""
        scr = self.screen()
        par = self.parent()
        if par is not None and par.screen() is not None:
            scr = par.screen()
        if scr is not None:
            geo = scr.availableGeometry()
            self.move(
                geo.center().x() - self.width() // 2,
                geo.center().y() - self.height() // 2,
            )

    # ── Déplacement à la souris ──────────────────────────────────────────────
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, ev):
        if self._drag_pos and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _ev):
        self._drag_pos = None

    # ── Construction UI ──────────────────────────────────────────────────────
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._card = QWidget()
        self._card.setObjectName("paywall_card")
        lay = QVBoxLayout(self._card)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(0)
        root.addWidget(self._card)

        # Icône + titre
        self._icon_lbl = QLabel("⬡")
        self._icon_lbl.setFont(QFont(FONT_MAIN, 32))
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._icon_lbl)
        lay.addSpacing(10)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.addStretch()
        self._title_lbl = QLabel("NEOSLICE")
        self._title_lbl.setFont(QFont(FONT_MAIN, 13, QFont.Bold))
        title_row.addWidget(self._title_lbl)
        self._title_pro = ProBadge("PRO", point_size=13, letter_spacing=2.0)
        title_row.addWidget(self._title_pro)
        title_row.addStretch()
        lay.addLayout(title_row)
        lay.addSpacing(6)

        self._subtitle_lbl = QLabel(_("pro.paywall_subtitle"))
        self._subtitle_lbl.setFont(QFont(FONT_MAIN, 8))
        self._subtitle_lbl.setAlignment(Qt.AlignCenter)
        self._subtitle_lbl.setWordWrap(True)
        lay.addWidget(self._subtitle_lbl)
        lay.addSpacing(18)

        # Prix + bouton acheter
        self._price_lbl = QLabel(_("pro.price_suffix", price=licensing.PRIX_AFFICHE))
        self._price_lbl.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
        self._price_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._price_lbl)
        lay.addSpacing(12)

        self._buy_btn = QPushButton(_("pro.unlock_btn"))
        self._buy_btn.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._buy_btn.setFixedHeight(38)
        self._buy_btn.setCursor(Qt.PointingHandCursor)
        self._buy_btn.clicked.connect(self._on_buy)
        lay.addWidget(self._buy_btn)
        lay.addSpacing(18)

        self._sep1 = _sep()
        lay.addWidget(self._sep1)
        lay.addSpacing(14)

        # Activation d'une clé déjà achetée
        self._activate_title = QLabel(_("pro.already_bought"))
        self._activate_title.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        lay.addWidget(self._activate_title)
        lay.addSpacing(8)

        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        self._key_edit = QLineEdit()
        self._key_edit.setPlaceholderText(_("pro.key_placeholder"))
        self._key_edit.setFixedHeight(34)
        self._key_edit.returnPressed.connect(self._on_activate)
        self._activate_btn = QPushButton(_("pro.activate_btn"))
        self._activate_btn.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._activate_btn.setFixedHeight(34)
        self._activate_btn.setCursor(Qt.PointingHandCursor)
        self._activate_btn.clicked.connect(self._on_activate)
        key_row.addWidget(self._key_edit, 1)
        key_row.addWidget(self._activate_btn)
        lay.addLayout(key_row)
        lay.addSpacing(8)

        self._status_lbl = QLabel("")
        self._status_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._status_lbl.setAlignment(Qt.AlignCenter)
        self._status_lbl.setWordWrap(True)
        self._status_lbl.hide()
        lay.addWidget(self._status_lbl)
        lay.addSpacing(10)

        self._later_btn = QPushButton(_("pro.later_btn"))
        self._later_btn.setFont(QFont(FONT_MAIN, 8))
        self._later_btn.setFixedHeight(30)
        self._later_btn.setCursor(Qt.PointingHandCursor)
        self._later_btn.clicked.connect(self.reject)
        lay.addWidget(self._later_btn)

    # ── Actions ──────────────────────────────────────────────────────────────
    def _on_buy(self):
        QDesktopServices.openUrl(QUrl(licensing.LIEN_ACHAT))

    def _on_activate(self):
        self._activate_btn.setEnabled(False)
        pal = _T.palette()
        self._status_lbl.setStyleSheet(f"color: {pal['ACCENT']}; background: transparent;")
        self._status_lbl.setText(_("pro.activating"))
        self._status_lbl.show()
        # Repaint immédiat pendant l'appel réseau bloquant
        self._status_lbl.repaint()

        ok, message = licensing.activer_cle(self._key_edit.text())
        self._activate_btn.setEnabled(True)
        self._set_status(message, ok)
        if ok:
            merci = ProThankYouDialog(self.parent() or self)
            merci.exec()
            self.accept()

    def _set_status(self, text: str, ok: bool):
        pal = _T.palette()
        color = pal["TELE_GREEN"] if ok else pal["ERROR_RED"]
        self._status_lbl.setStyleSheet(f"color: {color}; background: transparent;")
        self._status_lbl.setText(text)
        self._status_lbl.show()

    # ── Thème ────────────────────────────────────────────────────────────────
    def _apply_theme(self):
        pal = _T.palette()
        self._card.setStyleSheet(f"""
            QWidget#paywall_card {{
                background: {pal['BG_PANEL']};
                border: 1px solid {pal['ACCENT']};
                border-radius: 8px;
            }}
        """)
        self._icon_lbl.setStyleSheet(f"color: {pal['ACCENT']}; background: transparent;")
        self._title_lbl.setStyleSheet(
            f"color: {pal['TEXT_PRIMARY']}; background: transparent; letter-spacing: 2px;"
        )
        self._subtitle_lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        self._price_lbl.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")
        self._activate_title.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        self._sep1.setStyleSheet(f"background: {pal['INACTIVE']}; border: none;")

        self._key_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {pal['BG_ELEVATED']};
                color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']};
                border-radius: 4px;
                padding: 0 8px;
            }}
            QLineEdit:focus {{ border-color: {pal['ACCENT']}; }}
        """)
        self._buy_btn.setStyleSheet(f"""
            QPushButton {{
                background: {pal['TELE_GREEN']};
                color: {pal['EXPORT_FG']};
                border: none;
                border-radius: 4px;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{ background: #00D080; }}
        """)
        self._activate_btn.setStyleSheet(f"""
            QPushButton {{
                background: {pal['ACCENT']};
                color: {pal['EXPORT_FG']};
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{ opacity: 0.9; }}
        """)
        self._later_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {pal['TEXT_SECONDARY']};
                border: none;
            }}
            QPushButton:hover {{ color: {pal['TEXT_PRIMARY']}; }}
        """)
