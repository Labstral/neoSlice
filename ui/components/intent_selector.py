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
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QTimer
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
    FONT_MONO, FONT_MAIN, MANAGER as _T,
)
from core.intent.intent_profiles import IntentProfile
from core.i18n import _


# ── Données de configuration ───────────────────────────────────────────────

@dataclass
class _Preset:
    id: str
    label: str
    desc: str
    intent: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)


@dataclass
class SelectionResult:
    """Résultat de la sélection transmis à MainWindow."""
    intent_profile: IntentProfile
    config_overrides: dict
    selected_labels: list[str]
    human_summary: str


# ── Définition des groupes et presets ──────────────────────────────────────

def _make_groups() -> list[tuple[str, list[_Preset]]]:
    return [
        (_("intent.group_quality"), [
            _Preset("quality_draft",  _("intent.q_draft"),    _("intent.q_draft_desc"),
                    intent={"speed": 0.9, "quality": 0.05}),
            _Preset("quality_std",    _("intent.q_standard"), _("intent.q_standard_desc"),
                    intent={}),
            _Preset("quality_fine",   _("intent.q_fine"),     _("intent.q_fine_desc"),
                    intent={"quality": 0.8}),
            _Preset("quality_ultra",  _("intent.q_ultra"),    _("intent.q_ultra_desc"),
                    intent={"quality": 1.0, "surface_finish": 0.8}),
        ]),
        (_("intent.group_strength"), [
            _Preset("strength_light", _("intent.s_light"),    _("intent.s_light_desc"),
                    intent={"strength": 0.05, "filament_saving": 0.9}),
            _Preset("strength_std",   _("intent.s_standard"), _("intent.s_standard_desc"),
                    intent={}),
            _Preset("strength_high",  _("intent.s_strong"),   _("intent.s_strong_desc"),
                    intent={"strength": 0.75}),
            _Preset("strength_ultra", _("intent.s_ultra"),    _("intent.s_ultra_desc"),
                    intent={"strength": 1.0}),
            # Visible et sélectionné UNIQUEMENT quand une lithophanie est
            # chargée (set_lithophanie) : le profil est IMPOSÉ par le code.
            _Preset("strength_litho", _("intent.s_litho"),    _("intent.s_litho_desc"),
                    intent={}),
        ]),
        (_("intent.group_speed"), [
            _Preset("speed_std",   _("intent.sp_standard"), _("intent.sp_standard_desc"),
                    intent={}),
            _Preset("speed_high",  _("intent.sp_fast"),     _("intent.sp_fast_desc"),
                    intent={"speed": 0.75}),
            _Preset("speed_ultra", _("intent.sp_ultra"),    _("intent.sp_ultra_desc"),
                    intent={"speed": 1.0}),
        ]),
        (_("intent.group_support"), [
            _Preset("support_auto",    _("intent.sup_auto"),    _("intent.sup_auto_desc"),
                    config={"neoslice_support_mode": "auto"}),
            _Preset("support_classic", _("intent.sup_classic"), _("intent.sup_classic_desc"),
                    config={"support_type": "normal(auto)", "neoslice_support_mode": "classic"}),
            _Preset("support_tree",    _("intent.sup_tree"),    _("intent.sup_tree_desc"),
                    config={"support_type": "tree(auto)", "neoslice_support_mode": "tree"}),
            _Preset("support_none",    _("intent.sup_none"),    _("intent.sup_none_desc"),
                    config={"support_type": "none", "neoslice_support_mode": "none"}),
        ]),
        (_("intent.group_adhesion"), [
            _Preset("brim_none",  _("intent.a_none"),   _("intent.a_none_desc"),
                    config={"brim_type": "no_brim", "brim_width": 0.0}),
            _Preset("brim_std",   _("intent.a_brim5"),  _("intent.a_brim5_desc"),
                    config={"brim_type": "outer_only", "brim_width": 5.0}),
            _Preset("brim_large", _("intent.a_brim10"), _("intent.a_brim10_desc"),
                    config={"brim_type": "outer_only", "brim_width": 10.0}),
        ]),
        (_("intent.group_usage"), [
            _Preset("usage_indoor",   _("intent.u_indoor"),     _("intent.u_indoor_desc"),
                    intent={}),
            _Preset("usage_outdoor",  _("intent.u_outdoor"),    _("intent.u_outdoor_desc"),
                    intent={"outdoor_resistance": 1.0}),
            _Preset("usage_visible",  _("intent.u_visible"),    _("intent.u_visible_desc"),
                    intent={"surface_finish": 0.9}),
            _Preset("usage_precise",  _("intent.u_precision"),  _("intent.u_precision_desc"),
                    intent={"precision": 0.9}),
        ]),
        (_("intent.group_mode"), [
            _Preset("mode_normal",     _("intent.m_standard"),   _("intent.m_standard_desc"),
                    intent={}),
            _Preset("mode_silent",     _("intent.m_silent"),     _("intent.m_silent_desc"),
                    intent={"silent": 0.9}),
            _Preset("mode_multicolor", _("intent.m_multicolor"), _("intent.m_multicolor_desc"),
                    intent={"multicolor": 0.9}),
        ]),
    ]


_GROUPS: list[tuple[str, list[_Preset]]] = _make_groups()


# ── Règles de conflit inter-groupes ────────────────────────────────────────

def _make_conflicts() -> list[tuple[str, str, str, str, str]]:
    return [
        ("quality_ultra", "speed_ultra", "error",
         _("intent.conflict_ultra_fine_ultra_fast"),
         _("intent.conflict_ultra_fine_ultra_fast_hint")),

        ("quality_ultra", "speed_high", "warning",
         _("intent.conflict_fine_fast_warn"),
         _("intent.conflict_fine_fast_hint")),

        ("quality_fine", "speed_ultra", "warning",
         _("intent.conflict_fine_ultra_fast"),
         _("intent.conflict_fine_ultra_fast_hint")),

        ("strength_ultra", "speed_ultra", "error",
         _("intent.conflict_ultra_solid_ultra_fast"),
         _("intent.conflict_ultra_solid_ultra_fast_hint")),

        ("strength_ultra", "strength_light", "error",
         _("intent.conflict_solid_light"),
         _("intent.conflict_solid_light_hint")),

        ("strength_light", "usage_outdoor", "warning",
         _("intent.conflict_light_outdoor"),
         _("intent.conflict_light_outdoor_hint")),

        ("quality_draft", "usage_visible", "warning",
         _("intent.conflict_draft_visible"),
         _("intent.conflict_draft_visible_hint")),

        ("speed_ultra", "usage_visible", "warning",
         _("intent.conflict_ultra_fast_visible"),
         _("intent.conflict_ultra_fast_visible_hint")),
    ]


_CONFLICTS: list[tuple[str, str, str, str, str]] = _make_conflicts()


def _get_preset_by_id(preset_id: str) -> _Preset | None:
    for _grp, presets in _GROUPS:
        for p in presets:
            if p.id == preset_id:
                return p
    return None


def _check_conflicts(selected_ids: set[str]) -> list[tuple[str, str, str, str]]:
    found = []
    for id1, id2, severity, msg, compromise in _CONFLICTS:
        if id1 in selected_ids and id2 in selected_ids:
            found.append((severity, msg, compromise))
    return found


def _build_intent_profile(selected_ids: set[str]) -> IntentProfile:
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
    overrides: dict = {}
    for pid in selected_ids:
        p = _get_preset_by_id(pid)
        if p:
            overrides.update(p.config)
    return overrides


# ── Widget bouton de choix ─────────────────────────────────────────────────

class _ChoiceBtn(QWidget):
    """Carte cliquable représentant un preset dans un groupe."""

    clicked = Signal(str)

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
        self._title_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Bold))

        self._desc_lbl = QLabel(self._preset.desc)
        self._desc_lbl.setFont(QFont(FONT_MONO, 9))
        self._desc_lbl.setWordWrap(True)

        left.addWidget(self._title_lbl)
        left.addWidget(self._desc_lbl)
        layout.addLayout(left, 1)

        self._check = QLabel()
        self._check.setFont(QFont(FONT_MAIN, 10))
        self._check.setFixedWidth(20)
        self._check.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._check)

    def _apply_style(self):
        p = _T.palette()
        if self._selected:
            self.setStyleSheet(f"""
                _ChoiceBtn, QWidget {{
                    background: {p['BG_ELEVATED']};
                    border-left: 3px solid {p['TELE_GREEN']};
                    border-radius: 2px;
                }}
            """)
            self._title_lbl.setStyleSheet(f"color: {p['TELE_GREEN']}; background: transparent;")
            self._desc_lbl.setStyleSheet(f"color: {p['TEXT_SECONDARY']}; background: transparent;")
            self._check.setText("✓")
            self._check.setStyleSheet(f"color: {p['TELE_GREEN']}; background: transparent;")
        else:
            self.setStyleSheet(f"""
                _ChoiceBtn, QWidget {{
                    background: {p['BG_SURFACE']};
                    border-left: 3px solid transparent;
                    border-radius: 2px;
                }}
                _ChoiceBtn:hover, QWidget:hover {{
                    background: {p['BG_ELEVATED']};
                    border-left: 3px solid {p['INACTIVE']};
                }}
            """)
            self._title_lbl.setStyleSheet(f"color: {p['TEXT_PRIMARY']}; background: transparent;")
            self._desc_lbl.setStyleSheet(f"color: {p['TEXT_LABEL']}; background: transparent;")
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
            p = _T.palette()
            self.setStyleSheet(f"""
                QWidget {{ background: {p['BG_ELEVATED']}; border-left: 3px solid {p['INACTIVE']}; border-radius: 2px; }}
            """)
            self._title_lbl.setStyleSheet(f"color: {p['ACCENT_BRIGHT']}; background: transparent;")
            self._desc_lbl.setStyleSheet(f"color: {p['TEXT_SECONDARY']}; background: transparent;")

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
                font-family: {FONT_MAIN};
                font-size: 12px;
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
            self._content.setMaximumHeight(16777215)
            target_h = self._content.sizeHint().height()
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
            self._buttons[preset_id].set_selected(False)
            self._selected_id = None
        else:
            if self._selected_id and self._selected_id in self._buttons:
                self._buttons[self._selected_id].set_selected(False)
            self._selected_id = preset_id
            self._buttons[preset_id].set_selected(True)
        self.selection_changed.emit()

    def select_preset(self, preset_id: str):
        """Sélectionne un preset programmatiquement — ne toggle pas si déjà sélectionné."""
        if preset_id not in self._buttons:
            return
        if self._selected_id == preset_id:
            return  # Déjà sélectionné → ne pas toggler
        self._on_choice(preset_id)

    def set_preset_visible(self, preset_id: str, visible: bool) -> None:
        if preset_id in self._buttons:
            self._buttons[preset_id].setVisible(visible)

    def set_grise(self, grise: bool) -> None:
        """Grise et VERROUILLE le groupe (mode lithophanie : les réglages sont
        imposés par le code, l'utilisateur voit que c'est volontaire)."""
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        self._content.setEnabled(not grise)
        self._header.setEnabled(not grise)
        if grise:
            eff = QGraphicsOpacityEffect(self)
            eff.setOpacity(0.45)
            self.setGraphicsEffect(eff)
            if not self._open:
                self._toggle()            # groupe OUVERT : le choix imposé se voit
        else:
            self.setGraphicsEffect(None)

    def get_selected_id(self) -> str | None:
        return self._selected_id

    def get_selected_label(self) -> str | None:
        if self._selected_id:
            p = _get_preset_by_id(self._selected_id)
            return f"{self._title}: {p.label}" if p else None
        return None

    def mark_conflict(self, has_conflict: bool, severity: str = "warning"):
        _mp = _T.palette()
        if has_conflict:
            color = _mp["ERROR_RED"] if severity == "error" else _mp["AMBER"]
            self._header.setStyleSheet(f"""
                QPushButton {{
                    background: {_mp['BG_ELEVATED']};
                    border: none;
                    border-left: 3px solid {color};
                    color: {_mp['ACCENT_BRIGHT']};
                    text-align: left; padding: 0 10px;
                    font-family: {FONT_MAIN}; font-size: 12px;
                    font-weight: bold; letter-spacing: 2px;
                }}
                QPushButton:hover {{
                    background: {_mp['BG_SURFACE']};
                    border-left: 3px solid {color};
                }}
            """)
        else:
            self._header.setStyleSheet(f"""
                QPushButton {{
                    background: {_mp['BG_ELEVATED']};
                    border: none;
                    border-left: 3px solid {_mp['ACCENT']};
                    color: {_mp['ACCENT_BRIGHT']};
                    text-align: left;
                    padding: 0 10px;
                    font-family: {FONT_MAIN};
                    font-size: 12px;
                    font-weight: bold;
                    letter-spacing: 2px;
                }}
                QPushButton:hover {{
                    background: {_mp['BG_SURFACE']};
                    border-left: 3px solid {_mp['ACCENT_BRIGHT']};
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
        self._icon_msg.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._icon_msg.setWordWrap(True)

        self._compromise = QLabel()
        self._compromise.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._compromise.setStyleSheet(f"color: {TEXT_SECONDARY};")
        self._compromise.setWordWrap(True)

        layout.addWidget(self._icon_msg)
        layout.addWidget(self._compromise)
        self.hide()

    def show_conflicts(self, conflicts: list[tuple[str, str, str]]):
        if not conflicts:
            self.hide()
            return

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
        self.setFixedHeight(34)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 6, 0)
        layout.setSpacing(6)
        _dp = _T.palette()
        self.setStyleSheet(
            f"background: {_dp['BG_SURFACE']}; border-radius: 3px;"
            f" border-bottom: 1px solid {_dp['BG_ELEVATED']};"
        )

        lbl = QPushButton(name)
        lbl.setFont(QFont(FONT_MAIN, 9))
        lbl.setStyleSheet(f"""
            QPushButton {{ color: {_dp['AMBER']}; background: transparent; border: none; text-align: left; padding: 0; }}
            QPushButton:hover {{ color: {_dp['TEXT_PRIMARY']}; }}
        """)
        lbl.setCursor(Qt.PointingHandCursor)
        lbl.clicked.connect(self.load_requested)
        layout.addWidget(lbl, 1)

        del_btn = QPushButton("✕")
        del_btn.setFont(QFont(FONT_MAIN, 9))
        del_btn.setFixedSize(20, 20)
        del_btn.setStyleSheet(f"""
            QPushButton {{ color: {_dp['TEXT_LABEL']}; background: transparent; border: none; }}
            QPushButton:hover {{ color: {_dp['ERROR_RED']}; }}
        """)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._idx))
        layout.addWidget(del_btn)


# ── Composant principal ────────────────────────────────────────────────────

class IntentSelector(QWidget):
    """Sélecteur d'intentions par presets accordéon."""

    intent_submitted = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._groups: list[_Group] = []
        self._is_locked = True
        self._nozzle_diameter: float = 0.4
        self._setup_ui()
        self._apply_lock(True)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(1)

        _lp = _T.palette()
        self._lock_banner = QWidget()
        self._lock_banner.setAutoFillBackground(True)
        self._lock_banner.setStyleSheet(
            f"background: {_lp['BG_SURFACE']}; border-radius: 2px;"
        )
        from PySide6.QtWidgets import QSizePolicy as _QSP
        self._lock_banner.setSizePolicy(_QSP.Preferred, _QSP.Expanding)
        banner_layout = QVBoxLayout(self._lock_banner)
        banner_layout.setContentsMargins(10, 10, 10, 10)
        banner_layout.setSpacing(4)
        banner_layout.addStretch(1)        # centrage vertical du bloc de texte

        self._lock_icon_lbl = QLabel("⊘")
        self._lock_icon_lbl.setAlignment(Qt.AlignCenter)
        self._lock_icon_lbl.setStyleSheet(
            f"font-size: 30px; color: {_lp['TEXT_SECONDARY']}; background: transparent;")
        banner_layout.addWidget(self._lock_icon_lbl)

        # Même structure que le panneau verrouillé du DropZone (haut) : titre gras
        # FONT_MAIN + sous-titre FONT_MONO 9 + étape FONT_MONO 9 → polices identiques.
        self._lock_msg_lbl = QLabel(_("intent.lock_msg"))
        self._lock_msg_lbl.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._lock_msg_lbl.setAlignment(Qt.AlignCenter)
        self._lock_msg_lbl.setStyleSheet(
            f"color: {_lp['TEXT_SECONDARY']}; background: transparent; letter-spacing: 1px;")
        self._lock_msg_lbl.setWordWrap(True)
        banner_layout.addWidget(self._lock_msg_lbl)

        self._lock_sub_lbl = QLabel(_("intent.lock_sub"))
        self._lock_sub_lbl.setFont(QFont(FONT_MONO, 9))
        self._lock_sub_lbl.setAlignment(Qt.AlignCenter)
        self._lock_sub_lbl.setStyleSheet(f"color: {_lp['TEXT_LABEL']}; background: transparent;")
        self._lock_sub_lbl.setWordWrap(True)
        banner_layout.addWidget(self._lock_sub_lbl)

        self._lock_step_lbl = QLabel(_("intent.lock_step"))
        self._lock_step_lbl.setFont(QFont(FONT_MONO, 9))
        self._lock_step_lbl.setAlignment(Qt.AlignCenter)
        self._lock_step_lbl.setStyleSheet(f"color: {_lp['TEXT_LABEL']}; background: transparent;")
        banner_layout.addWidget(self._lock_step_lbl)
        banner_layout.addStretch(1)        # centrage vertical (bas)

        root.addWidget(self._lock_banner)

        # ── Section présets sauvegardés (accordéon, fermé par défaut) ────────
        self._presets_open = False
        self._presets_section = QWidget()
        self._presets_section.setStyleSheet(f"background: {BG_ELEVATED};")
        ps_layout = QVBoxLayout(self._presets_section)
        ps_layout.setContentsMargins(0, 0, 0, 0)
        ps_layout.setSpacing(0)

        self._presets_btn = QPushButton()
        self._presets_btn.setFixedHeight(30)
        self._presets_btn.setCursor(Qt.PointingHandCursor)
        self._presets_btn.clicked.connect(self._toggle_presets)
        ps_layout.addWidget(self._presets_btn)

        # Conteneur défilant — chaque préset occupe une ligne
        self._presets_chips = QWidget()
        self._presets_chips.setStyleSheet(f"background: {BG_ELEVATED};")
        chips_layout = QVBoxLayout(self._presets_chips)
        chips_layout.setContentsMargins(4, 2, 4, 4)
        chips_layout.setSpacing(2)
        chips_layout.addStretch()

        self._presets_scroll = QScrollArea()
        self._presets_scroll.setWidget(self._presets_chips)
        self._presets_scroll.setWidgetResizable(True)
        self._presets_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._presets_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._presets_scroll.setFrameShape(QFrame.NoFrame)
        self._presets_scroll.setMaximumHeight(0)   # fermé par défaut
        self._presets_scroll.setStyleSheet("background: transparent;")
        ps_layout.addWidget(self._presets_scroll)

        root.addWidget(self._presets_section)
        self._refresh_presets_ui()

        # Bannière auto-sélection
        self._auto_banner = QWidget()
        _ab_pal = _T.palette()
        self._auto_banner.setStyleSheet(
            f"background: rgba(0,200,100,0.07); border-left: 3px solid {_ab_pal['TELE_GREEN']}; border-radius: 2px;"
        )
        ab_layout = QHBoxLayout(self._auto_banner)
        ab_layout.setContentsMargins(10, 6, 10, 6)
        self._ab_lbl = QLabel(_("intent.auto_select_msg"))
        self._ab_lbl.setFont(QFont(FONT_MAIN, 9))
        self._ab_lbl.setStyleSheet(f"color: {_ab_pal['TELE_GREEN']}; background: transparent;")
        self._ab_lbl.setWordWrap(True)
        ab_layout.addWidget(self._ab_lbl)
        self._auto_banner.hide()
        root.addWidget(self._auto_banner)

        # ── Groupes accordéons ─────────────────────────────────────────────
        self._support_group_idx = -1
        self._strength_group_idx = -1
        self._litho_actif = False
        for i, (title, presets) in enumerate(_GROUPS):
            g = _Group(title, presets)
            g.selection_changed.connect(self._on_selection_changed)
            self._groups.append(g)
            root.addWidget(g)
            # Mémoriser l'index du groupe Supports
            if any(p.id == "support_auto" for p in presets):
                self._support_group_idx = i
            if any(p.id == "strength_litho" for p in presets):
                self._strength_group_idx = i
                g.set_preset_visible("strength_litho", False)   # litho seulement

        # Bannière de conflit — doit exister avant tout select_preset
        self._conflict_banner = _ConflictBanner()
        root.addWidget(self._conflict_banner)

        # Support : Auto pré-sélectionné après init complète
        if self._support_group_idx >= 0:
            idx = self._support_group_idx
            QTimer.singleShot(0, lambda: (
                self._groups[idx].select_preset("support_auto")
                if self._groups[idx].get_selected_id() != "support_auto" else None
            ))

        # ── Boutons du bas ─────────────────────────────────────────────────
        btns_row = QHBoxLayout()
        btns_row.setSpacing(4)
        btns_row.setContentsMargins(0, 0, 0, 0)

        self._save_btn = QPushButton(_("intent.btn_save"))
        self._save_btn.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
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

        self._btn = QPushButton(_("intent.btn_generate"))
        self._btn.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._btn.setFixedHeight(38)
        self._btn.setEnabled(False)
        self._btn.setCursor(Qt.PointingHandCursor)
        _dp = _T.palette()
        self._btn.setStyleSheet(f"""
            QPushButton {{
                background: {_dp['ACCENT']};
                color: #ffffff;
                border: 1px solid transparent;
                border-radius: 3px;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{ background: {_dp['ACCENT_BRIGHT']}; color: #ffffff; }}
            QPushButton:disabled {{ background: {_dp['INACTIVE']}; color: {_dp['TEXT_LABEL']}; }}
        """)
        self._btn.clicked.connect(self._on_generate)
        btns_row.addWidget(self._btn, 1)

        btns_widget = QWidget()
        btns_widget.setLayout(btns_row)
        btns_widget.setFixedHeight(38)
        root.addSpacing(6)
        root.addWidget(btns_widget)

    def _on_selection_changed(self):
        selected_ids = self._get_selected_ids()
        conflicts = _check_conflicts(selected_ids)

        self._conflict_banner.show_conflicts(conflicts)

        conflict_ids = set()
        for _grp, presets in _GROUPS:
            for p in presets:
                for id1, id2, severity, *_rest in _CONFLICTS:
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

        has_error = any(c[0] == "error" for c in conflicts)
        self._btn.setEnabled(bool(selected_ids) and not has_error
                             and getattr(self, "_prerequis_ok", True))
        self._save_btn.setEnabled(bool(selected_ids))
        _bp = _T.palette()
        if has_error:
            self._btn.setStyleSheet(f"""
                QPushButton {{
                    background: {_bp['INACTIVE']};
                    color: {_bp['TEXT_LABEL']};
                    border: 1px solid transparent; border-radius: 3px; letter-spacing: 1px;
                }}
            """)
            self._btn.setText(_("intent.btn_conflicts"))
        else:
            _btn_bg = _bp['ACCENT'] if _T.is_dark() else _bp['TELE_GREEN']
            self._btn.setStyleSheet(f"""
                QPushButton {{
                    background: {_btn_bg};
                    color: #ffffff;
                    border: 1px solid transparent;
                    border-radius: 3px;
                    letter-spacing: 1px;
                }}
                QPushButton:hover {{ background: {_bp['ACCENT_BRIGHT']}; color: #ffffff; }}
                QPushButton:disabled {{ background: {_bp['INACTIVE']}; color: {_bp['TEXT_LABEL']}; }}
            """)
            self._btn.setText(_("intent.btn_generate"))

    def _get_selected_ids(self) -> set[str]:
        ids = set()
        for g in self._groups:
            sid = g.get_selected_id()
            if sid:
                ids.add(sid)
        return ids

    def update_nozzle(self, diameter: float) -> None:
        self._nozzle_diameter = diameter

    def _on_generate(self):
        selected_ids = self._get_selected_ids()
        if not selected_ids:
            return

        intent_profile = _build_intent_profile(selected_ids)
        config_overrides = _build_config_overrides(selected_ids)
        config_overrides["nozzle_diameter"] = self._nozzle_diameter

        # Layer height selon le preset qualité sélectionné + diamètre buse.
        # Priorité absolue sur le profil de base (évite que save_filament écrase fine quality).
        # first_layer_height reste toujours à 0.20mm (meilleure adhérence 1ère couche).
        _nozzle = self._nozzle_diameter
        _closest = min(self._NOZZLE_QUALITY_HEIGHTS, key=lambda n: abs(n - _nozzle))
        _draft_h, _std_h, _fine_h, _ultra_h = self._NOZZLE_QUALITY_HEIGHTS[_closest]
        _quality_lh_map = {
            "quality_draft": _draft_h,
            "quality_std":   _std_h,
            "quality_fine":  _fine_h,
            "quality_ultra": _ultra_h,
        }
        for _qid, _lh in _quality_lh_map.items():
            if _qid in selected_ids:
                config_overrides["layer_height"] = _lh
                # first_layer_height >= layer_height (règle BS).
                # Fine/Ultra Fine: 0.20 > layer_height → 0.20 (meilleure adhérence).
                # Brouillon: 0.28 > 0.20 → doit être 0.28 sinon BS refuse.
                config_overrides["first_layer_height"] = round(max(0.20, _lh), 3)
                break

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

    def _toggle_presets(self):
        self._presets_open = not self._presets_open
        if self._presets_open:
            presets = _load_saved_presets()
            h = min(len(presets) * 38 + 8, 152) if presets else 38
            self._presets_scroll.setMaximumHeight(h)
        else:
            self._presets_scroll.setMaximumHeight(0)
        self._refresh_presets_btn()

    def _refresh_presets_btn(self):
        presets = _load_saved_presets()
        count = len(presets)
        arrow = "▼" if self._presets_open else "▶"
        suffix = f"  ({count})" if count else ""
        self._presets_btn.setText(f"  {arrow}   {_('intent.presets_header')}{suffix}")
        _dp = _T.palette()
        amber = _dp["AMBER"]
        self._presets_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_dp['BG_ELEVATED']};
                border: none;
                border-left: 3px solid {amber};
                color: {amber};
                text-align: left;
                padding: 0 10px;
                font-family: {FONT_MAIN};
                font-size: 10px;
                font-weight: bold;
                letter-spacing: 2px;
            }}
            QPushButton:hover {{
                background: {_dp['BG_SURFACE']};
                border-left: 3px solid {amber};
            }}
        """)

    def _on_save_preset(self):
        selected_ids = self._get_selected_ids()
        if not selected_ids:
            return
        labels = [lbl for g in self._groups if (lbl := g.get_selected_label())]
        default_name = " + ".join(p.split(": ", 1)[1] for p in labels[:3])
        name, ok = QInputDialog.getText(
            self, _("intent.save_dialog_title"), _("intent.save_dialog_label"), text=default_name
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
                g._on_choice(g.get_selected_id())
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
        self._refresh_presets_btn()
        presets = _load_saved_presets()
        layout = self._presets_chips.layout()
        # Vider sauf le stretch final
        while layout.count() > 1:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        _dp = _T.palette()
        if not presets:
            empty = QLabel(_("intent.presets_empty"))
            empty.setFont(QFont(FONT_MAIN, 9))
            empty.setContentsMargins(10, 4, 0, 4)
            empty.setStyleSheet(f"color: {_dp['TEXT_SECONDARY']}; background: transparent;")
            layout.insertWidget(0, empty)
            if self._presets_open:
                self._presets_scroll.setMaximumHeight(38)
            return

        if self._presets_open:
            self._presets_scroll.setMaximumHeight(min(len(presets) * 38 + 8, 152))
        for idx, preset in enumerate(presets):
            chip = _PresetChip(preset["name"], idx)
            chip.load_requested.connect(lambda p=preset: self._on_load_preset(p))
            chip.delete_requested.connect(self._on_delete_preset)
            layout.insertWidget(idx, chip)

    # ── API publique ────────────────────────────────────────────────────────

    def refresh_theme(self):
        pal = _T.palette()
        self.setStyleSheet(f"background: {pal['BG_PANEL']}")
        if hasattr(self, '_auto_banner'):
            self._auto_banner.setStyleSheet(
                f"background: rgba(0,200,100,0.07); border-left: 3px solid {pal['TELE_GREEN']}; border-radius: 2px;"
            )
        if hasattr(self, '_ab_lbl'):
            self._ab_lbl.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")
        if hasattr(self, '_lock_banner'):
            self._lock_banner.setStyleSheet(f"background: {pal['BG_SURFACE']}; border-radius: 2px;")
            self._lock_banner.update()
        if hasattr(self, '_lock_icon_lbl'):
            self._lock_icon_lbl.setStyleSheet(
                f"font-size: 30px; color: {pal['TEXT_SECONDARY']}; background: transparent;")
            self._lock_icon_lbl.update()
        if hasattr(self, '_lock_msg_lbl'):
            self._lock_msg_lbl.setStyleSheet(
                f"color: {pal['TEXT_SECONDARY']}; background: transparent; letter-spacing: 1px;")
            self._lock_msg_lbl.update()
        if hasattr(self, '_lock_sub_lbl'):
            self._lock_sub_lbl.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
            self._lock_sub_lbl.update()
        if hasattr(self, '_lock_step_lbl'):
            self._lock_step_lbl.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
            self._lock_step_lbl.update()
        if hasattr(self, '_presets_section'):
            self._presets_section.setStyleSheet(f"background: {pal['BG_ELEVATED']};")
        if hasattr(self, '_presets_chips'):
            self._presets_chips.setStyleSheet(f"background: {pal['BG_ELEVATED']};")
        if hasattr(self, '_presets_btn'):
            self._refresh_presets_ui()   # recrée les chips avec la bonne palette
        if hasattr(self, '_save_btn'):
            self._save_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {pal['BG_ELEVATED']};
                    color: {pal['ACCENT_BRIGHT']};
                    border: 1px solid {pal['ACCENT']};
                    border-radius: 3px;
                    padding: 0 8px;
                }}
                QPushButton:hover {{ background: {pal['BG_SURFACE']}; }}
                QPushButton:disabled {{ color: {pal['INACTIVE']}; border-color: {pal['INACTIVE']}; }}
            """)
        for group in self.findChildren(QWidget):
            if hasattr(group, "_header") and hasattr(group, "_content"):
                try:
                    group._header.setStyleSheet(f"""
                        QPushButton {{
                            background: {pal["BG_ELEVATED"]};
                            border: none;
                            border-left: 3px solid {pal["ACCENT"]};
                            color: {pal["ACCENT_BRIGHT"]};
                            text-align: left; padding: 0 10px;
                            font-family: {FONT_MAIN}; font-size: 8px;
                            font-weight: bold; letter-spacing: 2px;
                        }}
                        QPushButton:hover {{
                            background: {pal["BG_SURFACE"]};
                            border-left: 3px solid {pal["ACCENT_BRIGHT"]};
                        }}
                    """)
                    group._content.setStyleSheet(f"background: {pal['BG_PANEL']}")
                except Exception:
                    pass
        for btn in self.findChildren(_ChoiceBtn):
            try:
                btn._apply_style()
            except Exception:
                pass
        self._on_selection_changed()   # reapplique le style du bouton générer
        self.update()

    def set_locked(self, locked: bool):
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
            self._btn.setText(_("intent.btn_loading"))
        else:
            self._on_selection_changed()

    def set_prerequis(self, ok: bool) -> None:
        """Verrouille « Générer configuration » tant que l'étape ① (imprimante,
        filament, plateau) n'est pas VALIDÉE. Les pièces neoGen arrivent dans
        le viewer sans passer par le glisser-déposer qui imposait cette étape —
        sans ce verrou, on pouvait générer/exporter sans imprimante choisie."""
        self._prerequis_ok = ok
        self._btn.setToolTip("" if ok else _("intent.prereq_tip"))
        self._on_selection_changed()          # ré-évalue l'état du bouton

    def enable_generate(self, enabled: bool):
        ids = self._get_selected_ids()
        conflicts = _check_conflicts(ids)
        has_error = any(c[0] == "error" for c in conflicts)
        self._btn.setEnabled(enabled and bool(ids) and not has_error
                             and getattr(self, "_prerequis_ok", True))

    def set_lithophanie(self, actif: bool) -> None:
        """Mode LITHOPHANIE : la résistance est imposée par le code (remplissage
        100 %, parois lentes...). Le groupe Résistance montre le choix spécial
        « Lithophanie », GRISÉ et verrouillé — c'est volontaire et visible.
        Tout revient à la normale au chargement d'un autre fichier."""
        if self._strength_group_idx < 0 or actif == self._litho_actif:
            return
        self._litho_actif = actif
        g = self._groups[self._strength_group_idx]
        if actif:
            g.set_preset_visible("strength_litho", True)
            g.select_preset("strength_litho")
            g.set_grise(True)
            # Qualité FINE pré-sélectionnée (cohérente avec la couche fine
            # voulue pour la photo) — mais MODIFIABLE, contrairement à la
            # Résistance : l'utilisateur garde la main sur la qualité.
            self._groups[0].select_preset("quality_fine")
        else:
            g.set_grise(False)
            if g.get_selected_id() == "strength_litho":
                g.select_preset("strength_std")
            g.set_preset_visible("strength_litho", False)

    def auto_select_from_analysis(self, report) -> None:
        """Pré-sélectionne les presets selon l'analyse géométrique."""
        overhang  = getattr(report, "overhang_severity", 0.0)
        stability = getattr(report, "stability_score", 1.0)
        brim_mm   = getattr(report, "brim_recommendation_mm", 0)
        fragile   = getattr(report, "has_fragile_zones", False)
        large_flat = getattr(report, "is_large_flat_part", False)

        self._groups[0].select_preset(
            "quality_fine" if getattr(self, "_litho_actif", False)
            else "quality_std")

        if getattr(self, "_litho_actif", False):
            pass                        # résistance IMPOSÉE par la lithophanie
        elif fragile or overhang > 0.5:
            self._groups[1].select_preset("strength_high")
        else:
            self._groups[1].select_preset("strength_std")

        self._groups[2].select_preset("speed_std")

        # index 4 = ADHÉRENCE (0=qualité, 1=résistance, 2=vitesse, 3=supports, 4=adhérence)
        if large_flat or stability < 0.35:
            self._groups[4].select_preset("brim_large")
        elif brim_mm > 0 or stability < 0.65:
            self._groups[4].select_preset("brim_std")
        else:
            self._groups[4].select_preset("brim_none")

        self._groups[5].select_preset("usage_indoor")  # index 5 = USAGE

        # Support : reset à Auto sans toggle si déjà sélectionné
        if hasattr(self, "_support_group_idx"):
            grp = self._groups[self._support_group_idx]
            if grp.get_selected_id() != "support_auto":
                grp.select_preset("support_auto")

        self._on_selection_changed()

        if hasattr(self, "_auto_banner") and not self._is_locked:
            self._auto_banner.show()

    # Valeurs Bambu Studio : (draft, std, fine, ultra) en mm par buse
    _NOZZLE_QUALITY_HEIGHTS: dict[float, tuple[float, float, float, float]] = {
        0.2: (0.10, 0.10, 0.07, 0.05),
        0.4: (0.28, 0.20, 0.12, 0.08),
        0.6: (0.45, 0.25, 0.20, 0.15),
        0.8: (0.60, 0.30, 0.25, 0.20),
    }

    def update_nozzle(self, nozzle_mm: float) -> None:
        """Met à jour les descriptions de qualité selon le diamètre de buse sélectionné."""
        if not self._groups:
            return
        closest = min(self._NOZZLE_QUALITY_HEIGHTS, key=lambda n: abs(n - nozzle_mm))
        draft_h, std_h, fine_h, ultra_h = self._NOZZLE_QUALITY_HEIGHTS[closest]
        quality_group = self._groups[0]
        for preset_id, h in [
            ("quality_draft",  draft_h),
            ("quality_std",    std_h),
            ("quality_fine",   fine_h),
            ("quality_ultra",  ultra_h),
        ]:
            btn = quality_group._buttons.get(preset_id)
            if btn and hasattr(btn, "_desc_lbl"):
                current = btn._desc_lbl.text()
                suffix = current.split(" — ", 1)[1] if " — " in current else current
                btn._desc_lbl.setText(f"{h:.2f}mm — {suffix}")

    def reset_selection(self):
        for g in self._groups:
            sid = g.get_selected_id()
            if sid:
                g._on_choice(sid)
        if hasattr(self, "_auto_banner"):
            self._auto_banner.hide()
        self._on_selection_changed()
