"""Fenêtre « Licences et mentions », modale, sans chrome OS, thème-aware.

Regroupe, dans une vue scrollable, les licences des composants tiers (moteur
Ollama, modèles d'IA) et l'attribution des sources publiques ayant servi à
constituer la base de connaissances de l'assistant. But : créditer les auteurs
et respecter leurs conditions d'utilisation.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QTextBrowser,
    QVBoxLayout, QWidget,
)

from core.i18n import _
from ui.styles.theme import MANAGER as _T, FONT_MAIN, FONT_MONO


# ── Textes de licence (verbatim, laissés en anglais comme il se doit) ─────────
MIT_OLLAMA = """MIT License

Copyright (c) Ollama

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE."""

APACHE_2_0 = """Apache License
Version 2.0, January 2004
http://www.apache.org/licenses/

TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

1. Definitions.

   "License" shall mean the terms and conditions for use, reproduction, and
   distribution as defined by Sections 1 through 9 of this document.

   "Licensor" shall mean the copyright owner or entity authorized by the
   copyright owner that is granting the License.

   "Legal Entity" shall mean the union of the acting entity and all other
   entities that control, are controlled by, or are under common control with
   that entity. For the purposes of this definition, "control" means (i) the
   power, direct or indirect, to cause the direction or management of such
   entity, whether by contract or otherwise, or (ii) ownership of fifty percent
   (50%) or more of the outstanding shares, or (iii) beneficial ownership of
   such entity.

   "You" (or "Your") shall mean an individual or Legal Entity exercising
   permissions granted by this License.

   "Source" form shall mean the preferred form for making modifications,
   including but not limited to software source code, documentation source, and
   configuration files.

   "Object" form shall mean any form resulting from mechanical transformation or
   translation of a Source form, including but not limited to compiled object
   code, generated documentation, and conversions to other media types.

   "Work" shall mean the work of authorship, whether in Source or Object form,
   made available under the License, as indicated by a copyright notice that is
   included in or attached to the work.

   "Derivative Works" shall mean any work, whether in Source or Object form, that
   is based on (or derived from) the Work and for which the editorial revisions,
   annotations, elaborations, or other modifications represent, as a whole, an
   original work of authorship.

   "Contribution" shall mean any work of authorship, including the original
   version of the Work and any modifications or additions to that Work or
   Derivative Works thereof, that is intentionally submitted to Licensor for
   inclusion in the Work by the copyright owner or by an individual or Legal
   Entity authorized to submit on behalf of the copyright owner.

   "Contributor" shall mean Licensor and any individual or Legal Entity on behalf
   of whom a Contribution has been received by Licensor and subsequently
   incorporated within the Work.

2. Grant of Copyright License. Subject to the terms and conditions of this
   License, each Contributor hereby grants to You a perpetual, worldwide,
   non-exclusive, no-charge, royalty-free, irrevocable copyright license to
   reproduce, prepare Derivative Works of, publicly display, publicly perform,
   sublicense, and distribute the Work and such Derivative Works in Source or
   Object form.

3. Grant of Patent License. Subject to the terms and conditions of this License,
   each Contributor hereby grants to You a perpetual, worldwide, non-exclusive,
   no-charge, royalty-free, irrevocable (except as stated in this section) patent
   license to make, have made, use, offer to sell, sell, import, and otherwise
   transfer the Work.

4. Redistribution. You may reproduce and distribute copies of the Work or
   Derivative Works thereof in any medium, with or without modifications, and in
   Source or Object form, provided that You meet the conditions stated in the
   License, including retaining copyright, patent, trademark, and attribution
   notices.

5. Submission of Contributions. Unless You explicitly state otherwise, any
   Contribution intentionally submitted for inclusion in the Work shall be under
   the terms and conditions of this License.

6. Trademarks. This License does not grant permission to use the trade names,
   trademarks, service marks, or product names of the Licensor.

7. Disclaimer of Warranty. Unless required by applicable law or agreed to in
   writing, Licensor provides the Work on an "AS IS" BASIS, WITHOUT WARRANTIES OR
   CONDITIONS OF ANY KIND, either express or implied.

8. Limitation of Liability. In no event and under no legal theory shall any
   Contributor be liable to You for damages arising as a result of this License
   or out of the use or inability to use the Work.

9. Accepting Warranty or Additional Liability. While redistributing the Work or
   Derivative Works thereof, You may choose to offer, and charge a fee for,
   acceptance of support, warranty, indemnity, or other liability obligations
   and/or rights consistent with this License. However, in accepting such
   obligations, You may act only on Your own behalf and on Your sole
   responsibility, not on behalf of any other Contributor.

END OF TERMS AND CONDITIONS"""


# ── Sources de la base de connaissances (attribution) ─────────────────────────
# name, url. Documentation publique des fabricants et communautés.
KB_SOURCES: tuple[tuple[str, str], ...] = (
    ("Creality", "https://wiki.creality.com"),
    ("Anycubic", "https://wiki.anycubic.com"),
    ("Elegoo", "https://wiki.elegoo.com"),
    ("Snapmaker", "https://wiki.snapmaker.com"),
    ("QIDI", "https://wiki.qidi3d.com"),
    ("FlashForge", "https://wiki.flashforge.com"),
    ("FLSUN", "https://wiki.flsun3d.com"),
    ("Two Trees", "https://wiki.twotrees3d.com"),
    ("Rat Rig", "https://wiki.ratrig.com"),
    ("Sovol", "https://wiki.sovol3d.com"),
    ("Artillery", "https://wiki.artillery3d.com"),
    ("Kingroon", "https://wiki.kingroon.com"),
    ("Prusa Knowledge Base", "https://help.prusa3d.com"),
    ("Voron Documentation", "https://voron3d.wiki"),
    ("Bambu Lab Wiki", "https://wiki.bambulab.com"),
    ("Tronxy", "https://www.tronxy3d.com/pages/support-center-1"),
    ("Eryone", "https://www.eryone.com/support-center/"),
    ("Longer", "https://www.longer3d.com/"),
)


class LicensesDialog(QDialog):
    """Fenêtre scrollable des licences et attributions. Ouverte depuis les
    paramètres. Sans chrome OS, déplaçable, suit le thème actif."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.setFixedSize(560, 620)
        self._drag_pos: QPoint | None = None
        self._setup_ui()
        self._apply_theme()
        _T.register(self._apply_theme)

    def closeEvent(self, event):
        _T.unregister(self._apply_theme)
        super().closeEvent(event)

    # ── Drag (barre de titre) ────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # ── UI ───────────────────────────────────────────────────────────────────
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._card = QWidget()
        self._card.setObjectName("licenses_card")
        lay = QVBoxLayout(self._card)
        lay.setContentsMargins(22, 16, 22, 18)
        lay.setSpacing(0)
        root.addWidget(self._card)

        # Barre titre
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 12)
        self._title_lbl = QLabel(_("licenses.title"))
        self._title_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        self._close_x = QPushButton("✕")
        self._close_x.setFixedSize(22, 22)
        self._close_x.setFont(QFont(FONT_MAIN, 9))
        self._close_x.setCursor(Qt.PointingHandCursor)
        self._close_x.clicked.connect(self.close)
        title_row.addWidget(self._title_lbl)
        title_row.addStretch()
        title_row.addWidget(self._close_x)
        lay.addLayout(title_row)

        self._sep = QFrame()
        self._sep.setFrameShape(QFrame.Shape.HLine)
        self._sep.setFixedHeight(1)
        lay.addWidget(self._sep)
        lay.addSpacing(12)

        # Corps scrollable
        self._body = QTextBrowser()
        self._body.setOpenExternalLinks(True)
        self._body.setFrameShape(QFrame.Shape.NoFrame)
        lay.addWidget(self._body, 1)

        lay.addSpacing(12)

        # Bouton Fermer
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.addStretch()
        self._close_btn = QPushButton(_("licenses.close"))
        self._close_btn.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        self._close_btn.setFixedHeight(28)
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.clicked.connect(self.close)
        btn_row.addWidget(self._close_btn)
        lay.addLayout(btn_row)

    # ── Contenu HTML (thémé) ─────────────────────────────────────────────────
    def _build_html(self) -> str:
        pal = _T.palette()
        c_text = pal["TEXT_PRIMARY"]
        c_head = pal["ACCENT_BRIGHT"]
        c_sub = pal["TEXT_SECONDARY"]
        c_pre_bg = pal["BG_INPUT"]
        c_border = pal["INACTIVE"]

        def esc(s: str) -> str:
            return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

        def block(title: str, body_text: str) -> str:
            return (
                f"<p style='color:{c_head};font-weight:bold;margin:14px 0 4px 0;'>{esc(title)}</p>"
                f"<pre style='background:{c_pre_bg};border:1px solid {c_border};"
                f"border-radius:6px;padding:10px;white-space:pre-wrap;"
                f"font-family:{FONT_MONO};font-size:11px;color:{c_text};'>{esc(body_text)}</pre>"
            )

        parts: list[str] = []
        parts.append(
            f"<p style='color:{c_sub};font-size:12px;'>{esc(_('licenses.intro'))}</p>")

        # Moteur d'IA
        parts.append(
            f"<p style='color:{c_head};font-weight:bold;font-size:14px;"
            f"margin:16px 0 2px 0;'>{esc(_('licenses.sec_engine'))}</p>")
        parts.append(
            f"<p style='color:{c_text};font-size:12px;margin:2px 0;'>"
            "<b>Ollama</b> (moteur d'inference local), sous licence MIT.<br>"
            "<a href='https://github.com/ollama/ollama' style='color:" + c_head +
            "';>github.com/ollama/ollama</a></p>")
        parts.append(block("Ollama - MIT License", MIT_OLLAMA))

        parts.append(
            f"<p style='color:{c_text};font-size:12px;margin:10px 0 2px 0;'>"
            "<b>Qwen3-8B</b> (modele de discussion d'Oen), par Alibaba Cloud, "
            "sous licence Apache 2.0.<br>"
            "<a href='https://huggingface.co/Qwen/Qwen3-8B' style='color:" + c_head +
            "';>huggingface.co/Qwen/Qwen3-8B</a></p>")
        parts.append(
            f"<p style='color:{c_text};font-size:12px;margin:10px 0 2px 0;'>"
            "<b>Gemma 4 12B</b> (modele de generation 3D de neoGen), par Google "
            "DeepMind, sous les <i>Gemma Terms of Use</i> (usage et redistribution "
            "permis dans le respect de la politique d'usage interdit).<br>"
            "<a href='https://ai.google.dev/gemma/terms' style='color:" + c_head +
            "';>ai.google.dev/gemma/terms</a></p>")
        parts.append(
            f"<p style='color:{c_text};font-size:12px;margin:10px 0 2px 0;'>"
            "<b>nomic-embed-text</b> (modele d'embedding pour la recherche), par "
            "Nomic AI, sous licence Apache 2.0.<br>"
            "<a href='https://huggingface.co/nomic-ai/nomic-embed-text-v1.5' style='color:" + c_head +
            "';>huggingface.co/nomic-ai/nomic-embed-text-v1.5</a></p>")

        # Bibliothèques logicielles principales
        parts.append(
            f"<p style='color:{c_head};font-weight:bold;font-size:14px;"
            f"margin:16px 0 2px 0;'>{esc(_('licenses.sec_libs'))}</p>")
        libs = (
            ("PySide6 / Qt 6", "LGPL v3", "https://www.qt.io/qt-for-python"),
            ("PyVista", "MIT", "https://github.com/pyvista/pyvista"),
            ("Trimesh", "MIT", "https://github.com/mikedh/trimesh"),
            ("Shapely", "BSD-3-Clause", "https://github.com/shapely/shapely"),
            ("NumPy / SciPy", "BSD-3-Clause", "https://numpy.org"),
            ("Matplotlib", "PSF-based (Matplotlib License)", "https://matplotlib.org"),
            ("OpenCV", "Apache 2.0", "https://opencv.org"),
            ("manifold3d", "Apache 2.0", "https://github.com/elalish/manifold"),
            ("mapbox-earcut", "ISC", "https://github.com/skogler/mapbox_earcut_python"),
            ("svgelements", "MIT", "https://github.com/meerk40t/svgelements"),
            ("Pydantic", "MIT", "https://github.com/pydantic/pydantic"),
        )
        rows_libs = "".join(
            f"<li style='margin:3px 0;'>{esc(n)} — {esc(lic)} : "
            f"<a href='{u}' style='color:{c_head};'>{esc(u)}</a></li>"
            for n, lic, u in libs)
        parts.append(
            f"<ul style='color:{c_text};font-size:12px;margin:4px 0;'>{rows_libs}</ul>")

        # Texte Apache 2.0 (une seule fois, vaut pour tous les composants Apache)
        parts.append(
            f"<p style='color:{c_head};font-weight:bold;font-size:14px;"
            f"margin:16px 0 2px 0;'>{esc(_('licenses.sec_apache'))}</p>")
        parts.append(block("Apache License 2.0", APACHE_2_0))

        # Sources de la base de connaissances
        parts.append(
            f"<p style='color:{c_head};font-weight:bold;font-size:14px;"
            f"margin:16px 0 2px 0;'>{esc(_('licenses.sec_kb'))}</p>")
        parts.append(
            f"<p style='color:{c_sub};font-size:12px;'>{esc(_('licenses.kb_intro'))}</p>")
        rows = "".join(
            f"<li style='margin:3px 0;'>{esc(name)} : "
            f"<a href='{url}' style='color:{c_head};'>{esc(url)}</a></li>"
            for name, url in KB_SOURCES)
        parts.append(
            f"<ul style='color:{c_text};font-size:12px;margin:4px 0;'>{rows}</ul>")

        return (
            f"<div style='color:{c_text};font-family:{FONT_MAIN};'>"
            + "".join(parts) + "</div>")

    # ── Thème ────────────────────────────────────────────────────────────────
    def _apply_theme(self):
        pal = _T.palette()
        self._card.setStyleSheet(f"""
            QWidget#licenses_card {{
                background: {pal['BG_PANEL']};
                border: 1px solid {pal['INACTIVE']};
                border-radius: 8px;
            }}
        """)
        self._title_lbl.setStyleSheet(
            f"color: {pal['ACCENT_BRIGHT']}; background: transparent; letter-spacing: 2px;")
        self._sep.setStyleSheet(f"background: {pal['INACTIVE']}; border: none;")
        self._close_x.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {pal['TEXT_SECONDARY']};
                border: none; border-radius: 3px;
            }}
            QPushButton:hover {{ background: {pal['ERROR_RED']}; color: #ffffff; }}
        """)
        self._body.setStyleSheet(f"""
            QTextBrowser {{
                background: {pal['BG_PANEL']}; border: none;
            }}
            QScrollBar:vertical {{
                background: transparent; width: 10px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {pal['INACTIVE']}; border-radius: 5px; min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {pal['ACCENT']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self._close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {pal['BG_ELEVATED']}; color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']}; border-radius: 4px;
                padding: 4px 18px; font-family: {FONT_MAIN};
            }}
            QPushButton:hover {{ background: {pal['BG_SURFACE']}; border-color: {pal['ACCENT']}; }}
        """)
        # Regenerer le contenu avec les couleurs du thème courant
        self._body.setHtml(self._build_html())
