"""Calculateur de coût / devis — fenêtre neoSlice Pro.

Regroupe en un seul endroit :
  - les tarifs de l'utilisateur (enregistrés dans prefs.json, configurés une fois) ;
  - les données de l'impression courante (poids/durée pré-remplis, modifiables) ;
  - le détail du coût recalculé en direct + un prix de vente conseillé ;
  - l'export d'un devis PDF (via QPdfWriter natif, sans dépendance).

L'accès est réservé à neoSlice Pro (géré à l'ouverture, comme le diagnostic).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from core import costing
from core.i18n import _
from core.prefs import PREFS
from ui.styles.theme import MANAGER as _T, FONT_MAIN, FONT_MONO


# ── Clés prefs.json (tarifs persistants) ───────────────────────────────────────
_K = {
    "country":      "cost_country",
    "currency":     "cost_currency",
    "kwh":          "cost_kwh",
    "filament":     "cost_filament_price",
    "machine":      "cost_machine_price",
    "life":         "cost_machine_life_h",
    "labor":        "cost_labor_rate",
    "packaging":    "cost_packaging",
    "failure":      "cost_failure_pct",
    "margin":       "cost_margin_pct",
}
_DEFAULTS = {
    "country":  "Suisse",
    "currency": "CHF",
    "kwh":      0.32,   # aligné sur COUNTRY_DEFAULTS["Suisse"]
    "filament": 25.0,
    "machine":  0.0,
    "life":     5000.0,
    "labor":    30.0,
    "packaging": 0.0,
    "failure":  5.0,
    "margin":   50.0,
}

# Couleurs data-viz des postes de coût (fixes, lisibles en thème clair ET sombre)
_SEG_COLORS = {
    "material":    "#1E88E5",
    "electricity": "#F4B400",
    "wear":        "#8E7CC3",
    "labor":       "#00C853",
    "packaging":   "#FF8A65",
    "failure":     "#EF5350",
}


def _f(text: str, default: float = 0.0) -> float:
    """Parse tolérant (accepte la virgule décimale française)."""
    try:
        return float(str(text).replace(",", ".").strip())
    except (TypeError, ValueError):
        return default


def _make_sep() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setFixedHeight(1)
    return sep


class _CostBar(QWidget):
    """Barre empilée de répartition des coûts + légende (thème-aware)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segs: list[tuple[str, float, str]] = []   # (label, valeur, couleur hex)
        self._text_color = "#888888"
        self.setMinimumHeight(62)

    def set_text_color(self, color: str):
        self._text_color = color
        self.update()

    def set_segments(self, segs):
        self._segs = [(lab, max(0.0, v), c) for (lab, v, c) in segs if v > 0]
        self.update()

    def paintEvent(self, _ev):
        from PySide6.QtGui import QPainter, QColor
        total = sum(v for _, v, _ in self._segs)
        p = QPainter(self)
        try:
            W = self.width()
            barh = 14
            if total <= 0:
                p.end(); return
            # Barre empilée
            x = 0.0
            for _lab, v, c in self._segs:
                w = W * (v / total)
                p.fillRect(int(round(x)), 0, int(round(w)) + 1, barh, QColor(c))
                x += w
            # Légende sur 2 colonnes
            p.setFont(QFont(FONT_MAIN, 7))
            col_w = W // 2
            for i, (lab, v, c) in enumerate(self._segs):
                col = i % 2
                row = i // 2
                lx = col * col_w
                yy = barh + 6 + row * 14
                p.fillRect(lx, yy + 2, 8, 8, QColor(c))
                p.setPen(QColor(self._text_color))
                p.drawText(lx + 12, yy, col_w - 14, 12,
                           Qt.AlignLeft | Qt.AlignVCenter, f"{lab}  {v / total * 100:.0f}%")
        finally:
            p.end()


class CostCalculatorDialog(QDialog):
    """Fenêtre de calcul de coût et de devis."""

    # Paliers de prix suggérés : (id, clé i18n, marge %, couleur trait, fond uni)
    _TIERS = [
        ("eco",      "cost.tier_eco",      20.0, "#00C853", "rgba(0,200,83,0.16)"),
        ("standard", "cost.tier_standard", 40.0, "#1E88E5", "rgba(30,136,229,0.16)"),
        ("premium",  "cost.tier_premium",  60.0, "#F4B400", "rgba(244,180,0,0.18)"),
    ]

    def __init__(self, parent=None, *, est_weight_g: float | None = None,
                 est_time_h: float | None = None,
                 printer_model: str | None = None, part_name: str = ""):
        super().__init__(parent)
        self.setObjectName("cost_dialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        # PAS de WA_TranslucentBackground : la fenêtre se redimensionne quand la
        # note « estimé » se masque → une fenêtre translucide redimensionnée garde
        # son ancien rendu (zone cliquable décalée). Fenêtre opaque = rendu OK.
        self._drag_pos: QPoint | None = None
        self._part_name = part_name or "—"
        self._printer_model = printer_model or ""
        self._rate_edits: dict[str, QLineEdit] = {}
        self._estimated = False

        self._setup_ui()

        # Pré-remplissage
        self._load_rates()
        # Poids et durée = MÊMES estimations que le panneau « EN RÉSUMÉ »
        # (calculées par neoSlice et transmises ici) → valeurs cohérentes partout.
        if est_weight_g and est_weight_g > 0:
            self._weight_edit.setText(f"{est_weight_g:.0f}")
            self._estimated = True
        if est_time_h and est_time_h > 0:
            self._time_edit.setText(f"{est_time_h:.1f}")
            self._estimated = True
        self._power_edit.setText(str(costing.printer_power_w(printer_model)))

        self._apply_theme()
        _T.register(self._apply_theme)
        self._recompute()

    def closeEvent(self, event):
        self._save_rates()
        _T.unregister(self._apply_theme)
        super().closeEvent(event)

    def showEvent(self, event):
        """Garantit que la fenêtre tient dans l'écran (sinon on réduit la zone
        défilante puis on repositionne) — jamais de fenêtre tronquée hors-écran."""
        super().showEvent(event)
        scr = self.screen() or QApplication.primaryScreen()
        if scr is None:
            return
        avail = scr.availableGeometry()
        max_h = int(avail.height() * 0.94)
        if self.height() > max_h:
            over = self.height() - max_h
            self._scroll.setMaximumHeight(max(150, self._scroll.maximumHeight() - over))
            self.adjustSize()
        g = self.frameGeometry()
        if g.bottom() > avail.bottom() - 8:
            g.moveBottom(avail.bottom() - 8)
        if g.top() < avail.top() + 8:
            g.moveTop(avail.top() + 8)
        self.move(g.topLeft())

    # ── Drag fenêtre ───────────────────────────────────────────────────────────
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, ev):
        if self._drag_pos and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _ev):
        self._drag_pos = None

    # ── Construction UI ──────────────────────────────────────────────────────
    def _row(self, label_key: str, edit: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(_(label_key))
        lbl.setFont(QFont(FONT_MAIN, 8))
        lbl.setWordWrap(True)
        self._field_labels.append(lbl)
        row.addWidget(lbl, 1)
        row.addWidget(edit)
        return row

    def _money_row(self, label_key: str, edit: QWidget) -> QHBoxLayout:
        """Comme _row mais le libellé affiche la devise courante ({cur}) et se
        met à jour quand on change de pays / devise."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(_(label_key, cur=self._cur_now()))
        lbl.setFont(QFont(FONT_MAIN, 8))
        lbl.setWordWrap(True)
        self._field_labels.append(lbl)
        self._money_labels.append((lbl, label_key))
        row.addWidget(lbl, 1)
        row.addWidget(edit)
        return row

    def _cur_now(self) -> str:
        e = getattr(self, "_currency_edit", None)
        return (e.text().strip() if e is not None else "") or _DEFAULTS["currency"]

    def _refresh_money_labels(self):
        cur = self._cur_now()
        for lbl, key in self._money_labels:
            lbl.setText(_(key, cur=cur))

    def _num_edit(self, key: str | None = None) -> QLineEdit:
        e = QLineEdit()
        e.setFont(QFont(FONT_MONO, 8))
        e.setFixedWidth(90)
        e.setAlignment(Qt.AlignRight)
        e.textChanged.connect(self._on_field_changed)
        if key is not None:
            self._rate_edits[key] = e
        return e

    def _setup_ui(self):
        self._field_labels: list[QLabel] = []
        self._section_labels: list[QLabel] = []
        self._seps: list[QFrame] = []
        self._money_labels: list = []   # (label, clé i18n) → devise dynamique

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._card = QWidget()
        self._card.setObjectName("cost_card")
        self._card.setFixedWidth(460)
        card_lay = QVBoxLayout(self._card)
        card_lay.setContentsMargins(20, 14, 20, 18)
        card_lay.setSpacing(0)
        root.addWidget(self._card)

        # Titre
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 12)
        self._title_lbl = QLabel(_("cost.title"))
        self._title_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._close_x = QPushButton("X")
        self._close_x.setFixedSize(22, 22)
        self._close_x.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._close_x.setCursor(Qt.PointingHandCursor)
        self._close_x.clicked.connect(self.close)
        title_row.addWidget(self._title_lbl)
        title_row.addStretch()
        title_row.addWidget(self._close_x)
        card_lay.addLayout(title_row)

        sep0 = _make_sep(); self._seps.append(sep0)
        card_lay.addWidget(sep0)
        card_lay.addSpacing(10)

        # ── Zone défilante : formulaire ─────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Assez grand pour tout voir sans défiler ; la barre n'apparaît que si
        # l'écran est trop petit (et elle est alors bien visible, cf. style).
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setMaximumHeight(360)
        form = QWidget()
        form.setObjectName("cost_form")
        flay = QVBoxLayout(form)
        flay.setContentsMargins(0, 0, 8, 0)
        flay.setSpacing(6)
        self._scroll.setWidget(form)
        card_lay.addWidget(self._scroll)

        # ── Section IMPRESSION (en PREMIER : saisi à chaque devis) ──────────
        lbl_print = QLabel(_("cost.section_print"))
        lbl_print.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._section_labels.append(lbl_print)
        flay.addWidget(lbl_print)

        # Nom de la pièce (figure sur le devis PDF) — champ texte large
        self._partname_edit = QLineEdit()
        self._partname_edit.setFont(QFont(FONT_MAIN, 8))
        self._partname_edit.setMinimumWidth(190)
        self._partname_edit.setText(self._part_name if self._part_name != "—" else "")
        flay.addLayout(self._row("cost.part_name", self._partname_edit))
        # Quantité
        self._qty_edit = self._num_edit()
        self._qty_edit.blockSignals(True); self._qty_edit.setText("1"); self._qty_edit.blockSignals(False)
        flay.addLayout(self._row("cost.quantity", self._qty_edit))

        self._weight_edit = self._num_edit()
        flay.addLayout(self._row("cost.weight", self._weight_edit))
        self._time_edit = self._num_edit()
        flay.addLayout(self._row("cost.time", self._time_edit))
        self._labor_min_edit = self._num_edit()
        flay.addLayout(self._row("cost.labor_min", self._labor_min_edit))
        self._power_edit = self._num_edit()
        flay.addLayout(self._row("cost.power", self._power_edit))

        # Note estimation (sous le poids)
        self._est_note = QLabel(_("cost.estimated_note"))
        self._est_note.setFont(QFont(FONT_MAIN, 8))
        self._est_note.setWordWrap(True)
        flay.addWidget(self._est_note)

        flay.addSpacing(8)
        sep_mid = _make_sep(); self._seps.append(sep_mid)
        flay.addWidget(sep_mid)
        flay.addSpacing(8)

        # ── Section TARIFS (réglée une fois, enregistrée) ───────────────────
        lbl_rates = QLabel(_("cost.section_rates"))
        lbl_rates.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._section_labels.append(lbl_rates)
        flay.addWidget(lbl_rates)

        self._rates_note = QLabel(_("cost.rates_note"))
        self._rates_note.setFont(QFont(FONT_MAIN, 8))
        self._rates_note.setWordWrap(True)
        flay.addWidget(self._rates_note)
        flay.addSpacing(2)

        self._country_combo = QComboBox()
        self._country_combo.setFont(QFont(FONT_MAIN, 8))
        for pays in costing.PAYS_ORDRE:
            self._country_combo.addItem(pays)
        self._country_combo.currentTextChanged.connect(self._on_country_changed)
        flay.addLayout(self._row("cost.country", self._country_combo))

        self._currency_edit = QLineEdit(); self._currency_edit.setFixedWidth(90)
        self._currency_edit.setFont(QFont(FONT_MONO, 8))
        self._currency_edit.setAlignment(Qt.AlignRight)
        self._currency_edit.textChanged.connect(self._on_field_changed)
        self._rate_edits["currency"] = self._currency_edit
        flay.addLayout(self._row("cost.currency", self._currency_edit))

        flay.addLayout(self._money_row("cost.kwh", self._num_edit("kwh")))
        flay.addLayout(self._money_row("cost.filament_price", self._num_edit("filament")))
        flay.addLayout(self._money_row("cost.machine_price", self._num_edit("machine")))
        flay.addLayout(self._row("cost.machine_life", self._num_edit("life")))
        flay.addLayout(self._money_row("cost.labor_rate", self._num_edit("labor")))
        flay.addLayout(self._money_row("cost.packaging", self._num_edit("packaging")))
        flay.addLayout(self._row("cost.failure", self._num_edit("failure")))
        flay.addLayout(self._row("cost.margin", self._num_edit("margin")))
        flay.addStretch()

        card_lay.addSpacing(12)
        sep1 = _make_sep(); self._seps.append(sep1)
        card_lay.addWidget(sep1)
        card_lay.addSpacing(10)

        # ── Détail du coût (toujours visible) ───────────────────────────────
        self._break_rows: dict[str, tuple[QLabel, QLabel]] = {}
        for key, label_key in (
            ("material",    "cost.row_material"),
            ("electricity", "cost.row_electricity"),
            ("wear",        "cost.row_wear"),
            ("labor",       "cost.row_labor"),
            ("packaging",   "cost.row_packaging"),
            ("failure",     "cost.row_failure"),
        ):
            r = QHBoxLayout(); r.setContentsMargins(0, 0, 0, 0)
            name = QLabel(_(label_key)); name.setFont(QFont(FONT_MAIN, 8))
            val = QLabel("—"); val.setFont(QFont(FONT_MONO, 8)); val.setAlignment(Qt.AlignRight)
            r.addWidget(name, 1); r.addWidget(val)
            card_lay.addLayout(r)
            card_lay.addSpacing(2)
            self._break_rows[key] = (name, val)

        card_lay.addSpacing(4)
        sep2 = _make_sep(); self._seps.append(sep2)
        card_lay.addSpacing(6)

        # Coût de revient
        rc = QHBoxLayout(); rc.setContentsMargins(0, 0, 0, 0)
        self._total_name = QLabel(_("cost.total")); self._total_name.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._total_val = QLabel("—"); self._total_val.setFont(QFont(FONT_MONO, 9, QFont.Bold)); self._total_val.setAlignment(Qt.AlignRight)
        rc.addWidget(self._total_name, 1); rc.addWidget(self._total_val)
        card_lay.addLayout(rc)
        card_lay.addSpacing(8)

        # ── Prix suggérés (paliers de marge, façon « stratégie de prix ») ───
        self._tiers_lbl = QLabel(_("cost.suggested_prices"))
        self._tiers_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._section_labels.append(self._tiers_lbl)
        card_lay.addWidget(self._tiers_lbl)
        card_lay.addSpacing(4)
        tiers_row = QHBoxLayout(); tiers_row.setSpacing(8)
        self._tier_cards: dict = {}
        for tid, key, margin, color, fill in self._TIERS:
            card = QWidget(); card.setObjectName(f"tier_{tid}")
            card.setAttribute(Qt.WA_StyledBackground, True)
            card.setMinimumHeight(58)
            cl = QVBoxLayout(card); cl.setContentsMargins(11, 9, 11, 11); cl.setSpacing(4)
            nm = QLabel(f"{_(key)} +{margin:.0f}%"); nm.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
            pv = QLabel("—"); pv.setFont(QFont(FONT_MONO, 12, QFont.Bold))
            cl.addWidget(nm); cl.addWidget(pv)
            tiers_row.addWidget(card, 1)
            self._tier_cards[tid] = (card, nm, pv, color, margin, fill)
        card_lay.addLayout(tiers_row)
        card_lay.addSpacing(12)

        # Marge
        rm = QHBoxLayout(); rm.setContentsMargins(0, 0, 0, 0)
        self._margin_name = QLabel(_("cost.margin_row")); self._margin_name.setFont(QFont(FONT_MAIN, 8))
        self._margin_val = QLabel("—"); self._margin_val.setFont(QFont(FONT_MONO, 8)); self._margin_val.setAlignment(Qt.AlignRight)
        rm.addWidget(self._margin_name, 1); rm.addWidget(self._margin_val)
        card_lay.addLayout(rm)
        card_lay.addSpacing(6)

        # Prix de vente (grand, accent)
        rs = QHBoxLayout(); rs.setContentsMargins(0, 0, 0, 0)
        self._sale_name = QLabel(_("cost.sale_price")); self._sale_name.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._sale_name.setWordWrap(True)
        self._sale_val = QLabel("—"); self._sale_val.setFont(QFont(FONT_MONO, 12, QFont.Bold)); self._sale_val.setAlignment(Qt.AlignRight)
        rs.addWidget(self._sale_name, 1); rs.addWidget(self._sale_val)
        card_lay.addLayout(rs)
        card_lay.addSpacing(4)

        # Total pour N pièces (affiché seulement si quantité > 1)
        rq = QHBoxLayout(); rq.setContentsMargins(0, 0, 0, 0)
        self._qtytotal_name = QLabel("—"); self._qtytotal_name.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._qtytotal_val = QLabel("—"); self._qtytotal_val.setFont(QFont(FONT_MONO, 11, QFont.Bold))
        self._qtytotal_val.setAlignment(Qt.AlignRight)
        rq.addWidget(self._qtytotal_name, 1); rq.addWidget(self._qtytotal_val)
        card_lay.addLayout(rq)
        card_lay.addSpacing(12)

        # ── Répartition des coûts ───────────────────────────────────────────
        self._dist_lbl = QLabel(_("cost.distribution"))
        self._dist_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._section_labels.append(self._dist_lbl)
        card_lay.addWidget(self._dist_lbl)
        card_lay.addSpacing(4)
        self._cost_bar = _CostBar()
        card_lay.addWidget(self._cost_bar)
        card_lay.addSpacing(12)

        # Boutons
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        self._pdf_btn = QPushButton(_("cost.export_pdf"))
        self._pdf_btn.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._pdf_btn.setFixedHeight(32)
        self._pdf_btn.setCursor(Qt.PointingHandCursor)
        self._pdf_btn.clicked.connect(self._export_pdf)
        self._close_btn = QPushButton(_("cost.close"))
        self._close_btn.setFont(QFont(FONT_MAIN, 8))
        self._close_btn.setFixedHeight(32)
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.clicked.connect(self.close)
        btn_row.addWidget(self._pdf_btn, 1)
        btn_row.addWidget(self._close_btn)
        card_lay.addLayout(btn_row)

        # Message de statut (export)
        self._status_lbl = QLabel("")
        self._status_lbl.setFont(QFont(FONT_MAIN, 7))
        self._status_lbl.setWordWrap(True)
        card_lay.addWidget(self._status_lbl)

    # ── Persistance des tarifs ──────────────────────────────────────────────
    def _load_rates(self):
        country = PREFS.get(_K["country"], _DEFAULTS["country"])
        idx = self._country_combo.findText(country)
        if idx >= 0:
            self._country_combo.blockSignals(True)
            self._country_combo.setCurrentIndex(idx)
            self._country_combo.blockSignals(False)
        self._currency_edit.setText(str(PREFS.get(_K["currency"], _DEFAULTS["currency"])))
        for key in ("kwh", "filament", "machine", "life", "labor", "packaging", "failure", "margin"):
            self._rate_edits[key].setText(str(PREFS.get(_K[key], _DEFAULTS[key])))
        self._refresh_money_labels()

    def _save_rates(self):
        PREFS.set(_K["country"], self._country_combo.currentText())
        PREFS.set(_K["currency"], self._currency_edit.text().strip() or _DEFAULTS["currency"])
        for key in ("kwh", "filament", "machine", "life", "labor", "packaging", "failure", "margin"):
            PREFS.set(_K[key], _f(self._rate_edits[key].text(), _DEFAULTS[key]))

    def _on_country_changed(self, pays: str):
        d = costing.COUNTRY_DEFAULTS.get(pays)
        if d:
            self._rate_edits["kwh"].setText(str(d["kwh"]))
            self._currency_edit.setText(d["devise"])
        self._recompute()

    def _on_field_changed(self, *_a):
        # Une saisie manuelle du poids OU de la durée annule l'étiquette « estimé »
        if self.sender() in (self._weight_edit, self._time_edit):
            self._estimated = False
            self._refresh_note()
        self._refresh_money_labels()   # devise des libellés à jour (pays/devise)
        self._recompute()

    # ── Calcul ───────────────────────────────────────────────────────────────
    def _current_inputs(self) -> costing.CostInputs:
        return costing.CostInputs(
            weight_g=_f(self._weight_edit.text()),
            time_h=_f(self._time_edit.text()),
            filament_price_kg=_f(self._rate_edits["filament"].text(), _DEFAULTS["filament"]),
            printer_power_w=_f(self._power_edit.text(), costing.printer_power_w(self._printer_model)),
            kwh_rate=_f(self._rate_edits["kwh"].text(), _DEFAULTS["kwh"]),
            machine_price=_f(self._rate_edits["machine"].text()),
            machine_lifespan_h=_f(self._rate_edits["life"].text(), _DEFAULTS["life"]),
            labor_minutes=_f(self._labor_min_edit.text()),
            labor_rate_h=_f(self._rate_edits["labor"].text(), _DEFAULTS["labor"]),
            packaging_cost=_f(self._rate_edits["packaging"].text(), _DEFAULTS["packaging"]),
            failure_rate_pct=_f(self._rate_edits["failure"].text(), _DEFAULTS["failure"]),
            margin_pct=_f(self._rate_edits["margin"].text(), _DEFAULTS["margin"]),
            currency=self._currency_edit.text().strip() or _DEFAULTS["currency"],
        )

    def _recompute(self):
        b = costing.compute_cost(self._current_inputs())
        cur = b.currency

        def fmt(v):
            return f"{v:.2f} {cur}"

        self._break_rows["material"][1].setText(fmt(b.material))
        self._break_rows["electricity"][1].setText(fmt(b.electricity))
        self._break_rows["wear"][1].setText(fmt(b.wear))
        self._break_rows["labor"][1].setText(fmt(b.labor))
        self._break_rows["packaging"][1].setText(fmt(b.packaging))
        self._break_rows["failure"][1].setText(fmt(b.failure_buffer))
        self._total_val.setText(fmt(b.total_cost))
        self._margin_val.setText(fmt(b.margin_amount))
        self._sale_val.setText(fmt(b.sale_price))

        # Paliers de prix suggérés (prix unitaire par marge)
        for _tid, (_card, _nm, pv, _color, margin, _fill) in self._tier_cards.items():
            pv.setText(fmt(costing.sale_price_for(b.total_cost, margin)))

        # Total pour N pièces (affiché seulement si quantité > 1)
        qty = max(1, int(_f(self._qty_edit.text(), 1)))
        if qty > 1:
            self._qtytotal_name.setText(_("cost.total_qty", n=qty))
            self._qtytotal_val.setText(fmt(b.sale_price * qty))
            self._qtytotal_name.setVisible(True)
            self._qtytotal_val.setVisible(True)
        else:
            self._qtytotal_name.setVisible(False)
            self._qtytotal_val.setVisible(False)

        # Répartition des coûts (barre empilée)
        self._cost_bar.set_segments([
            (_("cost.row_material"),    b.material,        _SEG_COLORS["material"]),
            (_("cost.row_electricity"), b.electricity,     _SEG_COLORS["electricity"]),
            (_("cost.row_wear"),        b.wear,            _SEG_COLORS["wear"]),
            (_("cost.row_labor"),       b.labor,           _SEG_COLORS["labor"]),
            (_("cost.row_packaging"),   b.packaging,       _SEG_COLORS["packaging"]),
            (_("cost.row_failure"),     b.failure_buffer,  _SEG_COLORS["failure"]),
        ])
        self._last = b
        self._last_qty = qty

    def _refresh_note(self):
        self._est_note.setVisible(self._estimated)

    # ── Export PDF ──────────────────────────────────────────────────────────
    def _export_pdf(self):
        self._save_rates()
        b = self._last
        # Nom de pièce éditable → figure sur le devis
        self._part_name = self._partname_edit.text().strip() or "—"
        base = self._part_name if self._part_name != "—" else "piece"
        default_name = f"devis_{base}".replace(" ", "_")[:40] + ".pdf"

        # Dialogue NATIF (look du système, ce que l'utilisateur veut). Ancré sur la
        # FENÊTRE PRINCIPALE et non sur la petite fenêtre devis : le natif se centre
        # sur sa fenêtre parente ; ancré sur le devis (souvent près d'un bord), il
        # débordait sur l'écran voisin. La principale est grande/centrée → bon écran.
        parent = self.parent() or self
        path, _filter = QFileDialog.getSaveFileName(
            parent, _("cost.export_pdf"),
            str(Path.home() / default_name), "PDF (*.pdf)",
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            self._render_pdf(path, b)
            self._status_lbl.setText(_("cost.pdf_saved", path=path))
            pal = _T.palette()
            self._status_lbl.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")
        except Exception as exc:
            self._status_lbl.setText(_("cost.pdf_error", error=exc))
            pal = _T.palette()
            self._status_lbl.setStyleSheet(f"color: {pal['ERROR_RED']}; background: transparent;")

    def _render_pdf(self, path: str, b: costing.CostBreakdown):
        from PySide6.QtGui import QPdfWriter, QPainter, QPageSize, QColor
        from PySide6.QtCore import QMarginsF

        writer = QPdfWriter(path)
        writer.setPageSize(QPageSize(QPageSize.A4))
        writer.setResolution(150)
        writer.setPageMargins(QMarginsF(18, 18, 18, 18))
        try:
            writer.setTitle(f"{_('cost.quote_heading')} — {self._part_name}")
        except Exception:
            pass

        p = QPainter(writer)
        try:
            W = writer.width()
            ink = QColor("#0B0F14")
            grey = QColor("#5A6B7A")
            accent = QColor("#1E88E5")
            cur = b.currency
            x0 = 0
            y = 0

            big = QFont(FONT_MAIN, 22, QFont.Bold)
            mid = QFont(FONT_MAIN, 11, QFont.Bold)
            normal = QFont(FONT_MAIN, 10)
            mono = QFont(FONT_MONO, 10)

            # En-tête
            p.setFont(big); p.setPen(ink)
            p.drawText(x0, y, W, 60, Qt.AlignLeft | Qt.AlignVCenter, "neoSlice")
            p.setFont(QFont(FONT_MAIN, 12)); p.setPen(accent)
            p.drawText(x0, y, W, 60, Qt.AlignRight | Qt.AlignVCenter, _("cost.quote_heading"))
            y += 70
            p.setPen(grey); p.setFont(normal)
            p.drawText(x0, y, W, 26, Qt.AlignLeft, f"{_('cost.quote_part')} : {self._part_name}")
            p.drawText(x0, y, W, 26, Qt.AlignRight, f"{_('cost.quote_date')} : {date.today().isoformat()}")
            y += 40
            p.setPen(QColor("#C8D2DC"))
            p.drawLine(x0, y, W, y)
            y += 30

            def line(name, value, bold=False, big_val=False, color=ink):
                nonlocal y
                p.setPen(ink if not bold else accent)
                p.setFont(mid if bold else normal)
                p.drawText(x0, y, int(W * 0.62), 30, Qt.AlignLeft | Qt.AlignVCenter, name)
                p.setFont(QFont(FONT_MONO, 13, QFont.Bold) if big_val else mono)
                p.setPen(color)
                p.drawText(int(W * 0.62), y, int(W * 0.38), 30, Qt.AlignRight | Qt.AlignVCenter,
                           f"{value:.2f} {cur}")
                y += 34

            line(_("cost.row_material"), b.material)
            line(_("cost.row_electricity"), b.electricity)
            line(_("cost.row_wear"), b.wear)
            line(_("cost.row_labor"), b.labor)
            if b.packaging > 0:
                line(_("cost.row_packaging"), b.packaging)
            line(_("cost.row_failure"), b.failure_buffer)
            y += 6
            p.setPen(QColor("#C8D2DC")); p.drawLine(x0, y, W, y); y += 24
            line(_("cost.total"), b.total_cost, bold=False, color=ink)
            line(_("cost.margin_row"), b.margin_amount)
            y += 10
            line(_("cost.sale_price"), b.sale_price, bold=True, big_val=True, color=accent)
            qty = getattr(self, "_last_qty", 1)
            if qty > 1:
                y += 6
                line(_("cost.total_qty", n=qty), b.sale_price * qty, bold=True, big_val=True, color=accent)

            # Pied de page : mention légale (non contractuel) + signature
            p.setFont(QFont(FONT_MAIN, 7)); p.setPen(grey)
            p.drawText(x0, writer.height() - 96, W, 56,
                       Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
                       _("cost.quote_disclaimer"))
            p.setFont(QFont(FONT_MAIN, 8)); p.setPen(grey)
            p.drawText(x0, writer.height() - 36, W, 26, Qt.AlignCenter,
                       "neoSlice — neoslice-ai.com")
        finally:
            p.end()

    # ── Thème ─────────────────────────────────────────────────────────────────
    def _apply_theme(self):
        pal = _T.palette()
        # Fond du dialog opaque (plus de translucence) → les coins autour de la
        # card arrondie prennent la couleur du panneau au lieu de gris système.
        self.setStyleSheet(f"QDialog#cost_dialog {{ background: {pal['BG_PANEL']}; }}")
        self._card.setStyleSheet(f"""
            QWidget#cost_card {{
                background: {pal['BG_PANEL']};
                border: 1px solid {pal['ACCENT']};
                border-radius: 6px;
            }}
            QWidget#cost_form {{ background: {pal['BG_PANEL']}; }}
        """)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: {pal['BG_ELEVATED']}; width: 14px; margin: 0; border-radius: 7px;
            }}
            QScrollBar::handle:vertical {{
                background: {pal['TEXT_SECONDARY']}; border-radius: 6px; min-height: 32px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {pal['ACCENT']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)
        self._title_lbl.setStyleSheet(
            f"color: {pal['TEXT_PRIMARY']}; background: transparent; letter-spacing: 2px;"
        )
        self._close_x.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {pal['TEXT_SECONDARY']};
                           border: none; border-radius: 3px; font-weight: bold; }}
            QPushButton:hover {{ background: {pal['ERROR_RED']}; color: white; }}
        """)
        for sep in self._seps:
            sep.setStyleSheet(f"background: {pal['INACTIVE']}; border: none;")
        for lbl in self._section_labels:
            lbl.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent; letter-spacing: 2px;")
        for lbl in self._field_labels:
            lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        self._est_note.setStyleSheet(f"color: {pal['AMBER']}; background: transparent;")
        self._rates_note.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent; font-style: italic;")
        self._refresh_note()

        edit_css = f"""
            QLineEdit {{ background: {pal['BG_INPUT']}; color: {pal['TEXT_PRIMARY']};
                         border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 3px 6px; }}
            QLineEdit:focus {{ border-color: {pal['ACCENT']}; }}
        """
        for e in list(self._rate_edits.values()) + [
            self._weight_edit, self._time_edit, self._labor_min_edit, self._power_edit,
            self._partname_edit, self._qty_edit,
        ]:
            e.setStyleSheet(edit_css)
        self._country_combo.setStyleSheet(f"""
            QComboBox {{ background: {pal['BG_INPUT']}; color: {pal['TEXT_PRIMARY']};
                         border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 2px 6px; }}
            QComboBox QAbstractItemView {{ background: {pal['BG_ELEVATED']}; color: {pal['TEXT_PRIMARY']};
                         border: 1px solid {pal['INACTIVE']}; selection-background-color: {pal['ACCENT']}; }}
        """)

        for name, val in self._break_rows.values():
            name.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
            val.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        self._total_name.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        self._total_val.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        self._margin_name.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        self._margin_val.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        self._sale_name.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent; letter-spacing: 1px;")
        self._sale_val.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")
        self._status_lbl.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")

        # Cartes de paliers de prix (fond de couleur uni + bordure assortie)
        for tid, (card, nm, pv, color, _margin, fill) in self._tier_cards.items():
            card.setStyleSheet(
                f"QWidget#tier_{tid} {{ background: {fill}; "
                f"border: 1px solid {color}; border-radius: 7px; }}"
            )
            nm.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent; border: none;")
            pv.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent; border: none;")
        self._qtytotal_name.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        self._qtytotal_val.setStyleSheet(f"color: {pal['ACCENT']}; background: transparent;")
        self._cost_bar.set_text_color(pal['TEXT_SECONDARY'])

        self._pdf_btn.setStyleSheet(f"""
            QPushButton {{ background: {pal['TELE_GREEN']}; color: {pal['EXPORT_FG']};
                           border: none; border-radius: 3px; letter-spacing: 1px; }}
            QPushButton:hover {{ background: #00D080; }}
        """)
        self._close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {pal['TEXT_SECONDARY']};
                           border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 0 14px; }}
            QPushButton:hover {{ border-color: {pal['ACCENT']}; color: {pal['ACCENT']}; }}
        """)
