from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QColor

from ui.styles.theme import (
    BG_PANEL, BG_SURFACE, BG_ELEVATED, BG_INPUT,
    ACCENT, ACCENT_BRIGHT,
    TELE_GREEN, AMBER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_LABEL, INACTIVE,
    FONT_MONO, FONT_MAIN, MANAGER as _T,
)
from core.parameters.print_config import PrintConfig
from core.geometry.analysis_report import AnalysisReport
from core.i18n import _


# ── Section collapsible animée ─────────────────────────────────────────────

class CollapsibleSection(QWidget):
    """Section collapsible avec animation QPropertyAnimation sur maximumHeight."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._title = title
        self._open = True
        self._row_count = 0

        self._btn = QPushButton()
        self._btn.setCheckable(False)
        self._btn.clicked.connect(self._toggle)
        self._btn.setFixedHeight(28)
        self._btn.setCursor(Qt.PointingHandCursor)
        pal = _T.palette()
        self._btn.setStyleSheet(f"""
            QPushButton {{
                background: {pal["BG_ELEVATED"]};
                border: none;
                border-left: 3px solid {pal["ACCENT"]};
                color: {pal["ACCENT_BRIGHT"]};
                text-align: left;
                padding: 0 10px;
                font-family: {FONT_MAIN};
                font-size: 8px;
                font-weight: bold;
                letter-spacing: 2px;
            }}
            QPushButton:hover {{
                background: {pal["BG_SURFACE"]};
                border-left: 3px solid {pal["ACCENT_BRIGHT"]};
            }}
        """)
        self._update_header()

        self._content = QWidget()
        self._content.setStyleSheet(f"background: {_T.palette()['BG_PANEL']};")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._content.setMaximumHeight(16777215)

        self._anim = QPropertyAnimation(self._content, b"maximumHeight")
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(0, 0, 0, 1)
        vl.setSpacing(0)
        vl.addWidget(self._btn)
        vl.addWidget(self._content)

    def _update_header(self):
        arrow = "▼" if self._open else "▶"
        self._btn.setText(f"  {arrow}   {self._title.upper()}")

    def _toggle(self):
        self._open = not self._open
        self._update_header()
        if self._open:
            self._anim.setStartValue(0)
            self._anim.setEndValue(self._content.sizeHint().height())
        else:
            self._anim.setStartValue(self._content.maximumHeight())
            self._anim.setEndValue(0)
        self._anim.start()

    def add_row(self, name: str, value: str):
        row = QWidget()
        pal = _T.palette()
        bg = pal["BG_SURFACE"] if self._row_count % 2 == 0 else pal["BG_PANEL"]
        row.setStyleSheet(f"background: {bg};")

        hl = QHBoxLayout(row)
        hl.setContentsMargins(12, 4, 12, 4)
        hl.setSpacing(8)

        lbl_n = QLabel(name)
        lbl_n.setFont(QFont(FONT_MONO, 8))
        lbl_n.setStyleSheet(f"color: {_T.palette()['TEXT_SECONDARY']}; background: transparent;")
        lbl_n.setWordWrap(True)
        lbl_n.setMinimumWidth(0)

        lbl_v = QLabel(value)
        lbl_v.setFont(QFont(FONT_MONO, 8))
        lbl_v.setStyleSheet(f"color: {_T.palette()['TELE_GREEN']}; background: transparent;")
        lbl_v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        hl.addWidget(lbl_n, 1)
        hl.addWidget(lbl_v, 0)

        self._content_layout.addWidget(row)
        self._row_count += 1

    def clear_rows(self):
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._row_count = 0


# ── Empty state ────────────────────────────────────────────────────────────

class _EmptyState(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        vl = QVBoxLayout(self)
        vl.setAlignment(Qt.AlignCenter)
        vl.setSpacing(10)
        vl.setContentsMargins(24, 40, 24, 40)

        icon = QLabel("⬡")
        icon.setFont(QFont(FONT_MAIN, 32))
        icon.setStyleSheet(f"color: {INACTIVE};")
        icon.setAlignment(Qt.AlignCenter)
        vl.addWidget(icon)

        title = QLabel(_("preview.empty_title"))
        title.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        title.setStyleSheet(f"color: {TEXT_LABEL}; letter-spacing: 2px;")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        vl.addWidget(title)

        desc = QLabel(_("preview.empty_desc"))
        desc.setFont(QFont(FONT_MONO, 8))
        desc.setStyleSheet(f"color: {INACTIVE};")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        vl.addWidget(desc)


# ── ParamsPreview principal ────────────────────────────────────────────────

class ParamsPreview(QWidget):
    """Panneau droit — paramètres générés avec sections collapsibles."""

    export_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {_T.palette()['BG_PANEL']};")
        self._sections: dict[str, CollapsibleSection] = {}
        self._last_config   = None
        self._last_analysis = None
        self._last_explanations: list[dict] = []
        self._explain_visible = False      # volet « ce que neoSlice a amélioré »
        self._explain_box = None
        self._setup_ui()

    def refresh_theme(self):
        pal = _T.palette()
        self.setStyleSheet(f"background: {pal['BG_PANEL']}")
        if hasattr(self, "_sections_widget"):
            self._sections_widget.setStyleSheet(f"background: {pal['BG_PANEL']}")
        if self._last_config is not None:
            self._render_sections(self._last_config, self._last_analysis)
        self.update()

    def _setup_ui(self):
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(0)

        self._empty = _EmptyState()
        self._root.addWidget(self._empty)

        self._sections_widget = QWidget()
        self._sections_widget.setStyleSheet(f"background: {_T.palette()['BG_PANEL']};")
        self._sections_layout = QVBoxLayout(self._sections_widget)
        self._sections_layout.setContentsMargins(0, 0, 0, 0)
        self._sections_layout.setSpacing(1)
        self._sections_widget.hide()
        self._root.addWidget(self._sections_widget)

        self._root.addStretch()

    # ── API publique ───────────────────────────────────────────────────────

    def update_from_config(self, config: PrintConfig, analysis: AnalysisReport | None = None,
                           explanations: list[dict] | None = None):
        self._last_config = config
        self._last_analysis = analysis
        self._last_explanations = explanations or []
        self._explain_visible = False   # replié à chaque nouvelle génération
        self._empty.hide()
        self._sections_widget.show()
        self._render_sections(config, analysis)

    def set_loading(self, loading: bool):
        if loading:
            self._empty.hide()
            self._sections_widget.hide()

    def reset(self):
        while self._sections_layout.count():
            item = self._sections_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._sections.clear()
        self._last_explanations = []
        self._explain_visible = False
        self._explain_box = None
        self._sections_widget.hide()
        self._empty.show()

    # ── Rendu des sections ─────────────────────────────────────────────────

    def _render_summary(self, c: PrintConfig, a: AnalysisReport | None):
        lh = c.layer_height
        if lh <= 0.10:
            quality_name = _("preview.quality_ultra", h=lh)
        elif lh <= 0.14:
            quality_name = _("preview.quality_fine", h=lh)
        elif lh <= 0.22:
            quality_name = _("preview.quality_standard", h=lh)
        else:
            quality_name = _("preview.quality_draft", h=lh)

        density = c.infill_density
        if density <= 10:
            fill_name = _("preview.fill_light", d=density)
        elif density <= 25:
            fill_name = _("preview.fill_standard", d=density)
        elif density <= 50:
            fill_name = _("preview.fill_strong", d=density)
        else:
            fill_name = _("preview.fill_dense", d=density)

        if c.brim_type == "no_brim" or c.brim_width == 0:
            adhesion_name = _("preview.adhesion_none")
        else:
            adhesion_name = _("preview.adhesion_brim", w=c.brim_width)

        _rp = _T.palette()
        card = QWidget(self._sections_widget)
        card.setStyleSheet(
            f"background: {_rp['BG_ELEVATED']}; border-left: 3px solid {_rp['ACCENT']}; border-radius: 3px;"
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(5)

        header_row = QWidget()
        header_row.setStyleSheet("background: transparent;")
        hrl = QHBoxLayout(header_row)
        hrl.setContentsMargins(0, 0, 0, 0)
        hrl.setSpacing(6)
        header = QLabel(_("preview.summary_title"))
        header.setFont(QFont(FONT_MAIN, 7, QFont.Bold))
        header.setStyleSheet(f"color: {_rp['ACCENT_BRIGHT']}; letter-spacing: 2px; background: transparent;")
        hrl.addWidget(header)
        hrl.addStretch()
        # Icône « i » discrète → ouvre le volet « ce que neoSlice a amélioré »
        if self._last_explanations:
            info_btn = QPushButton("i")
            info_btn.setFixedSize(18, 18)
            info_btn.setCursor(Qt.PointingHandCursor)
            info_btn.setToolTip(_("explain.tip"))
            info_btn.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
            info_btn.setStyleSheet(
                f"QPushButton {{ background: {_rp['BG_SURFACE']}; color: {_rp['ACCENT_BRIGHT']}; "
                f"border: 1px solid {_rp['ACCENT']}; border-radius: 9px; }} "
                f"QPushButton:hover {{ background: {_rp['ACCENT']}; color: {_rp['BG_PANEL']}; }}"
            )
            info_btn.clicked.connect(self._toggle_explain)
            hrl.addWidget(info_btn)
        cl.addWidget(header_row)

        mode = getattr(c, "neoslice_support_mode", "auto")
        if mode == "none":
            support_name = _("preview.support_forced_none")
        elif mode == "classic":
            support_name = _("preview.support_classic")
        elif mode == "tree":
            support_name = _("preview.support_tree")
        elif c.support_type != "none":
            support_name = _("preview.support_auto_tree") if "tree" in c.support_type else _("preview.support_auto_normal")
        else:
            support_name = _("preview.support_auto_none")

        temp_name = ""
        if "nozzle_temperature" in c.model_fields_set:
            temp_name = _("preview.temps_fmt", nozzle=c.nozzle_temperature, bed=c.bed_temperature)

        summary_rows = [
            (_("preview.row_quality"),   quality_name),
            (_("preview.row_strength"),  fill_name),
            (_("preview.row_adhesion"),  adhesion_name),
            (_("preview.row_supports"),  support_name),
        ]
        if temp_name:
            summary_rows.append((_("preview.row_temps"), temp_name))

        if a and a.volume_cm3 > 0:
            height_mm = a.bounding_box_mm[2] if len(a.bounding_box_mm) > 2 else 20.0
            sup_ratio = getattr(a, "estimated_support_ratio", 0.0) if getattr(a, "support_needed", False) else 0.0
            est_min = c.estimated_time_minutes(a.volume_cm3, height_mm, support_ratio=sup_ratio)
            h, m = divmod(int(est_min), 60)
            time_str = f"~{h}h{m:02d}" if h > 0 else f"~{m} min"
            fil_g = c.estimated_filament_g(a.volume_cm3, getattr(a, "surface_area_cm2", 0.0))
            summary_rows.insert(0, (_("preview.row_time"),     time_str))
            summary_rows.insert(1, (_("preview.row_filament"), f"~{fil_g:.0f} g"))

        for label, value in summary_rows:
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(8)
            lbl_k = QLabel(label)
            lbl_k.setFont(QFont(FONT_MAIN, 8))
            lbl_k.setStyleSheet(f"color: {_rp['TEXT_SECONDARY']}; background: transparent;")
            lbl_v = QLabel(value)
            lbl_v.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
            lbl_v.setStyleSheet(f"color: {_T.palette()['TELE_GREEN']}; background: transparent;")
            lbl_v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            rl.addWidget(lbl_k, 1)
            rl.addWidget(lbl_v, 0)
            cl.addWidget(row)

        # ── Volet « ce que neoSlice a amélioré » (replié par défaut) ────────
        self._explain_box = None
        if self._last_explanations:
            self._explain_box = self._build_explain_box()
            self._explain_box.setVisible(self._explain_visible)
            cl.addWidget(self._explain_box)

        self._sections_layout.addWidget(card)

    def _toggle_explain(self):
        self._explain_visible = not self._explain_visible
        if self._explain_box is not None:
            self._explain_box.setVisible(self._explain_visible)

    def _build_explain_box(self) -> QWidget:
        """Construit le volet listant les explications pédagogiques."""
        _p = _T.palette()
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 6, 0, 0)
        bl.setSpacing(6)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {_p['INACTIVE']};")
        bl.addWidget(sep)

        hdr = QLabel(_("explain.header"))
        hdr.setFont(QFont(FONT_MAIN, 7, QFont.Bold))
        hdr.setStyleSheet(f"color: {_p['TEXT_LABEL']}; letter-spacing: 2px; background: transparent;")
        bl.addWidget(hdr)

        for e in self._last_explanations:
            bl.addWidget(self._make_explain_row(e))
        return box

    def _make_explain_row(self, e: dict) -> QWidget:
        """Une explication : catégorie + titre + raison, filet accent à gauche."""
        _p = _T.palette()
        row = QWidget()
        row.setStyleSheet(
            f"background: {_p['BG_SURFACE']}; border-left: 2px solid {_p['ACCENT']}; border-radius: 2px;"
        )
        rl = QVBoxLayout(row)
        rl.setContentsMargins(8, 5, 8, 5)
        rl.setSpacing(1)

        cat = QLabel(e.get("cat", ""))
        cat.setFont(QFont(FONT_MAIN, 7, QFont.Bold))
        cat.setStyleSheet(f"color: {_p['ACCENT_BRIGHT']}; letter-spacing: 2px; background: transparent;")
        rl.addWidget(cat)

        titre = QLabel(e.get("titre", ""))
        titre.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
        titre.setStyleSheet(f"color: {_p['TEXT_PRIMARY']}; background: transparent;")
        titre.setWordWrap(True)
        rl.addWidget(titre)

        raison = QLabel(e.get("raison", ""))
        raison.setFont(QFont(FONT_MAIN, 8))
        raison.setStyleSheet(f"color: {_p['TEXT_SECONDARY']}; background: transparent;")
        raison.setWordWrap(True)
        rl.addWidget(raison)
        return row

    def _render_sections(self, c: PrintConfig, a: AnalysisReport | None):
        while self._sections_layout.count():
            item = self._sections_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._sections.clear()

        self._render_summary(c, a)

        s = self._add_section(_("preview.sec_mission"))
        if c.neoslice_printer:
            s.add_row(_("preview.lbl_printer"), c.neoslice_printer)
        name = c.neoslice_profile_name.replace("_", " ").upper()
        s.add_row(_("preview.lbl_profile"),    name)
        s.add_row(_("preview.lbl_intent"),     c.neoslice_intent_text[:28] + "…" if len(c.neoslice_intent_text) > 28 else c.neoslice_intent_text)
        s.add_row(_("preview.lbl_confidence"), f"{int(c.neoslice_confidence * 100)} %")

        s = self._add_section(_("preview.sec_layers"))
        s.add_row(_("preview.lbl_layer_h"),   f"{c.layer_height} mm")
        s.add_row(_("preview.lbl_first_layer"),f"{c.first_layer_height} mm")
        s.add_row(_("preview.lbl_wall_gen"),   c.wall_generator.upper())
        s.add_row(_("preview.lbl_wall_seq"),   c.wall_sequence.upper())

        s = self._add_section(_("preview.sec_structure"))
        s.add_row(_("preview.lbl_walls"),      str(c.wall_loops))
        s.add_row(_("preview.lbl_top_shells"), str(c.top_shell_layers))
        s.add_row(_("preview.lbl_bot_shells"), str(c.bottom_shell_layers))
        s.add_row(_("preview.lbl_single_top"), _("preview.val_yes") if c.top_one_wall_type != "not apply" else _("preview.val_no"))

        s = self._add_section(_("preview.sec_infill"))
        s.add_row(_("preview.lbl_density"), f"{c.infill_density} %")
        s.add_row(_("preview.lbl_pattern"), c.infill_pattern.upper())
        s.add_row(_("preview.lbl_surface"), c.top_surface_pattern.upper())

        s = self._add_section(_("preview.sec_speeds"))
        s.add_row(_("preview.lbl_outer_wall"), f"{c.outer_wall_speed} mm/s")
        s.add_row(_("preview.lbl_inner_wall"), f"{c.inner_wall_speed} mm/s")
        s.add_row(_("preview.lbl_infill"),     f"{c.infill_speed} mm/s")
        s.add_row(_("preview.lbl_first_c"),    f"{c.first_layer_speed} mm/s")
        s.add_row(_("preview.lbl_top_surf"),   f"{c.top_surface_speed} mm/s")
        s.add_row(_("preview.lbl_bridge"),     f"{c.bridge_speed} mm/s")

        s = self._add_section(_("preview.sec_finish"))
        s.add_row(_("preview.lbl_seam"),        c.seam_position.upper())
        s.add_row(_("preview.lbl_ironing"),     c.ironing_type.upper())
        if c.ironing_type != "no ironing":
            s.add_row(_("preview.lbl_iron_speed"), f"{c.ironing_speed} mm/s")
            s.add_row(_("preview.lbl_iron_flow"),  f"{c.ironing_flow} %")
        s.add_row(_("preview.lbl_elep_foot"),   f"{c.elefant_foot_compensation} mm")
        s.add_row(_("preview.lbl_xy_comp"),     f"{c.xy_contour_compensation} mm")

        if c.brim_type != "no_brim" and c.brim_width > 0:
            s = self._add_section(_("preview.sec_adhesion"))
            s.add_row(_("preview.lbl_brim_type"), c.brim_type.upper())
            s.add_row(_("preview.lbl_brim_w"),    f"{c.brim_width:.1f} mm")

        fields = c.model_fields_set
        has_mat = "nozzle_temperature" in fields or "bed_temperature" in fields
        has_support = "support_type" in fields and c.support_type != "none"
        has_mode = "enable_prime_tower" in fields or "flush_into_infill" in fields
        if has_mat or has_support or has_mode:
            s = self._add_section(_("preview.sec_material"))
            if "nozzle_temperature" in fields:
                s.add_row(_("preview.lbl_nozzle"),  f"{c.nozzle_temperature} °C")
            if "bed_temperature" in fields:
                s.add_row(_("preview.lbl_bed"),     f"{c.bed_temperature} °C")
            if has_support:
                label = _("preview.supp_tree") if "tree" in c.support_type else _("preview.supp_classic")
                s.add_row(_("preview.lbl_supports"),  label)
                s.add_row(_("preview.lbl_threshold"), f"{c.support_threshold_angle:.0f}°")
                s.add_row(_("preview.lbl_plate_only"),
                          _("preview.val_yes") if c.support_on_build_plate_only else _("preview.val_no"))
            if "enable_prime_tower" in fields and c.enable_prime_tower:
                s.add_row(_("preview.lbl_prime_tower"), _("preview.val_active"))
            if "flush_into_infill" in fields and c.flush_into_infill:
                s.add_row(_("preview.lbl_flush_ams"), _("preview.val_infill"))

        if a and a.volume_cm3 > 0:
            s = self._add_section(_("preview.sec_estimates"))
            filament_g = c.estimated_filament_g(a.volume_cm3, getattr(a, "surface_area_cm2", 0.0))
            height_mm  = a.bounding_box_mm[2] if len(a.bounding_box_mm) > 2 else 20.0
            sup_ratio  = getattr(a, "estimated_support_ratio", 0.0) if getattr(a, "support_needed", False) else 0.0
            est_min    = c.estimated_time_minutes(a.volume_cm3, height_mm, support_ratio=sup_ratio)
            h, m = divmod(est_min, 60)
            time_str = f"~{h}h{m:02d}" if h > 0 else f"~{m} min"
            s.add_row(_("preview.lbl_filament_est"), f"~{filament_g:.0f} g")
            s.add_row(_("preview.lbl_time_est"),     time_str)
            s.add_row(_("preview.lbl_volume"),       f"{a.volume_cm3:.1f} cm³")

        self._sections_layout.addStretch()

    def _add_section(self, title: str) -> CollapsibleSection:
        sec = CollapsibleSection(title, self._sections_widget)
        self._sections_layout.addWidget(sec)
        self._sections[title] = sec
        return sec
