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
    FONT_MONO, score_color, MANAGER as _T,
)
from core.geometry.analysis_report import AnalysisReport
from core.i18n import _


class _GaugeRow(QWidget):
    """Jauge NASA : label + barre gradient + valeur mono."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        self._label = QLabel(label.upper())
        self._label.setFont(QFont("Segoe UI", 7, QFont.Bold))
        _p0 = _T.palette()
        self._label.setStyleSheet(f"color: {_p0['TEXT_LABEL']}; letter-spacing: 1px; background: transparent;")
        self._label.setFixedWidth(88)
        layout.addWidget(self._label)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setFixedHeight(5)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                background: {_p0["INACTIVE"]};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {_p0["ACCENT"]}, stop:1 {_p0["TELE_GREEN"]});
                border-radius: 2px;
            }}
        """)
        layout.addWidget(self._bar, 1)

        self._val = QLabel(_("analysis.default_val"))
        self._val.setFont(QFont(FONT_MONO, 8))
        self._val.setStyleSheet(f"color: {_p0['INACTIVE']}; background: transparent;")
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

        _ps = _T.palette()
        self._val.setText(text or f"{pct}%")
        self._val.setStyleSheet(f"color: {color}; background: transparent;")
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                background: {_ps["INACTIVE"]};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {_ps["ACCENT"]}, stop:1 {color});
                border-radius: 2px;
            }}
        """)

    def reset(self):
        _pr = _T.palette()
        self._bar.setValue(0)
        self._bar.setStyleSheet(f"""
            QProgressBar {{ background: {_pr["INACTIVE"]}; border: none; border-radius: 2px; }}
            QProgressBar::chunk {{ background: {_pr["INACTIVE"]}; border-radius: 2px; }}
        """)
        self._val.setText(_("analysis.default_val"))
        self._val.setStyleSheet(f"color: {_pr['INACTIVE']}; background: transparent;")


class _StatusDot(QLabel):
    """Indicateur point coloré."""
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._label_text = label
        self.setFont(QFont(FONT_MONO, 7))
        self.set_inactive()

    def set_active(self):
        self.setText(f"● {self._label_text}")
        self.setStyleSheet(f"color: {_T.palette()['TELE_GREEN']}; background: transparent;")

    def set_busy(self):
        self.setText(f"◌ {self._label_text}")
        self.setStyleSheet(f"color: {_T.palette()['AMBER']}; background: transparent;")

    def set_inactive(self):
        self.setText(f"○ {self._label_text}")
        self.setStyleSheet(f"color: {_T.palette()['INACTIVE']}; background: transparent;")

    def set_error(self):
        self.setText(f"✕ {self._label_text}")
        self.setStyleSheet(f"color: {_T.palette()['ERROR_RED']}; background: transparent;")


class AnalysisPanel(QWidget):
    """Panneau d'analyse géométrique — jauges NASA compactes."""

    apply_orientation = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_report = None
        self.setStyleSheet(f"background: {BG_PANEL};")
        self._setup_ui()

    def refresh_theme(self):
        pal = _T.palette()
        self.setStyleSheet(f"background: {pal['BG_PANEL']}")
        if hasattr(self, "_sep_line"):
            self._sep_line.setStyleSheet(f"background: {pal['INACTIVE']}")
        if hasattr(self, "_gauges_box"):
            self._gauges_box.setStyleSheet(f"background: {pal['BG_SURFACE']}; border-radius: 3px;")
        if hasattr(self, "_geo_box"):
            self._geo_box.setStyleSheet(f"background: {pal['BG_SURFACE']}; border-radius: 3px;")
        for lbl in getattr(self, "_geo_keys", []):
            lbl.setStyleSheet(f"color: {pal['TEXT_LABEL']}; letter-spacing: 1px; background: transparent;")
        for sep in getattr(self, "_geo_seps", []):
            sep.setStyleSheet(f"color: {pal['INACTIVE']}")
        for lbl in self._geo.values():
            if lbl.text() == _("analysis.default_val"):
                lbl.setStyleSheet(f"color: {pal['INACTIVE']}; background: transparent;")
        for g in (getattr(self, "_g_overhangs", None), getattr(self, "_g_stability", None),
                  getattr(self, "_g_fragility", None), getattr(self, "_g_support", None)):
            if g: g.reset()
        if hasattr(self, "_orient_btn"):
            self._orient_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {pal["ACCENT"]};
                    border: 1px solid {pal["ACCENT"]}; border-radius: 3px; padding: 0 10px;
                }}
                QPushButton:hover {{ background: {pal["ACCENT"]}; color: {pal["EXPORT_FG"]}; }}
            """)
        self.update()
        if hasattr(self, '_last_report') and self._last_report is not None:
            self.update_from_report(self._last_report)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(6)

        # ── Status dots ────────────────────────────────────────────────────
        dots_row = QHBoxLayout()
        dots_row.setSpacing(16)
        self._dot_sys    = _StatusDot(_("analysis.dot_system"))
        self._dot_stl    = _StatusDot(_("analysis.dot_stl"))
        self._dot_anlys  = _StatusDot(_("analysis.dot_analysis"))
        self._dot_gen    = _StatusDot(_("analysis.dot_gen"))
        self._dot_sys.set_active()
        dots_row.addWidget(self._dot_sys)
        dots_row.addWidget(self._dot_stl)
        dots_row.addWidget(self._dot_anlys)
        dots_row.addWidget(self._dot_gen)
        dots_row.addStretch()
        root.addLayout(dots_row)

        # ── Séparateur ─────────────────────────────────────────────────────
        self._sep_line = QFrame()
        self._sep_line.setFixedHeight(1)
        _pi = _T.palette()
        self._sep_line.setStyleSheet(f"background: {_pi['INACTIVE']}")
        root.addWidget(self._sep_line)

        # ── Jauges ─────────────────────────────────────────────────────────
        self._gauges_box = gauges = QWidget()
        gauges.setStyleSheet(f"background: {_pi['BG_SURFACE']}; border-radius: 3px;")
        g_layout = QVBoxLayout(gauges)
        g_layout.setContentsMargins(10, 8, 10, 8)
        g_layout.setSpacing(6)

        self._g_overhangs = _GaugeRow(_("analysis.gauge_oh"))
        self._g_stability = _GaugeRow(_("analysis.gauge_stab"))
        self._g_fragility = _GaugeRow(_("analysis.gauge_frag"))
        self._g_support   = _GaugeRow(_("analysis.gauge_supp"))
        g_layout.addWidget(self._g_overhangs)
        g_layout.addWidget(self._g_stability)
        g_layout.addWidget(self._g_fragility)
        g_layout.addWidget(self._g_support)
        root.addWidget(gauges)

        self._g_overhangs.setToolTip(_("analysis.tip_oh"))
        self._g_stability.setToolTip(_("analysis.tip_stab"))
        self._g_fragility.setToolTip(_("analysis.tip_frag"))
        self._g_support.setToolTip(_("analysis.tip_supp"))

        # ── Données dimensionnelles ────────────────────────────────────────
        self._geo_box = geo = QWidget()
        geo.setStyleSheet(f"background: {_pi['BG_SURFACE']}; border-radius: 3px;")
        geo_layout = QHBoxLayout(geo)
        geo_layout.setContentsMargins(10, 6, 10, 6)
        geo_layout.setSpacing(0)

        self._geo: dict[str, QLabel] = {}
        self._geo_keys: list[QLabel] = []
        self._geo_seps: list[QFrame] = []
        fields = [
            (_("analysis.dim_x"), _("analysis.default_val")),
            (_("analysis.dim_y"), _("analysis.default_val")),
            (_("analysis.dim_z"), _("analysis.default_val")),
            (_("analysis.vol"),   _("analysis.default_val")),
            (_("analysis.faces"), _("analysis.default_val")),
        ]
        _dim_keys = ["X", "Y", "Z", "VOL", "FACES"]
        for i, (key_lbl, default) in enumerate(fields):
            col = QVBoxLayout()
            col.setSpacing(1)
            lbl_k = QLabel(key_lbl)
            lbl_k.setFont(QFont("Segoe UI", 6, QFont.Bold))
            lbl_k.setStyleSheet(f"color: {_pi['TEXT_LABEL']}; letter-spacing: 1px; background: transparent;")
            lbl_k.setAlignment(Qt.AlignCenter)
            self._geo_keys.append(lbl_k)
            lbl_v = QLabel(default)
            lbl_v.setFont(QFont(FONT_MONO, 8))
            lbl_v.setStyleSheet(f"color: {_pi['INACTIVE']}; background: transparent;")
            lbl_v.setAlignment(Qt.AlignCenter)
            lbl_v.setWordWrap(True)
            col.addWidget(lbl_k)
            col.addWidget(lbl_v)
            geo_layout.addLayout(col, 1)
            if i < len(fields) - 1:
                vsep = QFrame()
                vsep.setFrameShape(QFrame.VLine)
                vsep.setStyleSheet(f"color: {_pi['INACTIVE']}")
                self._geo_seps.append(vsep)
                geo_layout.addWidget(vsep)
            self._geo[_dim_keys[i]] = lbl_v

        root.addWidget(geo)

        # ── Bloc status : verdict + infos condensées ───────────────────────
        self._status_block = QLabel()
        self._status_block.setFont(QFont(FONT_MONO, 8))
        self._status_block.setTextFormat(Qt.RichText)
        self._status_block.setWordWrap(True)
        self._status_block.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._status_block.setContentsMargins(0, 0, 0, 0)
        self._status_block.setStyleSheet("background: transparent;")
        root.addWidget(self._status_block)

        # ── Bouton : appliquer l'orientation optimale ──────────────────────
        self._orient_btn = QPushButton(_("analysis.orient_btn"))
        self._orient_btn.setFont(QFont("Segoe UI", 8, QFont.Bold))
        self._orient_btn.setFixedHeight(26)
        self._orient_btn.setCursor(Qt.PointingHandCursor)
        self._orient_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {_pi["ACCENT"]};
                border: 1px solid {_pi["ACCENT"]};
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

        # ── Alertes matériau ───────────────────────────────────────────────
        self._material_warn = QLabel()
        self._material_warn.setFont(QFont(FONT_MONO, 7))
        self._material_warn.setWordWrap(True)
        self._material_warn.setContentsMargins(0, 0, 0, 0)
        self._material_warn.setStyleSheet("background: transparent;")
        root.addWidget(self._material_warn)

    # ── API publique ───────────────────────────────────────────────────────

    def update_from_report(self, report: AnalysisReport):
        self._last_report = report
        self._dot_stl.set_active()
        self._dot_anlys.set_active()

        oh_sev = report.overhang_severity
        self._g_overhangs.set_value(oh_sev,
                                     f"{int(oh_sev*100)}%",
                                     color_score=1.0 - oh_sev)
        self._g_stability.set_value(report.stability_score,
                                     f"{int(report.stability_score*100)}%")
        frag_sev = getattr(report, "fragility_severity", 1.0 if report.has_fragile_zones else 0.0)
        self._g_fragility.set_value(frag_sev, f"{int(frag_sev * 100)}%", color_score=1.0 - frag_sev)
        self._g_support.set_value(report.estimated_support_ratio,
                                   f"{int(report.estimated_support_ratio*100)}%",
                                   color_score=1.0 - report.estimated_support_ratio)

        bb = report.bounding_box_mm
        self._set_geo("X",     f"{bb[0]:.0f}mm",  active=True)
        self._set_geo("Y",     f"{bb[1]:.0f}mm",  active=True)
        self._set_geo("Z",     f"{bb[2]:.0f}mm",  active=True)
        self._set_geo("VOL",   f"{report.volume_cm3:.1f}cm³", active=True)
        fc = report.face_count
        faces_str = f"{fc//1000}k" if fc >= 1000 else str(fc)
        self._set_geo("FACES", faces_str, active=True)

        complexity = report.overall_complexity
        _apal = _T.palette()
        _is_dk = _T.is_dark()
        _tg = _apal['TELE_GREEN']; _am = _apal['AMBER']; _er = _apal['ERROR_RED']
        _ab = _apal['ACCENT_BRIGHT']
        if complexity < 0.25 and not report.support_needed:
            verdict_text   = _("analysis.verdict_ok")
            verdict_color  = _tg
            verdict_bg     = "#0B1E14" if _is_dk else "#eef8f2"
            verdict_border = _tg
        elif complexity < 0.55 or (report.support_needed and complexity < 0.6):
            verdict_text   = _("analysis.verdict_warn")
            verdict_color  = _am
            verdict_bg     = "#1E1800" if _is_dk else "#fdf4ed"
            verdict_border = _am
        else:
            verdict_text   = _("analysis.verdict_bad")
            verdict_color  = _er
            verdict_bg     = "#200A0A" if _is_dk else "#faefee"
            verdict_border = _er

        rows = []
        oh_sev = report.overhang_severity
        ovh_pct = int(oh_sev * 100)
        has_floating = getattr(report, "has_floating_regions", False)

        if has_floating:
            rows.append(f'<span style="color:{_er};">{_("analysis.status_floating")}</span>')
        elif report.support_needed:
            rows.append(f'<span style="color:{_er};">{_("analysis.status_supp_req", pct=ovh_pct)}</span>')
        elif oh_sev > 0.15:
            rows.append(f'<span style="color:{_am};">{_("analysis.status_supp_mod", pct=ovh_pct)}</span>')
        else:
            rows.append(f'<span style="color:{_tg};">{_("analysis.status_oh_ok")}</span>')

        if report.stability_score < 0.4:
            rows.append(f'<span style="color:{_er};">{_("analysis.status_stab_low")}</span>')
        elif report.stability_score < 0.65:
            rows.append(f'<span style="color:{_am};">{_("analysis.status_stab_med")}</span>')
        else:
            rows.append(f'<span style="color:{_tg};">{_("analysis.status_stab_ok")}</span>')

        if report.has_fragile_zones:
            rows.append(
                f'<span style="color:{_am};">'
                + _("analysis.status_frag",
                     min_t=f"{report.min_wall_thickness_mm:.1f}",
                     rec_t=f"{report.nozzle_diameter_mm * 3.0:.1f}")
                + '</span>'
            )

        if report.is_large_flat_part:
            rows.append(f'<span style="color:{_am};">{_("analysis.status_flat")}</span>')

        orient_label = report.orientation_label
        improvement = getattr(report, "orientation_improvement_pct", 0.0)
        if orient_label and orient_label != "Actuelle (Z+)" and improvement > 22.0:
            rows.append(
                f'<span style="color:{_ab};">'
                + _("analysis.status_orient", label=orient_label, imp=improvement)
                + '</span>'
            )
            self._orient_btn.setText(_("analysis.orient_apply_fmt", label=orient_label, imp=improvement))
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
            f'<tr><td colspan="2" bgcolor="{_apal["BG_SURFACE"]}" style="padding:6px 8px;">'
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
        self.set_progress(0, _("analysis.progress_init"))
        self._material_warn.setText("")
        self._material_warn.setStyleSheet("background: transparent;")

    def set_progress(self, pct: int, msg: str) -> None:
        """Affiche la progression en temps réel pendant l'analyse."""
        _pp = _T.palette()
        html = (
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr>'
            f'<td style="color:{_pp["TEXT_LABEL"]}; font-family:{FONT_MONO}; font-size:7pt;">'
            f'◌&nbsp;{_("analysis.loading_label")}</td>'
            f'<td align="right" style="color:{_pp["ACCENT"]}; font-family:{FONT_MONO}; '
            f'font-size:9pt; font-weight:bold;">{pct}%</td>'
            f'</tr>'
            f'<tr><td colspan="2" style="color:{_pp["TEXT_SECONDARY"]}; font-family:{FONT_MONO}; '
            f'font-size:7pt; padding-top:3px;">{msg}</td></tr>'
            f'</table>'
        )
        self._status_block.setText(html)

    def _set_geo(self, key: str, value: str, active: bool = False):
        if key in self._geo:
            color = _T.palette()['TELE_GREEN'] if active else _T.palette()['INACTIVE']
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
        self._orient_btn.hide()

    def hide_orient_btn(self) -> None:
        self._orient_btn.hide()

    def reset_orientation_state(self, orient_label: str = "", improvement: float = 0.0) -> None:
        if orient_label and orient_label != "Actuelle (Z+)" and improvement > 22.0:
            self._orient_btn.setText(_("analysis.orient_apply_fmt", label=orient_label, imp=improvement))
            self._orient_btn.show()

    def reset(self):
        self._dot_stl.set_inactive()
        self._dot_anlys.set_inactive()
        self._dot_gen.set_inactive()
        for g in (self._g_overhangs, self._g_stability, self._g_fragility, self._g_support):
            g.reset()
        for key in list(self._geo.keys()):
            self._set_geo(key, _("analysis.default_val"), active=False)
        self._status_block.setText("")
        self._material_warn.setText("")
        self._material_warn.setStyleSheet("background: transparent;")
        self._orient_btn.hide()
