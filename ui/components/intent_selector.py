"""Sélecteur d'intentions structuré — accords collapsibles + détection de conflits.

Remplace le champ texte libre. Chaque groupe est un accordéon avec des choix
exclusifs (un seul par groupe). La détection de conflits inter-groupes est
automatique et propose un compromis quand possible.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QSizePolicy, QInputDialog,
    QScrollArea, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QColor

_PRESETS_FILE = Path.home() / ".neoslice" / "presets.json"


def _load_saved_presets() -> list[dict]:
    try:
        if _PRESETS_FILE.exists():
            return json.loads(_PRESETS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _save_presets_file(presets: list[dict]) -> None:
    _PRESETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PRESETS_FILE.write_text(json.dumps(presets, indent=2, ensure_ascii=False), encoding="utf-8")

from ui.styles.theme import (
    BG_PANEL, BG_SURFACE, BG_ELEVATED, BG_INPUT,
    ACCENT, ACCENT_BRIGHT,
    TELE_GREEN, AMBER, ERROR_RED,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_LABEL, INACTIVE,
    FONT_MONO, FONT_MAIN,
)
from core.intent.intent_profiles import IntentProfile


# ── Données de configuration ───────────────────────────────────────────────

@dataclass
class _Preset:
    id: str
    label: str
    desc: str
    intent: dict = field(default_factory=dict)   # IntentProfile field overrides
    config: dict = field(default_factory=dict)   # PrintConfig direct overrides


@dataclass
class SelectionResult:
    """Résultat de la sélection transmis à MainWindow."""
    intent_profile: IntentProfile
    config_overrides: dict
    selected_labels: list[str]
    human_summary: str


# ── Définition des groupes et presets ──────────────────────────────────────

_GROUPS: list[tuple[str, list[_Preset]]] = [
    ("QUALITÉ", [
        _Preset("quality_draft",  "Brouillon",    "0.28mm — prototype uniquement",
                intent={"speed": 0.9, "quality": 0.05}),
        _Preset("quality_std",    "Standard",     "0.20mm — équilibre vitesse / qualité",
                intent={}),
        _Preset("quality_fine",   "Fine",         "0.12mm — bonne finition de surface",
                intent={"quality": 0.8}),
        _Preset("quality_ultra",  "Ultra Fine",   "0.08mm — finition maximale, lent",
                intent={"quality": 1.0, "surface_finish": 0.8}),
    ]),
    ("RÉSISTANCE", [
        _Preset("strength_light", "Légère",       "Parois minimales, économie de matière",
                intent={"strength": 0.05, "filament_saving": 0.9}),
        _Preset("strength_std",   "Standard",     "Solidité normale pour usage courant",
                intent={}),
        _Preset("strength_high",  "Renforcée",    "Parois + infill augmentés (cubic)",
                intent={"strength": 0.75}),
        _Preset("strength_ultra", "Ultra Solide", "Résistance maximale — gyroid 80%",
                intent={"strength": 1.0}),
    ]),
    ("VITESSE", [
        _Preset("speed_std",   "Standard",     "Vitesses Bambu Lab recommandées",
                intent={}),
        _Preset("speed_high",  "Rapide",       "+50% vitesse — qualité légèrement réduite",
                intent={"speed": 0.75}),
        _Preset("speed_ultra", "Ultra Rapide", "Vitesse maximale — prototype seulement",
                intent={"speed": 1.0}),
    ]),
    ("ADHÉRENCE", [
        _Preset("brim_none",  "Aucune",       "Pas de brim — pièce stable uniquement",
                config={"brim_type": "no_brim", "brim_width": 0.0}),
        _Preset("brim_std",   "Brim 5mm",     "Brim standard — stabilité modérée",
                config={"brim_type": "outer_only", "brim_width": 5.0}),
        _Preset("brim_large", "Brim 10mm",    "Brim large — pièces hautes ou fragiles",
                config={"brim_type": "outer_only", "brim_width": 10.0}),
    ]),
    ("USAGE", [
        _Preset("usage_indoor",   "Intérieur standard", "Paramètres PLA optimaux",
                intent={}),
        _Preset("usage_outdoor",  "Extérieur / UV",     "Gyroid renforcé, températures PETG/ASA",
                intent={"outdoor_resistance": 1.0}),
        _Preset("usage_visible",  "Finition visible",   "Ironing, coutures dans le dos",
                intent={"surface_finish": 0.9}),
        _Preset("usage_precise",  "Assemblage précis",  "Arachne + compensation XY serrée",
                intent={"precision": 0.9}),
    ]),
    ("MODE", [
        _Preset("mode_normal",     "Standard",           "Aucun mode spécial",
                intent={}),
        _Preset("mode_silent",     "Silencieux",         "Vitesses -40% — impression discrète",
                intent={"silent": 0.9}),
        _Preset("mode_multicolor", "Multicolore (AMS)",  "Prime tower + flush optimisé",
                intent={"multicolor": 0.9}),
    ]),
]

# ── Règles de conflit inter-groupes ────────────────────────────────────────
# (id1, id2, sévérité, message, compromis)

_CONFLICTS: list[tuple[str, str, str, str, str]] = [
    ("quality_ultra", "speed_ultra", "error",
     "Ultra Fine + Ultra Rapide sont incompatibles — la qualité sera celle du Brouillon.",
     "Essayez : Fine + Rapide  ou  Standard + Ultra Rapide"),

    ("quality_ultra", "speed_high", "warning",
     "Ultra Fine avec vitesse Rapide peut dégrader légèrement la finition.",
     "Compromis : Fine + Rapide pour un bon équilibre"),

    ("quality_fine", "speed_ultra", "warning",
     "Fine + Ultra Rapide donnera effectivement une qualité Standard.",
     "Compromis : Fine + Rapide  ou  Standard + Ultra Rapide"),

    ("strength_ultra", "speed_ultra", "error",
     "Ultra Solide + Ultra Rapide sont incompatibles — les parois épaisses ont besoin de temps.",
     "Essayez : Renforcée + Rapide  ou  Ultra Solide + Standard"),

    ("strength_ultra", "strength_light", "error",
     "Ultra Solide et Légère sont contradictoires.",
     "Choisissez l'un ou l'autre selon votre besoin"),

    ("strength_light", "usage_outdoor", "warning",
     "Une pièce Légère est déconseillée pour un usage extérieur.",
     "Recommandé : Standard ou Renforcée + Extérieur"),

    ("quality_draft", "usage_visible", "warning",
     "Brouillon + Finition visible : la résolution 0.28mm ne donnera pas une belle finition.",
     "Utilisez au minimum la qualité Standard pour une pièce visible"),

    ("speed_ultra", "usage_visible", "warning",
     "Ultra Rapide dégrade les coutures et la finition de surface.",
     "Recommandé : Standard ou Rapide pour une pièce visible"),
]


def _get_preset_by_id(preset_id: str) -> _Preset | None:
    for _, presets in _GROUPS:
        for p in presets:
            if p.id == preset_id:
                return p
    return None


def _check_conflicts(selected_ids: set[str]) -> list[tuple[str, str, str, str]]:
    """Retourne la liste des conflits actifs : (sévérité, message, compromis)."""
    found = []
    for id1, id2, severity, msg, compromise in _CONFLICTS:
        if id1 in selected_ids and id2 in selected_ids:
            found.append((severity, msg, compromise))
    return found


def _build_intent_profile(selected_ids: set[str]) -> IntentProfile:
    """Fusionne les intent_overrides de tous les presets sélectionnés."""
    merged: dict[str, float] = {
        "strength": 0.0, "speed": 0.0, "quality": 0.0,
        "filament_saving": 0.0, "outdoor_resistance": 0.0, "surface_finish": 0.0,
        "precision": 0.0, "silent": 0.0, "multicolor": 0.0,
    }
    for pid in selected_ids:
        p = _get_preset_by_id(pid)
        if p:
            for k, v in p.intent.items():
                merged[k] = max(merged.get(k, 0.0), v)

    return IntentProfile(**merged)


def _build_config_overrides(selected_ids: set[str]) -> dict:
    """Fusionne les config overrides directs (dernier sélectionné gagne par groupe)."""
    overrides: dict = {}
    for pid in selected_ids:
        p = _get_preset_by_id(pid)
        if p:
            overrides.update(p.config)
    return overrides


# ── Widget bouton de choix ─────────────────────────────────────────────────

class _ChoiceBtn(QWidget):
    """Carte cliquable représentant un preset dans un groupe."""

    clicked = Signal(str)  # émet l'id du preset

    def __init__(self, preset: _Preset, parent=None):
        super().__init__(parent)
        self._preset = preset
        self._selected = False
        self.setCursor(Qt.PointingHandCursor)
        self._setup_ui()
        self._apply_style()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(10)

        left = QVBoxLayout()
        left.setSpacing(2)

        self._title_lbl = QLabel(self._preset.label)
        self._title_lbl.setFont(QFont("Segoe UI", 9, QFont.Bold))

        self._desc_lbl = QLabel(self._preset.desc)
        self._desc_lbl.setFont(QFont(FONT_MONO, 7))
        self._desc_lbl.setWordWrap(True)

        left.addWidget(self._title_lbl)
        left.addWidget(self._desc_lbl)
        layout.addLayout(left, 1)

        self._check = QLabel()
        self._check.setFont(QFont("Segoe UI", 10))
        self._check.setFixedWidth(20)
        self._check.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._check)

    def _apply_style(self):
        if self._selected:
            self.setStyleSheet(f"""
                _ChoiceBtn, QWidget {{
                    background: {BG_ELEVATED};
                    border-left: 3px solid {TELE_GREEN};
                    border-radius: 2px;
                }}
            """)
            self._title_lbl.setStyleSheet(f"color: {TELE_GREEN}; background: transparent;")
            self._desc_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
            self._check.setText("✓")
            self._check.setStyleSheet(f"color: {TELE_GREEN}; background: transparent;")
        else:
            self.setStyleSheet(f"""
                _ChoiceBtn, QWidget {{
                    background: {BG_SURFACE};
                    border-left: 3px solid transparent;
                    border-radius: 2px;
                }}
                _ChoiceBtn:hover, QWidget:hover {{
                    background: {BG_ELEVATED};
                    border-left: 3px solid {INACTIVE};
                }}
            """)
            self._title_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
            self._desc_lbl.setStyleSheet(f"color: {TEXT_LABEL}; background: transparent;")
            self._check.setText("")
            self._check.setStyleSheet("background: transparent;")

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._preset.id)

    def enterEvent(self, event):
        if not self._selected:
            self.setStyleSheet(f"""
                QWidget {{ background: {BG_ELEVATED}; border-left: 3px solid {INACTIVE}; border-radius: 2px; }}
            """)
            self._title_lbl.setStyleSheet(f"color: {ACCENT_BRIGHT}; background: transparent;")
            self._desc_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")

    def leaveEvent(self, event):
        if not self._selected:
            self._apply_style()


# ── Groupe accordéon ───────────────────────────────────────────────────────

class _Group(QWidget):
    """Groupe collapsible avec choix exclusifs (radio style)."""

    selection_changed = Signal()

    def __init__(self, title: str, presets: list[_Preset], start_open: bool = False, parent=None):
        super().__init__(parent)
        self._title = title
        self._presets = presets
        self._open = start_open
        self._selected_id: str | None = None
        self._buttons: dict[str, _ChoiceBtn] = {}
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        arrow = "▼" if self._open else "▶"
        self._header = QPushButton(f"  {arrow}   {self._title}")
        self._header.setFixedHeight(30)
        self._header.setCursor(Qt.PointingHandCursor)
        self._header.setStyleSheet(f"""
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
        self._header.clicked.connect(self._toggle)
        root.addWidget(self._header)

        self._content = QWidget()
        self._content.setStyleSheet(f"background: {BG_PANEL};")
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 1, 0, 1)
        content_layout.setSpacing(1)

        for p in self._presets:
            btn = _ChoiceBtn(p, self._content)
            btn.clicked.connect(self._on_choice)
            self._buttons[p.id] = btn
            content_layout.addWidget(btn)

        self._anim = QPropertyAnimation(self._content, b"maximumHeight")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._content.setMaximumHeight(16777215 if self._open else 0)
        root.addWidget(self._content)

    def _toggle(self):
        self._open = not self._open
        arrow = "▼" if self._open else "▶"
        self._header.setText(f"  {arrow}   {self._title}")
        if self._open:
            # Lever la contrainte pour que sizeHint() soit calculé correctement
            self._content.setMaximumHeight(16777215)
            target_h = self._content.sizeHint().height()
            # Fallback si sizeHint() n'est pas encore calculé (widget pas encore affiché)
            if target_h <= 0:
                target_h = len(self._presets) * 58
            self._content.setMaximumHeight(0)
            self._anim.setStartValue(0)
            self._anim.setEndValue(target_h)
        else:
            self._anim.setStartValue(self._content.maximumHeight())
            self._anim.setEndValue(0)
        self._anim.start()

    def _on_choice(self, preset_id: str):
        if self._selected_id == preset_id:
            # Déselectionner
            self._buttons[preset_id].set_selected(False)
            self._selected_id = None
        else:
            if self._selected_id and self._selected_id in self._buttons:
                self._buttons[self._selected_id].set_selected(False)
            self._selected_id = preset_id
            self._buttons[preset_id].set_selected(True)
        self.selection_changed.emit()

    def select_preset(self, preset_id: str):
        """Sélectionne un preset sans passer par un clic utilisateur."""
        if preset_id in self._buttons:
            self._on_choice(preset_id)

    def get_selected_id(self) -> str | None:
        return self._selected_id

    def get_selected_label(self) -> str | None:
        if self._selected_id:
            p = _get_preset_by_id(self._selected_id)
            return f"{self._title}: {p.label}" if p else None
        return None

    def mark_conflict(self, has_conflict: bool, severity: str = "warning"):
        if has_conflict:
            color = ERROR_RED if severity == "error" else AMBER
            self._header.setStyleSheet(self._header.styleSheet().replace(
                f"border-left: 3px solid {ACCENT};",
                f"border-left: 3px solid {color};",
            ))
        else:
            # Reset style
            self._header.setStyleSheet(f"""
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


# ── Bannière de conflit ────────────────────────────────────────────────────

class _ConflictBanner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        self._icon_msg = QLabel()
        self._icon_msg.setFont(QFont("Segoe UI", 8, QFont.Bold))
        self._icon_msg.setWordWrap(True)

        self._compromise = QLabel()
        self._compromise.setFont(QFont("Segoe UI", 8, QFont.Bold))
        self._compromise.setStyleSheet(f"color: {TEXT_SECONDARY};")
        self._compromise.setWordWrap(True)

        layout.addWidget(self._icon_msg)
        layout.addWidget(self._compromise)
        self.hide()

    def show_conflicts(self, conflicts: list[tuple[str, str, str]]):
        if not conflicts:
            self.hide()
            return

        # Prendre le conflit le plus sévère
        errors = [c for c in conflicts if c[0] == "error"]
        warnings = [c for c in conflicts if c[0] == "warning"]
        worst = errors[0] if errors else warnings[0]

        severity, msg, compromise = worst
        if severity == "error":
            self.setStyleSheet(f"""
                QWidget {{ background: rgba(255,59,59,0.12); border: 1px solid {ERROR_RED};
                border-radius: 3px; }}
            """)
            self._icon_msg.setText(f"⛔  {msg}")
            self._icon_msg.setStyleSheet(f"color: {ERROR_RED}; background: transparent;")
        else:
            self.setStyleSheet(f"""
                QWidget {{ background: rgba(255,184,0,0.10); border: 1px solid {AMBER};
                border-radius: 3px; }}
            """)
            self._icon_msg.setText(f"⚠  {msg}")
            self._icon_msg.setStyleSheet(f"color: {AMBER}; background: transparent;")

        # Afficher tous les compromis
        all_compromises = [c[2] for c in conflicts if c[2]]
        comp_color = ERROR_RED if errors else AMBER
        self._compromise.setText("\n".join(f"→  {c}" for c in all_compromises[:2]))
        self._compromise.setStyleSheet(f"color: {comp_color}; background: transparent; font-weight: bold;")
        self.show()


# ── Chip de préset sauvegardé ──────────────────────────────────────────────

class _PresetChip(QWidget):
    load_requested   = Signal()
    delete_requested = Signal(int)

    def __init__(self, name: str, idx: int, parent=None):
        super().__init__(parent)
        self._idx = idx
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 4, 3)
        layout.setSpacing(4)
        self.setStyleSheet(f"background: {BG_SURFACE}; border-radius: 3px;")

        lbl = QPushButton(name)
        lbl.setFont(QFont(FONT_MONO, 7))
        lbl.setStyleSheet(f"""
            QPushButton {{ color: {ACCENT_BRIGHT}; background: transparent; border: none; text-align: left; }}
            QPushButton:hover {{ color: {TEXT_PRIMARY}; }}
        """)
        lbl.setCursor(Qt.PointingHandCursor)
        lbl.clicked.connect(self.load_requested)
        layout.addWidget(lbl)

        del_btn = QPushButton("✕")
        del_btn.setFont(QFont(FONT_MONO, 7))
        del_btn.setFixedSize(14, 14)
        del_btn.setStyleSheet(f"""
            QPushButton {{ color: {INACTIVE}; background: transparent; border: none; }}
            QPushButton:hover {{ color: {ERROR_RED}; }}
        """)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._idx))
        layout.addWidget(del_btn)


# ── Composant principal ────────────────────────────────────────────────────

class IntentSelector(QWidget):
    """Sélecteur d'intentions par presets accordéon."""

    intent_submitted = Signal(object)  # émet un SelectionResult

    def __init__(self, parent=None):
        super().__init__(parent)
        self._groups: list[_Group] = []
        self._is_locked = True
        self._setup_ui()
        self._apply_lock(True)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(1)

        # Bandeau de verrouillage (affiché avant chargement du STL)
        self._lock_banner = QWidget()
        self._lock_banner.setStyleSheet(
            f"background: rgba(26,53,80,0.6); border-radius: 2px;"
        )
        banner_layout = QVBoxLayout(self._lock_banner)
        banner_layout.setContentsMargins(10, 10, 10, 10)
        banner_layout.setSpacing(4)

        lock_icon = QLabel("⊘")
        lock_icon.setFont(QFont("Segoe UI", 18))
        lock_icon.setAlignment(Qt.AlignCenter)
        lock_icon.setStyleSheet(f"color: {INACTIVE}; background: transparent;")
        banner_layout.addWidget(lock_icon)

        lock_msg = QLabel("Chargez un fichier STL\npour accéder aux réglages")
        lock_msg.setFont(QFont(FONT_MONO, 8))
        lock_msg.setAlignment(Qt.AlignCenter)
        lock_msg.setStyleSheet(f"color: {INACTIVE}; background: transparent;")
        lock_msg.setWordWrap(True)
        banner_layout.addWidget(lock_msg)

        lock_step = QLabel("← Étape ②")
        lock_step.setFont(QFont(FONT_MONO, 7))
        lock_step.setAlignment(Qt.AlignCenter)
        lock_step.setStyleSheet(f"color: {INACTIVE}; background: transparent;")
        banner_layout.addWidget(lock_step)

        root.addWidget(self._lock_banner)

        # ── Section présets sauvegardés ────────────────────────────────────
        self._presets_section = QWidget()
        self._presets_section.setStyleSheet(f"background: {BG_ELEVATED};")
        ps_layout = QVBoxLayout(self._presets_section)
        ps_layout.setContentsMargins(8, 6, 8, 6)
        ps_layout.setSpacing(4)

        ps_header = QLabel("★  MES PRÉSETS")
        ps_header.setFont(QFont("Segoe UI", 7, QFont.Bold))
        ps_header.setStyleSheet(f"color: {ACCENT_BRIGHT}; letter-spacing: 2px;")
        ps_layout.addWidget(ps_header)

        self._presets_chips = QWidget()
        chips_layout = QHBoxLayout(self._presets_chips)
        chips_layout.setContentsMargins(0, 0, 0, 0)
        chips_layout.setSpacing(4)
        chips_layout.addStretch()
        ps_layout.addWidget(self._presets_chips)

        root.addWidget(self._presets_section)
        self._refresh_presets_ui()

        # Bannière auto-sélection
        self._auto_banner = QWidget()
        self._auto_banner.setStyleSheet(
            f"background: rgba(0,255,159,0.07); border-left: 3px solid {TELE_GREEN}; border-radius: 2px;"
        )
        ab_layout = QHBoxLayout(self._auto_banner)
        ab_layout.setContentsMargins(10, 6, 10, 6)
        ab_lbl = QLabel("✦  Réglages pré-sélectionnés selon l'analyse — modifiez-les si besoin")
        ab_lbl.setFont(QFont("Segoe UI", 7))
        ab_lbl.setStyleSheet(f"color: {TELE_GREEN}; background: transparent;")
        ab_lbl.setWordWrap(True)
        ab_layout.addWidget(ab_lbl)
        self._auto_banner.hide()
        root.addWidget(self._auto_banner)

        # ── Groupes accordéons ─────────────────────────────────────────────
        for title, presets in _GROUPS:
            g = _Group(title, presets)
            g.selection_changed.connect(self._on_selection_changed)
            self._groups.append(g)
            root.addWidget(g)

        # Bannière de conflit
        self._conflict_banner = _ConflictBanner()
        root.addWidget(self._conflict_banner)

        # ── Boutons du bas ─────────────────────────────────────────────────
        btns_row = QHBoxLayout()
        btns_row.setSpacing(4)
        btns_row.setContentsMargins(0, 6, 0, 0)

        self._save_btn = QPushButton("★  SAUVEGARDER")
        self._save_btn.setFont(QFont("Segoe UI", 8, QFont.Bold))
        self._save_btn.setFixedHeight(38)
        self._save_btn.setEnabled(False)
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_ELEVATED};
                color: {ACCENT_BRIGHT};
                border: 1px solid {ACCENT};
                border-radius: 3px;
                padding: 0 8px;
            }}
            QPushButton:hover {{ background: {BG_SURFACE}; }}
            QPushButton:disabled {{ color: {INACTIVE}; border-color: {INACTIVE}; }}
        """)
        self._save_btn.clicked.connect(self._on_save_preset)
        btns_row.addWidget(self._save_btn)

        self._btn = QPushButton("GÉNÉRER CONFIGURATION →")
        self._btn.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self._btn.setFixedHeight(38)
        self._btn.setEnabled(False)
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT};
                color: #020408;
                border: none;
                border-radius: 3px;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{ background: {ACCENT_BRIGHT}; }}
            QPushButton:disabled {{ background: {INACTIVE}; color: {TEXT_LABEL}; }}
        """)
        self._btn.clicked.connect(self._on_generate)
        btns_row.addWidget(self._btn, 1)

        btns_widget = QWidget()
        btns_widget.setLayout(btns_row)
        root.addWidget(btns_widget)

    def _on_selection_changed(self):
        selected_ids = self._get_selected_ids()
        conflicts = _check_conflicts(selected_ids)

        # Mettre à jour la bannière
        self._conflict_banner.show_conflicts(conflicts)

        # Marquer les groupes en conflit
        conflict_ids = set()
        for _, presets in _GROUPS:
            for p in presets:
                for id1, id2, severity, *_ in _CONFLICTS:
                    if (p.id == id1 and id2 in selected_ids) or \
                       (p.id == id2 and id1 in selected_ids):
                        if p.id in selected_ids:
                            conflict_ids.add(p.id)

        for g in self._groups:
            sid = g.get_selected_id()
            if sid and sid in conflict_ids:
                severity = "error" if any(c[0] == "error" for c in conflicts) else "warning"
                g.mark_conflict(True, severity)
            else:
                g.mark_conflict(False)

        # Activer les boutons si au moins un choix et pas de conflit bloquant
        has_error = any(c[0] == "error" for c in conflicts)
        self._btn.setEnabled(bool(selected_ids) and not has_error)
        self._save_btn.setEnabled(bool(selected_ids))
        if has_error:
            self._btn.setStyleSheet(self._btn.styleSheet().replace(
                f"background: {ACCENT};", f"background: {INACTIVE};"
            ))
            self._btn.setText("⛔  RÉSOLVEZ LES CONFLITS")
        else:
            self._btn.setStyleSheet(f"""
                QPushButton {{
                    background: {ACCENT};
                    color: #020408;
                    border: none;
                    border-radius: 3px;
                    letter-spacing: 1px;
                    margin-top: 6px;
                }}
                QPushButton:hover {{ background: {ACCENT_BRIGHT}; }}
                QPushButton:disabled {{ background: {INACTIVE}; color: {TEXT_LABEL}; }}
            """)
            self._btn.setText("GÉNÉRER CONFIGURATION →")

    def _get_selected_ids(self) -> set[str]:
        ids = set()
        for g in self._groups:
            sid = g.get_selected_id()
            if sid:
                ids.add(sid)
        return ids

    def _on_generate(self):
        selected_ids = self._get_selected_ids()
        if not selected_ids:
            return

        intent_profile = _build_intent_profile(selected_ids)
        config_overrides = _build_config_overrides(selected_ids)

        labels = [lbl for g in self._groups
                  if (lbl := g.get_selected_label()) is not None]

        summary = " · ".join(labels)

        result = SelectionResult(
            intent_profile=intent_profile,
            config_overrides=config_overrides,
            selected_labels=labels,
            human_summary=summary,
        )
        self.intent_submitted.emit(result)

    # ── Présets sauvegardés ────────────────────────────────────────────────

    def _on_save_preset(self):
        selected_ids = self._get_selected_ids()
        if not selected_ids:
            return
        labels = [lbl for g in self._groups if (lbl := g.get_selected_label())]
        default_name = " + ".join(p.split(": ", 1)[1] for p in labels[:3])
        name, ok = QInputDialog.getText(
            self, "Sauvegarder le préset", "Nom du préset :", text=default_name
        )
        if not ok or not name.strip():
            return
        presets = _load_saved_presets()
        presets.append({"name": name.strip(), "selected_ids": sorted(selected_ids)})
        _save_presets_file(presets)
        self._refresh_presets_ui()

    def _on_load_preset(self, preset: dict):
        for g in self._groups:
            if g.get_selected_id():
                g._on_choice(g.get_selected_id())  # désélectionner
        for pid in preset.get("selected_ids", []):
            for g in self._groups:
                if pid in g._buttons:
                    g.select_preset(pid)
                    break
        self._on_selection_changed()

    def _on_delete_preset(self, idx: int):
        presets = _load_saved_presets()
        if 0 <= idx < len(presets):
            presets.pop(idx)
            _save_presets_file(presets)
            self._refresh_presets_ui()

    def _refresh_presets_ui(self):
        presets = _load_saved_presets()
        layout = self._presets_chips.layout()
        while layout.count() > 1:  # garder le stretch
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not presets:
            empty = QLabel("Aucun préset — sauvegardez vos réglages favoris")
            empty.setFont(QFont(FONT_MONO, 7))
            empty.setStyleSheet(f"color: {INACTIVE};")
            layout.insertWidget(0, empty)
            return

        for idx, preset in enumerate(presets):
            chip = _PresetChip(preset["name"], idx)
            chip.load_requested.connect(lambda p=preset: self._on_load_preset(p))
            chip.delete_requested.connect(self._on_delete_preset)
            layout.insertWidget(idx, chip)

    # ── API publique ────────────────────────────────────────────────────────

    def set_locked(self, locked: bool):
        """Verrouille / déverrouille le panneau d'instructions."""
        self._is_locked = locked
        self._apply_lock(locked)

    def _apply_lock(self, locked: bool):
        self._lock_banner.setVisible(locked)
        self._presets_section.setVisible(not locked)
        for g in self._groups:
            g.setVisible(not locked)
        if hasattr(self, "_conflict_banner"):
            self._conflict_banner.setVisible(not locked)
        if hasattr(self, "_save_btn"):
            self._save_btn.setVisible(not locked)
            self._btn.setVisible(not locked)
        if hasattr(self, "_auto_banner"):
            if locked:
                self._auto_banner.hide()

    def set_loading(self, loading: bool):
        self._btn.setEnabled(not loading)
        self._save_btn.setEnabled(not loading)
        if loading:
            self._btn.setText("◌  GÉNÉRATION EN COURS...")
        else:
            self._on_selection_changed()  # recalcule l'état

    def enable_generate(self, enabled: bool):
        ids = self._get_selected_ids()
        conflicts = _check_conflicts(ids)
        has_error = any(c[0] == "error" for c in conflicts)
        self._btn.setEnabled(enabled and bool(ids) and not has_error)

    def auto_select_from_analysis(self, report) -> None:
        """Pré-sélectionne les presets selon l'analyse géométrique."""
        overhang  = getattr(report, "overhang_severity", 0.0)
        stability = getattr(report, "stability_score", 1.0)
        brim_mm   = getattr(report, "brim_recommendation_mm", 0)
        fragile   = getattr(report, "has_fragile_zones", False)
        large_flat = getattr(report, "is_large_flat_part", False)

        # Qualité → Standard (safe pour débutants)
        self._groups[0].select_preset("quality_std")

        # Résistance → renforcée si pièce fragile ou surplombs importants
        if fragile or overhang > 0.5:
            self._groups[1].select_preset("strength_high")
        else:
            self._groups[1].select_preset("strength_std")

        # Vitesse → standard (toujours plus sûr pour un débutant)
        self._groups[2].select_preset("speed_std")

        # Adhérence → selon stabilité et forme
        if large_flat or stability < 0.35:
            self._groups[3].select_preset("brim_large")
        elif brim_mm > 0 or stability < 0.65:
            self._groups[3].select_preset("brim_std")
        else:
            self._groups[3].select_preset("brim_none")

        # Usage → Intérieur standard
        self._groups[4].select_preset("usage_indoor")

        self._on_selection_changed()

        if hasattr(self, "_auto_banner") and not self._is_locked:
            self._auto_banner.show()

    def reset_selection(self):
        """Déselectionne tous les presets et cache la bannière auto."""
        for g in self._groups:
            sid = g.get_selected_id()
            if sid:
                g._on_choice(sid)
        if hasattr(self, "_auto_banner"):
            self._auto_banner.hide()
        self._on_selection_changed()
