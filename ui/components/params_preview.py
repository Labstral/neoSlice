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
    FONT_MONO, FONT_MAIN,
)
from core.parameters.print_config import PrintConfig
from core.geometry.analysis_report import AnalysisReport


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
        self._btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_ELEVATED};
                border: none;
                border-left: 3px solid {ACCENT};
                color: {ACCENT_BRIGHT};
                text-align: left;
                padding: 0 10px;
                font-family: 'Segoe UI';
                font-size: 8px;
                font-weight: bold;
                letter-spacing: 2px;
            }}
            QPushButton:hover {{
                background: {BG_SURFACE};
                border-left: 3px solid {ACCENT_BRIGHT};
            }}
        """)
        self._update_header()

        self._content = QWidget()
        self._content.setStyleSheet(f"background: {BG_PANEL};")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._content.setMaximumHeight(16777215)  # ouvert par défaut

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
        bg = BG_SURFACE if self._row_count % 2 == 0 else BG_PANEL
        row.setStyleSheet(f"background: {bg};")

        hl = QHBoxLayout(row)
        hl.setContentsMargins(12, 4, 12, 4)
        hl.setSpacing(8)

        lbl_n = QLabel(name)
        lbl_n.setFont(QFont(FONT_MONO, 8))
        lbl_n.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        lbl_n.setWordWrap(True)
        lbl_n.setMinimumWidth(0)

        lbl_v = QLabel(value)
        lbl_v.setFont(QFont(FONT_MONO, 8))
        lbl_v.setStyleSheet(f"color: {TELE_GREEN}; background: transparent;")
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
        vl = QVBoxLayout(self)
        vl.setAlignment(Qt.AlignCenter)
        vl.setSpacing(10)
        vl.setContentsMargins(24, 40, 24, 40)

        icon = QLabel("⬡")
        icon.setFont(QFont("Segoe UI", 32))
        icon.setStyleSheet(f"color: {INACTIVE};")
        icon.setAlignment(Qt.AlignCenter)
        vl.addWidget(icon)

        title = QLabel("AUCUN PARAMÈTRE GÉNÉRÉ")
        title.setFont(QFont("Segoe UI", 9, QFont.Bold))
        title.setStyleSheet(f"color: {TEXT_LABEL}; letter-spacing: 2px;")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        vl.addWidget(title)

        desc = QLabel(
            "Importez un fichier STL\n"
            "puis décrivez votre intention\n"
            "pour générer la configuration."
        )
        desc.setFont(QFont(FONT_MONO, 8))
        desc.setStyleSheet(f"color: {INACTIVE};")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        vl.addWidget(desc)


# ── ParamsPreview principal ────────────────────────────────────────────────

class ParamsPreview(QWidget):
    """Panneau droit — paramètres générés avec sections collapsibles."""

    export_requested = Signal()  # conservé pour compatibilité

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {BG_PANEL};")
        self._sections: dict[str, CollapsibleSection] = {}
        self._setup_ui()

    def _setup_ui(self):
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(0)

        # État vide (visible par défaut)
        self._empty = _EmptyState()
        self._root.addWidget(self._empty)

        # Zone sections (cachée jusqu'à la première génération)
        self._sections_widget = QWidget()
        self._sections_widget.setStyleSheet(f"background: {BG_PANEL};")
        self._sections_layout = QVBoxLayout(self._sections_widget)
        self._sections_layout.setContentsMargins(0, 0, 0, 0)
        self._sections_layout.setSpacing(1)
        self._sections_widget.hide()
        self._root.addWidget(self._sections_widget)

        self._root.addStretch()

    # ── API publique ───────────────────────────────────────────────────────

    def update_from_config(self, config: PrintConfig, analysis: AnalysisReport | None = None):
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
        self._sections_widget.hide()
        self._empty.show()

    # ── Rendu des sections ─────────────────────────────────────────────────

    def _render_summary(self, c: PrintConfig, a: AnalysisReport | None):
        """Carte de résumé en langage humain, ajoutée en tête des sections."""
        lh = c.layer_height
        if lh <= 0.10:
            quality_name = f"Ultra Fine ({lh} mm)"
        elif lh <= 0.14:
            quality_name = f"Fine ({lh} mm)"
        elif lh <= 0.22:
            quality_name = f"Standard ({lh} mm)"
        else:
            quality_name = f"Brouillon ({lh} mm)"

        density = c.infill_density
        if density <= 10:
            fill_name = f"Léger — {density} %"
        elif density <= 25:
            fill_name = f"Standard — {density} %"
        elif density <= 50:
            fill_name = f"Renforcé — {density} %"
        else:
            fill_name = f"Très dense — {density} %"

        if c.brim_type == "no_brim" or c.brim_width == 0:
            adhesion_name = "Sans brim"
        else:
            adhesion_name = f"Brim {c.brim_width:.0f} mm"

        card = QWidget(self._sections_widget)
        card.setStyleSheet(
            f"background: {BG_ELEVATED}; border-left: 3px solid {ACCENT}; border-radius: 3px;"
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(5)

        header = QLabel("EN RÉSUMÉ")
        header.setFont(QFont("Segoe UI", 7, QFont.Bold))
        header.setStyleSheet(f"color: {ACCENT_BRIGHT}; letter-spacing: 2px; background: transparent;")
        cl.addWidget(header)

        support_name = "Sans support"
        if c.support_type != "none" and "support_type" in c.model_fields_set:
            support_name = "Supports arborescents" if "tree" in c.support_type else "Supports normaux"

        temp_name = ""
        if "nozzle_temperature" in c.model_fields_set:
            temp_name = f"{c.nozzle_temperature}°C buse / {c.bed_temperature}°C plateau"

        summary_rows = [
            ("Qualité d'impression", quality_name),
            ("Solidité / remplissage", fill_name),
            ("Adhérence plateau", adhesion_name),
            ("Supports", support_name),
        ]
        if temp_name:
            summary_rows.append(("Températures", temp_name))

        if a and a.volume_cm3 > 0:
            height_mm = a.bounding_box_mm[2] if len(a.bounding_box_mm) > 2 else 20.0
            sup_ratio = getattr(a, "estimated_support_ratio", 0.0) if getattr(a, "support_needed", False) else 0.0
            est_min = c.estimated_time_minutes(a.volume_cm3, height_mm, support_ratio=sup_ratio)
            h, m = divmod(int(est_min), 60)
            time_str = f"~{h}h{m:02d}" if h > 0 else f"~{m} min"
            fil_g = c.estimated_filament_g(a.volume_cm3)
            summary_rows.insert(0, ("Temps estimé", time_str))
            summary_rows.insert(1, ("Filament estimé", f"~{fil_g:.0f} g"))

        for label, value in summary_rows:
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(8)
            lbl_k = QLabel(label)
            lbl_k.setFont(QFont("Segoe UI", 8))
            lbl_k.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
            lbl_v = QLabel(value)
            lbl_v.setFont(QFont("Segoe UI", 8, QFont.Bold))
            lbl_v.setStyleSheet(f"color: {TELE_GREEN}; background: transparent;")
            lbl_v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            rl.addWidget(lbl_k, 1)
            rl.addWidget(lbl_v, 0)
            cl.addWidget(row)

        self._sections_layout.addWidget(card)

    def _render_sections(self, c: PrintConfig, a: AnalysisReport | None):
        # Nettoyer sections précédentes
        while self._sections_layout.count():
            item = self._sections_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._sections.clear()

        # ── Résumé lisible ──
        self._render_summary(c, a)

        # ── MISSION PROFILE ──
        s = self._add_section("MISSION PROFILE")
        name = c.neoslice_profile_name.replace("_", " ").upper()
        s.add_row("PROFIL", name)
        s.add_row("INTENTION", c.neoslice_intent_text[:28] + "…" if len(c.neoslice_intent_text) > 28 else c.neoslice_intent_text)
        s.add_row("CONFIANCE", f"{int(c.neoslice_confidence * 100)} %")

        # ── COUCHES ──
        s = self._add_section("COUCHES")
        s.add_row("HAUTEUR COUCHE",    f"{c.layer_height} mm")
        s.add_row("PREMIÈRE COUCHE",   f"{c.first_layer_height} mm")
        s.add_row("GÉNÉRATEUR PAROI",  c.wall_generator.upper())
        s.add_row("SÉQUENCE PAROI",    c.wall_sequence.upper())

        # ── STRUCTURE ──
        s = self._add_section("STRUCTURE")
        s.add_row("PAROIS",       str(c.wall_loops))
        s.add_row("COQUES SUP.",  str(c.top_shell_layers))
        s.add_row("COQUES INF.",  str(c.bottom_shell_layers))
        s.add_row("PAROI UNIQUE DESSUS", "OUI" if c.top_one_wall_type != "not apply" else "NON")

        # ── REMPLISSAGE ──
        s = self._add_section("REMPLISSAGE")
        s.add_row("DENSITÉ",  f"{c.infill_density} %")
        s.add_row("MOTIF",    c.infill_pattern.upper())
        s.add_row("SURFACE",  c.top_surface_pattern.upper())

        # ── VITESSES ──
        s = self._add_section("VITESSES")
        s.add_row("PAROI EXT.",    f"{c.outer_wall_speed} mm/s")
        s.add_row("PAROI INT.",    f"{c.inner_wall_speed} mm/s")
        s.add_row("REMPLISSAGE",   f"{c.infill_speed} mm/s")
        s.add_row("PREMIÈRE C.",   f"{c.first_layer_speed} mm/s")
        s.add_row("SURFACE SUP.",  f"{c.top_surface_speed} mm/s")
        s.add_row("PONT",          f"{c.bridge_speed} mm/s")

        # ── FINITION ──
        s = self._add_section("FINITION")
        s.add_row("COUTURES",    c.seam_position.upper())
        s.add_row("IRONING",     c.ironing_type.upper())
        if c.ironing_type != "no ironing":
            s.add_row("VITESSE IRON.", f"{c.ironing_speed} mm/s")
            s.add_row("FLUX IRON.",   f"{c.ironing_flow} %")
        s.add_row("COMPENS. ÉLÉP.", f"{c.elefant_foot_compensation} mm")
        s.add_row("COMPENS. XY",    f"{c.xy_contour_compensation} mm")

        # ── ADHÉRENCE (seulement si brim) ──
        if c.brim_type != "no_brim" and c.brim_width > 0:
            s = self._add_section("ADHÉRENCE")
            s.add_row("TYPE BRIM",   c.brim_type.upper())
            s.add_row("LARGEUR",     f"{c.brim_width:.1f} mm")

        # ── MATÉRIAU & MACHINE ──
        fields = c.model_fields_set
        has_mat = "nozzle_temperature" in fields or "bed_temperature" in fields
        has_support = "support_type" in fields and c.support_type != "none"
        has_mode = "enable_prime_tower" in fields or "flush_into_infill" in fields
        if has_mat or has_support or has_mode:
            s = self._add_section("MATÉRIAU & MACHINE")
            if "nozzle_temperature" in fields:
                s.add_row("BUSE",       f"{c.nozzle_temperature} °C")
            if "bed_temperature" in fields:
                s.add_row("PLATEAU",    f"{c.bed_temperature} °C")
            if has_support:
                label = "Arborescents" if "tree" in c.support_type else "Normaux"
                s.add_row("SUPPORTS",   label)
                s.add_row("SEUIL",      f"{c.support_threshold_angle:.0f}°")
                s.add_row("PLATEAU ONLY",
                          "OUI" if c.support_on_build_plate_only else "NON")
            if "enable_prime_tower" in fields and c.enable_prime_tower:
                s.add_row("PRIME TOWER", "ACTIVÉE")
            if "flush_into_infill" in fields and c.flush_into_infill:
                s.add_row("FLUSH AMS",  "INFILL")

        # ── ESTIMATIONS ──
        if a and a.volume_cm3 > 0:
            s = self._add_section("ESTIMATIONS")
            filament_g = c.estimated_filament_g(a.volume_cm3)
            height_mm  = a.bounding_box_mm[2] if len(a.bounding_box_mm) > 2 else 20.0
            sup_ratio  = getattr(a, "estimated_support_ratio", 0.0) if getattr(a, "support_needed", False) else 0.0
            est_min    = c.estimated_time_minutes(a.volume_cm3, height_mm, support_ratio=sup_ratio)
            h, m = divmod(est_min, 60)
            time_str = f"~{h}h{m:02d}" if h > 0 else f"~{m} min"
            s.add_row("FILAMENT EST.", f"~{filament_g:.0f} g")
            s.add_row("TEMPS EST.",    time_str)
            s.add_row("VOLUME PIÈCE",  f"{a.volume_cm3:.1f} cm³")

        self._sections_layout.addStretch()

    def _add_section(self, title: str) -> CollapsibleSection:
        sec = CollapsibleSection(title, self._sections_widget)
        self._sections_layout.addWidget(sec)
        self._sections[title] = sec
        return sec
