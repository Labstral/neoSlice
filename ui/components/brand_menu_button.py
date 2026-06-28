"""Sélecteur d'imprimante à menu hiérarchique (cascade par marque).

Basé sur un vrai QComboBox pour un rendu IDENTIQUE aux autres combos (alignement
du texte, police, flèche), mais dont le popup est remplacé par un menu en cascade :
clic → marques → sous-menu des modèles. Les marques rares peuvent être rangées
sous un sous-groupe (« Autres marques ▸ Marque ▸ modèles »).

API proche d'un combo : current_key / set_current_key / signal selectionChanged.
Le style visuel du combo lui-même est appliqué par l'appelant (même feuille que
les autres combos) ; apply_theme() ne style que le menu déroulant.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtWidgets import QComboBox, QMenu

from ui.styles.theme import MANAGER as _T, FONT_MAIN


class BrandMenuButton(QComboBox):
    """Combo dont le popup est un menu hiérarchique marque → modèles."""

    selectionChanged = Signal(str)   # émet le model_key choisi

    def __init__(self, parent=None, placeholder: str = "—"):
        super().__init__(parent)
        self._key: str = ""
        self._placeholder = placeholder
        self._key_label: dict[str, str] = {}
        self._submenus: list[QMenu] = []
        self._menu = QMenu(self)
        self.addItem(placeholder)        # item d'affichage (un seul, mis à jour)
        self.apply_theme()

    # ── Popup remplacé par le menu cascade ────────────────────────────────────
    def showPopup(self):                 # noqa: N802 (API Qt)
        if self._menu.isEmpty():
            return
        self._menu.exec(self.mapToGlobal(QPoint(0, self.height())))

    # ── Population ────────────────────────────────────────────────────────────
    def set_groups(self, groups: list, keep: bool = True) -> None:
        """groups = [(libellé, payload), …].
        payload = liste de (libellé, model_key)  → modèles (feuille)
                 OU liste de (libellé, payload)  → sous-groupes (imbriqué)."""
        self._menu.clear()
        self._submenus.clear()
        self._key_label.clear()
        self._first_key = None
        self._build_into(self._menu, groups)
        self.apply_theme()

        if keep and self._key in self._key_label:
            self._set_display(self._key_label[self._key])
        elif self._first_key is not None:
            self._key = self._first_key
            self._set_display(self._key_label[self._first_key])
        else:
            self._key = ""
            self._set_display(self._placeholder)

    def _build_into(self, menu: QMenu, entries: list) -> None:
        for label, payload in entries:
            if not payload:
                continue
            sub = menu.addMenu(label)
            self._submenus.append(sub)
            if isinstance(payload[0][1], (list, tuple)):
                self._build_into(sub, payload)            # sous-groupes imbriqués
            else:
                for mlabel, key in payload:               # modèles (feuille)
                    act = sub.addAction(mlabel)
                    act.setData(key)
                    act.triggered.connect(lambda _=False, k=key: self._on_pick(k))
                    self._key_label[key] = mlabel
                    if self._first_key is None:
                        self._first_key = key

    # ── API type combo ────────────────────────────────────────────────────────
    def current_key(self) -> str:
        return self._key

    def set_current_key(self, key: str, emit: bool = True) -> None:
        if key in self._key_label:
            self._key = key
            self._set_display(self._key_label[key])
            if emit:
                self.selectionChanged.emit(key)

    def _on_pick(self, key: str) -> None:
        self._key = key
        self._set_display(self._key_label.get(key, key))
        self.selectionChanged.emit(key)

    def _set_display(self, text: str) -> None:
        """Met à jour le texte affiché (un seul item, sans émettre de signal combo)."""
        self.blockSignals(True)
        self.clear()
        self.addItem(text)
        self.setCurrentIndex(0)
        self.blockSignals(False)

    # ── Thème (menu uniquement ; le combo est stylé par l'appelant) ────────────
    def apply_theme(self) -> None:
        pal = _T.palette()
        menu_qss = f"""
            QMenu {{
                background: {pal['BG_ELEVATED']}; color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']}; padding: 3px;
                font-family: {FONT_MAIN};
            }}
            QMenu::item {{ padding: 4px 26px 4px 14px; border-radius: 3px; }}
            QMenu::item:selected {{
                background: {pal['ACCENT']}; color: {pal.get('EXPORT_FG', '#ffffff')};
            }}
        """
        self._menu.setStyleSheet(menu_qss)
        for sub in self._submenus:
            sub.setStyleSheet(menu_qss)
