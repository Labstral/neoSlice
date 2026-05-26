from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QFrame, QPushButton,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Signal
from PySide6.QtGui import QFont, QColor

from ui.styles.theme import (
    BG_PANEL, BG_SURFACE, BG_ELEVATED,
    ACCENT, ACCENT_BRIGHT, TELE_GREEN, AMBER, ERROR_RED,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_LABEL, INACTIVE,
    FONT_MONO, score_color,
)
from core.geometry.analysis_report import AnalysisReport


class _GaugeRow(QWidget):
    """Jauge NASA : label + barre gradient + valeur mono."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        self._label = QLabel(label.upper())
        self._label.setFont(QFont("Segoe UI", 7, QFont.Bold))
        self._label.setStyleSheet(f"color: {TEXT_LABEL}; letter-spacing: 1px; background: transparent;")
        self._label.setFixedWidth(88)
        layout.addWidget(self._label)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setFixedHeight(5)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                background: {INACTIVE};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {ACCENT}, stop:1 {TELE_GREEN});
                border-radius: 2px;
            }}
        """)
        layout.addWidget(self._bar, 1)

        self._val = QLabel("———")
        self._val.setFont(QFont(FONT_MONO, 8))
        self._val.setStyleSheet(f"color: {INACTIVE}; background: transparent;")
        self._val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._val.setFixedWidth(44)
        layout.addWidget(self._val)

    def set_value(self, score: float, text: str = "", color_score: float | None = None):
        pct = int(score * 100)
        color = score_color(color_score if color_score is not None else score)

        anim = QPropertyAnimation(self._bar, b"value", self)
        anim.setDuration(500)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setEndValue(pct)
        anim.start(QPropertyAnimation.DeleteWhenStopped)

        self._val.setText(text or f"{pct}%")
        self._val.setStyleSheet(f"color: {color}; background: transparent;")
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                background: {INACTIVE};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {ACCENT}, stop:1 {color});
                border-radius: 2px;
            }}
        """)

    def reset(self):
        self._bar.setValue(0)
        self._bar.setStyleSheet(f"""
            QProgressBar {{ background: {INACTIVE}; border: none; border-radius: 2px; }}
            QProgressBar::chunk {{ background: {INACTIVE}; border-radius: 2px; }}
        """)
        self._val.setText("———")
        self._val.setStyleSheet(f"color: {INACTIVE}; background: transparent;")


class _StatusDot(QLabel):
    """Indicateur point coloré."""
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._label_text = label
        self.setFont(QFont(FONT_MONO, 7))
        self.set_inactive()

    def set_active(self):
        self.setText(f"● {self._label_text}")
        self.setStyleSheet(f"color: {TELE_GREEN}; background: transparent;")

    def set_busy(self):
        self.setText(f"◌ {self._label_text}")
        self.setStyleSheet(f"color: {AMBER}; background: transparent;")

    def set_inactive(self):
        self.setText(f"○ {self._label_text}")
        self.setStyleSheet(f"color: {INACTIVE}; background: transparent;")

    def set_error(self):
        self.setText(f"✕ {self._label_text}")
        self.setStyleSheet(f"color: {ERROR_RED}; background: transparent;")


class AnalysisPanel(QWidget):
    """Panneau d'analyse géométrique — jauges NASA compactes."""

    apply_orientation = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {BG_PANEL};")
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(6)

        # ── Status dots ────────────────────────────────────────────────────
        dots_row = QHBoxLayout()
        dots_row.setSpacing(16)
        self._dot_sys    = _StatusDot("SYSTÈME")
        self._dot_stl    = _StatusDot("STL")
        self._dot_anlys  = _StatusDot("ANALYSE")
        self._dot_gen    = _StatusDot("GÉNÉRATION")
        self._dot_sys.set_active()
        dots_row.addWidget(self._dot_sys)
        dots_row.addWidget(self._dot_stl)
        dots_row.addWidget(self._dot_anlys)
        dots_row.addWidget(self._dot_gen)
        dots_row.addStretch()
        root.addLayout(dots_row)

        # ── Séparateur ─────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {INACTIVE};")
        root.addWidget(sep)

        # ── Jauges ─────────────────────────────────────────────────────────
        gauges = QWidget()
        gauges.setStyleSheet(f"background: {BG_SURFACE}; border-radius: 3px;")
        g_layout = QVBoxLayout(gauges)
        g_layout.setContentsMargins(10, 8, 10, 8)
        g_layout.setSpacing(6)

        self._g_overhangs = _GaugeRow("Surplombs")
        self._g_stability = _GaugeRow("Stabilité")
        self._g_fragility = _GaugeRow("Fragilité")
        self._g_support   = _GaugeRow("Vol. support")
        g_layout.addWidget(self._g_overhangs)
        g_layout.addWidget(self._g_stability)
        g_layout.addWidget(self._g_fragility)
        g_layout.addWidget(self._g_support)
        root.addWidget(gauges)

        # Tooltips explicatifs pour les débutants
        self._g_overhangs.setToolTip(
            "Surplombs : zones inclinées à plus de 45° sans matière en-dessous.\n"
            "Élevé → activez les supports dans Bambu Studio pour éviter l'effondrement."
        )
        self._g_stability.setToolTip(
            "Stabilité sur le plateau : plus c'est haut, mieux la pièce tient.\n"
            "Faible → risque de décollement en cours d'impression → utilisez un brim."
        )
        self._g_fragility.setToolTip(
            "Épaisseur minimale des parois détectée dans la pièce.\n"
            "La valeur affichée est l'épaisseur réelle (en mm).\n"
            "En dessous de 1,2 mm → risque de cassure ou mauvaise impression → augmentez les parois."
        )
        self._g_support.setToolTip(
            "Volume de matière support nécessaire par rapport à la pièce.\n"
            "Élevé → plus de filament consommé et temps d'impression plus long."
        )

        # ── Données dimensionnelles ────────────────────────────────────────
        geo = QWidget()
        geo.setStyleSheet(f"background: {BG_SURFACE}; border-radius: 3px;")
        geo_layout = QHBoxLayout(geo)
        geo_layout.setContentsMargins(10, 6, 10, 6)
        geo_layout.setSpacing(0)

        self._geo: dict[str, QLabel] = {}
        fields = [
            ("X", "———"),("Y", "———"),("Z", "———"),
            ("VOL", "———"),("FACES", "———"),
        ]
        for i, (key, default) in enumerate(fields):
            col = QVBoxLayout()
            col.setSpacing(1)
            lbl_k = QLabel(key)
            lbl_k.setFont(QFont("Segoe UI", 6, QFont.Bold))
            lbl_k.setStyleSheet(f"color: {TEXT_LABEL}; letter-spacing: 1px; background: transparent;")
            lbl_k.setAlignment(Qt.AlignCenter)
            lbl_v = QLabel(default)
            lbl_v.setFont(QFont(FONT_MONO, 8))
            lbl_v.setStyleSheet(f"color: {INACTIVE}; background: transparent;")
            lbl_v.setAlignment(Qt.AlignCenter)
            lbl_v.setWordWrap(True)
            col.addWidget(lbl_k)
            col.addWidget(lbl_v)
            geo_layout.addLayout(col, 1)
            if i < len(fields) - 1:
                vsep = QFrame()
                vsep.setFrameShape(QFrame.VLine)
                vsep.setStyleSheet(f"color: {INACTIVE};")
                geo_layout.addWidget(vsep)
            self._geo[key] = lbl_v

        root.addWidget(geo)

        # ── Bloc status : verdict + infos condensées (toujours dans le DOM) ──
        # Ne jamais appeler hide() sur ce widget — utiliser setText("") pour vider.
        # Cela évite le flash de lignes vertes lors du rechargement d'analyse.
        self._status_block = QLabel()
        self._status_block.setFont(QFont(FONT_MONO, 8))
        self._status_block.setTextFormat(Qt.RichText)
        self._status_block.setWordWrap(True)
        self._status_block.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._status_block.setContentsMargins(0, 0, 0, 0)
        self._status_block.setStyleSheet("background: transparent;")
        root.addWidget(self._status_block)

        # ── Bouton : appliquer l'orientation optimale ──────────────────────
        self._orient_btn = QPushButton("↻  Appliquer l'orientation recommandée")
        self._orient_btn.setFont(QFont("Segoe UI", 8, QFont.Bold))
        self._orient_btn.setFixedHeight(26)
        self._orient_btn.setCursor(Qt.PointingHandCursor)
        self._orient_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {ACCENT};
                border: 1px solid {ACCENT};
                border-radius: 3px;
                padding: 0 10px;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background: {ACCENT};
                color: #020408;
            }}
        """)
        self._orient_btn.hide()
        self._orient_btn.clicked.connect(self.apply_orientation)
        root.addWidget(self._orient_btn)

        # ── Alertes matériau (remplies après génération du profil) ─────────
        self._material_warn = QLabel()
        self._material_warn.setFont(QFont(FONT_MONO, 7))
        self._material_warn.setWordWrap(True)
        self._material_warn.setContentsMargins(0, 0, 0, 0)
        self._material_warn.setStyleSheet("background: transparent;")
        root.addWidget(self._material_warn)

    # ── API publique ───────────────────────────────────────────────────────

    def update_from_report(self, report: AnalysisReport):
        # Dots
        self._dot_stl.set_active()
        self._dot_anlys.set_active()

        # Jauges
        # Surplombs : barre = ratio brut, couleur inversée (peu = vert, beaucoup = rouge)
        self._g_overhangs.set_value(report.overhang_ratio,
                                     f"{int(report.overhang_ratio*100)}%",
                                     color_score=1.0 - report.overhang_ratio)
        # Stabilité : haut = bon → couleur directe
        self._g_stability.set_value(report.stability_score,
                                     f"{int(report.stability_score*100)}%")
        # Fragilité : sévérité gradient + épaisseur min réelle
        frag_sev = getattr(report, "fragility_severity", 1.0 if report.has_fragile_zones else 0.0)
        self._g_fragility.set_value(frag_sev, f"{int(frag_sev * 100)}%", color_score=1.0 - frag_sev)
        # Vol. support : peu = vert, beaucoup = rouge
        self._g_support.set_value(report.estimated_support_ratio,
                                   f"{int(report.estimated_support_ratio*100)}%",
                                   color_score=1.0 - report.estimated_support_ratio)

        # Données geo
        bb = report.bounding_box_mm
        self._set_geo("X",     f"{bb[0]:.0f}mm",  active=True)
        self._set_geo("Y",     f"{bb[1]:.0f}mm",  active=True)
        self._set_geo("Z",     f"{bb[2]:.0f}mm",  active=True)
        self._set_geo("VOL",   f"{report.volume_cm3:.1f}cm³", active=True)
        self._set_geo("FACES", str(len(report.bounding_box_mm) * 100 // 100), active=True)

        # ── Verdict + bloc compact (rendu en HTML, pas de show/hide) ─────────
        complexity = report.overall_complexity
        if complexity < 0.25 and not report.support_needed:
            verdict_text   = "✓  PRÊT À IMPRIMER"
            verdict_color  = TELE_GREEN
            verdict_bg     = "#0B1E14"
            verdict_border = TELE_GREEN
        elif complexity < 0.55 or (report.support_needed and complexity < 0.6):
            verdict_text   = "⚠  VÉRIFIER AVANT IMPRESSION"
            verdict_color  = AMBER
            verdict_bg     = "#1E1800"
            verdict_border = AMBER
        else:
            verdict_text   = "⛔  PIÈCE COMPLEXE — ATTENTION"
            verdict_color  = ERROR_RED
            verdict_bg     = "#200A0A"
            verdict_border = ERROR_RED

        rows = []
        ovh_pct = int(report.overhang_ratio * 100)
        has_floating = getattr(report, "has_floating_regions", False)

        if has_floating:
            rows.append(f'<span style="color:{ERROR_RED};">⛔ Régions flottantes — supports obligatoires</span>')
        elif report.support_needed:
            rows.append(f'<span style="color:{ERROR_RED};">⚠ Supports requis ({ovh_pct}% surplombs)</span>')
        elif report.overhang_ratio > 0.1:
            rows.append(f'<span style="color:{AMBER};">⚠ Surplombs modérés ({ovh_pct}%) — vérifier</span>')
        else:
            rows.append(f'<span style="color:{TELE_GREEN};">✓ Sans support ({ovh_pct}% surplombs)</span>')

        if report.stability_score < 0.4:
            rows.append(f'<span style="color:{ERROR_RED};">⚠ Stabilité faible — brim obligatoire</span>')
        elif report.stability_score < 0.65:
            rows.append(f'<span style="color:{AMBER};">⚠ Stabilité modérée — brim conseillé</span>')
        else:
            rows.append(f'<span style="color:{TELE_GREEN};">✓ Stable — brim non nécessaire</span>')

        if report.has_fragile_zones:
            rows.append(
                f'<span style="color:{AMBER};">⚠ Parois fines — min {report.min_wall_thickness_mm:.1f} mm'
                f' (rec. {report.nozzle_diameter_mm * 3.0:.1f} mm)</span>'
            )

        if report.is_large_flat_part:
            rows.append(f'<span style="color:{AMBER};">⚠ Pièce plate — risque warping</span>')

        orient_label = report.orientation_label
        improvement = getattr(report, "orientation_improvement_pct", 0.0)
        if orient_label and orient_label != "Actuelle (Z+)" and improvement > 8.0:
            rows.append(
                f'<span style="color:{ACCENT_BRIGHT};">↻ Orientation optimale : {orient_label} (+{improvement:.0f}%)</span>'
            )
            self._orient_btn.setText(f"↻  Appliquer — {orient_label}  (+{improvement:.0f}%)")
            self._orient_btn.show()
        else:
            self._orient_btn.hide()

        rows_html = "<br>".join(rows)
        status_html = (
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr>'
            f'<td width="3" bgcolor="{verdict_border}">&nbsp;</td>'
            f'<td bgcolor="{verdict_bg}" style="padding:5px 8px;">'
            f'<span style="color:{verdict_color}; font-weight:bold;">{verdict_text}</span>'
            f'</td></tr>'
            f'<tr><td colspan="2" height="3"></td></tr>'
            f'<tr><td colspan="2" bgcolor="{BG_SURFACE}" style="padding:6px 8px;">'
            f'{rows_html}'
            f'</td></tr>'
            f'</table>'
        )
        self._status_block.setText(status_html)

    def set_loading(self):
        self._dot_stl.set_active()
        self._dot_anlys.set_busy()
        for g in (self._g_overhangs, self._g_stability, self._g_fragility, self._g_support):
            g.reset()
        self.set_progress(0, "Initialisation...")
        self._material_warn.setText("")
        self._material_warn.setStyleSheet("background: transparent;")

    def set_progress(self, pct: int, msg: str) -> None:
        """Affiche la progression en temps réel pendant l'analyse."""
        html = (
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr>'
            f'<td style="color:{TEXT_LABEL}; font-family:{FONT_MONO}; font-size:7pt;">'
            f'◌&nbsp;ANALYSE EN COURS</td>'
            f'<td align="right" style="color:{ACCENT}; font-family:{FONT_MONO}; '
            f'font-size:9pt; font-weight:bold;">{pct}%</td>'
            f'</tr>'
            f'<tr><td colspan="2" style="color:{TEXT_SECONDARY}; font-family:{FONT_MONO}; '
            f'font-size:7pt; padding-top:3px;">{msg}</td></tr>'
            f'</table>'
        )
        self._status_block.setText(html)

    def _set_geo(self, key: str, value: str, active: bool = False):
        if key in self._geo:
            color = TELE_GREEN if active else INACTIVE
            self._geo[key].setText(value)
            self._geo[key].setStyleSheet(f"color: {color}; background: transparent;")

    def show_material_warnings(self, warnings: list[str]) -> None:
        """Affiche les alertes matériau×géométrie après génération de la config."""
        if warnings:
            lines = ["⚠ " + (w[:78] + "…" if len(w) > 80 else w) for w in warnings]
            self._material_warn.setText("\n".join(lines))
            self._material_warn.setStyleSheet(
                f"color: {AMBER}; background: rgba(255,184,0,0.07); "
                f"border-left: 2px solid {AMBER}; border-radius: 2px; padding: 3px 6px;"
            )
        else:
            self._material_warn.setText("")
            self._material_warn.setStyleSheet("background: transparent;")

    def set_generation_active(self):
        self._dot_gen.set_active()

    def set_generation_busy(self):
        self._dot_gen.set_busy()

    def mark_orientation_applied(self) -> None:
        """Appelé après application de l'orientation — masque le bouton."""
        self._orient_btn.hide()

    def reset(self):
        self._dot_stl.set_inactive()
        self._dot_anlys.set_inactive()
        self._dot_gen.set_inactive()
        for g in (self._g_overhangs, self._g_stability, self._g_fragility, self._g_support):
            g.reset()
        for key in list(self._geo.keys()):
            self._set_geo(key, "———", active=False)
        self._status_block.setText("")
        self._material_warn.setText("")
        self._material_warn.setStyleSheet("background: transparent;")
        self._orient_btn.hide()
