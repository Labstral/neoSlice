"""Génère la fiche de réglages filament et le rapport complet en PDF avec reportlab."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

# Températures plateau × filament (°C). Sources : fiches officielles Bambu Lab par plateau.
# Pour les plages (ex. 90~110°C), on prend 100°C. Pour 45~60°C, on prend 60°C.
# Cool Plate : pas de doc officielle Bambu pour filaments hors PLA — valeurs estimées
# (les avertissements dans l'UI signalent les combos non recommandés).
# SuperTack : seul PLA est officiellement documenté (45°C). Les autres filaments affichent
# un avertissement dans l'UI mais on conserve une température de référence raisonnable.
_PLATE_BED_TEMPS: dict[str, dict[str, tuple[int, int]]] = {
    "Textured PEI Plate": {                         # source : fiche Bambu Textured PEI
        "PLA": (60, 60),   # 45~60°C
        "PETG": (70, 70),  # 60~80°C
        "ABS": (100, 100), # 90~100°C
        "ASA": (100, 100), # 90~100°C
        "Nylon": (100, 100), # 90~110°C
        "PC": (100, 100),  # 90~110°C
        "TPU": (40, 40),   # 35~45°C
        "TPE": (40, 40),   # non listé — estimé
    },
    "Cool Plate": {                                  # source : pas de doc officielle Bambu
        "PLA": (35, 35),   # connu — plateau conçu pour PLA
        "PETG": (70, 70),  # estimé (avec colle — non recommandé)
        "ABS": (100, 100), # estimé (non recommandé)
        "ASA": (100, 100), # estimé (non recommandé)
        "Nylon": (100, 100), # estimé (non recommandé)
        "PC": (100, 100),  # estimé (non recommandé)
        "TPU": (40, 40),   # estimé
        "TPE": (40, 40),   # estimé
    },
    "Hot Plate": {                                   # source : fiche Bambu Smooth PEI
        "PLA": (60, 60),   # 45~60°C
        "PETG": (70, 70),  # 60~80°C
        "ABS": (100, 100), # 90~100°C
        "ASA": (100, 100), # 90~100°C
        "Nylon": (100, 100), # 90~110°C
        "PC": (100, 100),  # 90~110°C
        "TPU": (40, 40),   # 35~45°C
        "TPE": (40, 40),   # non listé — estimé
    },
    "Engineering Plate": {                           # source : fiche Bambu Engineering
        "PLA": (60, 60),   # 45~60°C
        "PETG": (80, 80),  # 60~80°C (haut de plage)
        "ABS": (100, 100), # 90~100°C
        "ASA": (100, 100), # 90~100°C
        "Nylon": (100, 100), # 90~110°C
        "PC": (100, 100),  # 90~110°C
        "TPU": (40, 40),   # 35~45°C
        "TPE": (40, 40),   # non listé — estimé
    },
    "Bambu Cool Plate SuperTack": {                  # source : fiche Bambu SuperTack
        "PLA": (45, 45),   # documenté : 45°C côté SuperTack
        "PETG": (70, 70),  # non documenté — estimé (avertissement UI)
        "ABS": (100, 100), # non documenté — estimé (avertissement UI)
        "ASA": (100, 100), # non documenté — estimé (avertissement UI)
        "Nylon": (100, 100), # non documenté — estimé (avertissement UI)
        "PC": (100, 100),  # non documenté — estimé (avertissement UI)
        "TPU": (40, 40),   # non documenté — estimé (avertissement UI)
        "TPE": (40, 40),   # non documenté — estimé (avertissement UI)
    },
}

_PLATE_DISPLAY: dict[str, str] = {
    "Textured PEI Plate":         "Textured PEI Plate",
    "Cool Plate":                  "Cool Plate / PLA Plate",
    "Hot Plate":                   "Smooth PEI / High Temp Plate",
    "Engineering Plate":           "Engineering Plate",
    "Bambu Cool Plate SuperTack":  "Bambu Cool Plate SuperTack",
}


def _get_bed_temps(plate_type: str, filament_name: str, fallback) -> tuple:
    pair = _PLATE_BED_TEMPS.get(plate_type, {}).get(filament_name)
    return pair if pair else (fallback, fallback)

from loguru import logger


def _assets_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is not None:
        return Path(meipass) / "assets"
    return Path(__file__).parent.parent.parent / "assets"

if TYPE_CHECKING:
    from core.geometry.analysis_report import AnalysisReport
    from core.parameters.print_config import PrintConfig


def generate_filament_pdf(
    filament_name: str,
    printer_name: str,
    output_path: Path,
    plate_type: str = "Textured PEI Plate",
) -> bool:
    """Génère le PDF et retourne True si succès."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.colors import HexColor, white, black
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph,
            Spacer, HRFlowable, KeepTogether, Image,
        )
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
    except ImportError:
        logger.error("reportlab non installé — pip install reportlab")
        return False

    from data.filaments import FILAMENTS
    from core.i18n import _

    fil = FILAMENTS.get(filament_name)
    if not fil:
        logger.error(f"Filament inconnu : {filament_name}")
        return False

    # ── Couleurs ─────────────────────────────────────────────────────────
    C_BG       = HexColor("#070D14")
    C_PANEL    = HexColor("#0A1628")
    C_ELEVATED = HexColor("#0F1F35")
    C_ACCENT   = HexColor("#1E90FF")
    C_GREEN    = HexColor("#00FF9F")
    C_AMBER    = HexColor("#FFB800")
    C_RED      = HexColor("#FF3B3B")
    C_TEXT     = HexColor("#C8DCF0")
    C_MUTED    = HexColor("#4A7A9B")
    C_INACTIVE = HexColor("#1A3550")

    # ── Styles texte ──────────────────────────────────────────────────────
    def style(name, size=9, color=C_TEXT, bold=False, align=TA_LEFT, leading=None):
        return ParagraphStyle(
            name,
            fontSize=size,
            textColor=color,
            fontName="Helvetica-Bold" if bold else "Helvetica",
            alignment=align,
            leading=leading or size * 1.35,
            spaceAfter=0,
        )

    s_title    = style("title",   16, C_ACCENT,  bold=True,  align=TA_CENTER)
    s_sub      = style("sub",      9, C_MUTED,               align=TA_CENTER)
    s_section  = style("section", 10, C_ACCENT,  bold=True)
    s_warn     = style("warn",     9, C_RED,      bold=True)
    s_cell     = style("cell",     8, C_TEXT)
    s_cell_hl  = style("cell_hl",  8, white,      bold=True)
    s_cell_mut = style("cell_mut", 8, C_MUTED)
    s_note     = style("note",     8, C_MUTED)
    s_footer   = style("footer",   7, C_INACTIVE,             align=TA_CENTER)

    # ── Helpers tableaux ──────────────────────────────────────────────────
    COL_W = [5.8*cm, 3.5*cm, 1.5*cm, 5.2*cm]

    def _row(param, value, unit="", note="", highlight=False):
        p_style = s_cell_hl if highlight else s_cell
        n_style = s_cell_hl if highlight else s_cell_mut
        return [
            Paragraph(param, p_style),
            Paragraph(str(value), p_style),
            Paragraph(unit, p_style),
            Paragraph(note, n_style),
        ]

    def _table(rows, highlight_rows: set | None = None):
        highlight_rows = highlight_rows or set()
        header = [
            Paragraph(_("pdf.col_param"), style("hdr", 8, C_MUTED, bold=True)),
            Paragraph(_("pdf.col_value"), style("hdr", 8, C_MUTED, bold=True)),
            Paragraph(_("pdf.col_unit"),  style("hdr", 8, C_MUTED, bold=True)),
            Paragraph(_("pdf.col_note"),  style("hdr", 8, C_MUTED, bold=True)),
        ]
        data = [header] + rows
        ts = TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), C_ELEVATED),
            ("BACKGROUND", (0, 1), (-1, -1), C_PANEL),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_PANEL, C_BG]),
            ("GRID", (0, 0), (-1, -1), 0.3, C_INACTIVE),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])
        for i in highlight_rows:
            row_idx = i + 1
            ts.add("BACKGROUND", (0, row_idx), (-1, row_idx), C_ACCENT)
        t = Table(data, colWidths=COL_W, repeatRows=1)
        t.setStyle(ts)
        return t

    def _section_title(text):
        return [
            Spacer(1, 0.35*cm),
            Paragraph(text, s_section),
            HRFlowable(width="100%", thickness=0.5, color=C_ACCENT, spaceAfter=4),
        ]

    def yn(v):
        return _("pdf.yes") if v else _("pdf.no")

    # ── Contenu ───────────────────────────────────────────────────────────
    story = []

    story.append(Spacer(1, 0.3*cm))
    _logo_path = _assets_dir() / "neoSlice.png"
    if _logo_path.exists():
        _logo = Image(str(_logo_path), width=2.8*cm, height=2.8*cm)
        _logo.hAlign = "CENTER"
        story.append(_logo)
    else:
        story.append(Paragraph("◈  NEOSLICE", s_title))
    story.append(Spacer(1, 0.15*cm))
    story.append(Paragraph(_("pdf.filament_subtitle"), style("sub2", 11, C_TEXT, align=TA_CENTER)))
    story.append(Spacer(1, 0.15*cm))
    date_str = datetime.now().strftime("%d/%m/%Y")
    story.append(Paragraph(
        _("pdf.header_fmt", filament=filament_name, printer=printer_name, date=date_str),
        s_sub,
    ))
    story.append(Spacer(1, 0.5*cm))

    warnings = fil.get("warnings", [])
    if warnings:
        for w in warnings:
            story.append(Paragraph(f"⚠  {w}", s_warn))
            story.append(Spacer(1, 0.1*cm))
        story.append(Spacer(1, 0.2*cm))

    # ── Section 1 : Informations de base ──────────────────────────────────
    rapport = fil.get("rapport_debit", 0.98)
    hl_rapport = {0} if rapport != 1.0 else set()
    story.append(KeepTogether(_section_title(_("pdf.sec_base")) + [
        _table([
            _row(_("pdf.flow_ratio"),       f"{rapport:.2f}", "",   _("pdf.flow_note"), rapport != 1.0),
            _row(_("pdf.softening_temp"),   fil.get("ramollissement", "—"), "°C", ""),
        ], hl_rapport)
    ]))

    # ── Section 2 : Températures ──────────────────────────────────────────
    _bed_first, _bed_other = _get_bed_temps(plate_type, filament_name, fil.get("plateau", "—"))
    _plate_label = _PLATE_DISPLAY.get(plate_type, plate_type)
    story.append(KeepTogether(_section_title(_("pdf.sec_temp")) + [
        _table([
            _row(_("pdf.plate_selected"), _plate_label,                 "",   ""),
            _row(_("pdf.bed_first"),      str(_bed_first),              "°C", "", True),
            _row(_("pdf.bed_other"),      str(_bed_other),              "°C", "", True),
            _row(_("pdf.nozzle_first"),   fil.get("buse_1ere", "—"),   "°C", "", True),
            _row(_("pdf.nozzle_other"),   fil.get("buse_autres", "—"), "°C", "", True),
        ], {1, 2, 3, 4})
    ]))

    # ── Section 3 : Vitesse volumétrique ─────────────────────────────────
    story.append(KeepTogether(_section_title(_("pdf.sec_vol")) + [
        _table([
            _row(_("pdf.vol_max"),      fil.get("volumetrique_max", "—"), "mm³/s", ""),
            _row(_("pdf.vol_adaptive"), _("pdf.vol_disabled"), "", ""),
        ])
    ]))

    # ── Section 4 : Ventilateur ───────────────────────────────────────────
    story.append(KeepTogether(_section_title(_("pdf.sec_fan")) + [
        _table([
            _row(_("pdf.fan_first_layer"),  "0",                                           "%",    _("pdf.fan_first_note")),
            _row(_("pdf.fan_min"),          fil.get("ventilateur_seuil_mini", "—"),        "%",    ""),
            _row(_("pdf.fan_max_thresh"),   fil.get("ventilateur_max", "—"),               "%",    "", True),
            _row(_("pdf.fan_always"),       yn(fil.get("ventilation_active")),             "",     "", True),
            _row(_("pdf.fan_slow_cool"),    yn(fil.get("ralentir_refroidir")),             "",     ""),
            _row(_("pdf.fan_no_slow_outer"),yn(fil.get("ne_pas_ralentir_parois")),         "",     "", True),
            _row(_("pdf.fan_min_speed"),    fil.get("vitesse_min_impression", "—"),        "mm/s", ""),
            _row(_("pdf.fan_force_oh"),     yn(fil.get("forcer_ventilation_surplombs")),   "",     ""),
            _row(_("pdf.fan_oh_thresh"),    fil.get("ventiler_surplombs_depassant", "—"),  "%",    ""),
            _row(_("pdf.fan_oh_speed"),     fil.get("ventilateur_surplombs", "—"),         "%",    ""),
        ], {2, 3, 5})
    ]))

    # ── Section 5 : Rétraction ────────────────────────────────────────────
    ret_lon  = fil.get("retraction_longueur")
    ret_vit  = fil.get("retraction_vitesse")
    ret_rei  = fil.get("retraction_reinsertion")
    ret_dist = fil.get("retraction_distance_coupe")
    force_ret = ret_lon is not None

    story.append(KeepTogether(_section_title(_("pdf.sec_retract")) + [
        _table([
            _row(_("pdf.retract_len"),   f"{ret_lon} mm" if ret_lon else _("pdf.na_auto"), "", _("pdf.retract_force") if force_ret else "", force_ret),
            _row(_("pdf.retract_speed"), f"{ret_vit}" if ret_vit else _("pdf.na"),  "mm/s", "", force_ret),
            _row(_("pdf.retract_dsp"),   f"{ret_rei}" if ret_rei else _("pdf.na"),  "mm/s", "", force_ret),
            _row(_("pdf.retract_long"),  yn(fil.get("retraction_longue_coupe", False)), "",  ""),
            _row(_("pdf.retract_long_dist"), f"{ret_dist}" if ret_dist else _("pdf.na"), "mm", ""),
        ], {0, 1, 2} if force_ret else set())
    ]))

    sechage = fil.get("sechage", "")
    if sechage:
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph(_("pdf.drying", value=sechage), style("sech", 9, C_AMBER)))

    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=0.3, color=C_INACTIVE))
    story.append(Spacer(1, 0.15*cm))
    story.append(Paragraph(_("pdf.footer_note"), s_note))
    story.append(Spacer(1, 0.2*cm))
    from version import __version__
    story.append(Paragraph(_("pdf.generated_by", version=__version__), s_footer))

    # ── Build PDF ─────────────────────────────────────────────────────────
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm,
    )

    def _draw_bg(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(C_BG)
        canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
        canvas.restoreState()

    doc.build(story, onFirstPage=_draw_bg, onLaterPages=_draw_bg)
    logger.info(f"PDF généré : {output_path}")
    return True


def generate_full_report_pdf(
    filament_name: str,
    printer_name: str,
    config: "PrintConfig",
    analysis: "AnalysisReport",
    output_path: Path,
    plate_type: str = "Textured PEI Plate",
) -> bool:
    """Rapport complet : analyse géométrique + paramètres + filament."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.colors import HexColor, white
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph,
            Spacer, HRFlowable, KeepTogether, Image,
        )
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
    except ImportError:
        logger.error("reportlab non installé — pip install reportlab")
        return False

    from data.filaments import FILAMENTS
    from core.i18n import _

    fil = FILAMENTS.get(filament_name, {})

    C_BG       = HexColor("#070D14")
    C_PANEL    = HexColor("#0A1628")
    C_ELEVATED = HexColor("#0F1F35")
    C_ACCENT   = HexColor("#1E90FF")
    C_GREEN    = HexColor("#00FF9F")
    C_AMBER    = HexColor("#FFB800")
    C_RED      = HexColor("#FF3B3B")
    C_TEXT     = HexColor("#C8DCF0")
    C_MUTED    = HexColor("#4A7A9B")
    C_INACTIVE = HexColor("#1A3550")

    def style(name, size=9, color=C_TEXT, bold=False, align=TA_LEFT, leading=None):
        return ParagraphStyle(
            name, fontSize=size, textColor=color,
            fontName="Helvetica-Bold" if bold else "Helvetica",
            alignment=align, leading=leading or size * 1.35, spaceAfter=0,
        )

    s_title   = style("t",   16, C_ACCENT,  bold=True,  align=TA_CENTER)
    s_sub     = style("s",    9, C_MUTED,               align=TA_CENTER)
    s_section = style("sec", 10, C_ACCENT,  bold=True)
    s_warn    = style("w",    9, C_RED,     bold=True)
    s_cell    = style("c",    8, C_TEXT)
    s_cellhl  = style("ch",   8, white,     bold=True)
    s_cellmt  = style("cm",   8, C_MUTED)
    s_note    = style("n",    8, C_MUTED)
    s_footer  = style("f",    7, C_INACTIVE, align=TA_CENTER)

    COL_W = [5.8*cm, 3.5*cm, 1.5*cm, 5.2*cm]

    def _row(param, value, unit="", note="", hl=False):
        ps = s_cellhl if hl else s_cell
        ns = s_cellhl if hl else s_cellmt
        return [Paragraph(param, ps), Paragraph(str(value), ps),
                Paragraph(unit, ps), Paragraph(note, ns)]

    def _table(rows, hl_rows=None):
        hl_rows = hl_rows or set()
        hdr = [
            Paragraph(_("pdf.col_param"), style(f"hp", 8, C_MUTED, bold=True)),
            Paragraph(_("pdf.col_value"), style(f"hv", 8, C_MUTED, bold=True)),
            Paragraph(_("pdf.col_unit"),  style(f"hu", 8, C_MUTED, bold=True)),
            Paragraph(_("pdf.col_note"),  style(f"hn", 8, C_MUTED, bold=True)),
        ]
        data = [hdr] + rows
        ts = TableStyle([
            ("BACKGROUND", (0,0), (-1,0), C_ELEVATED),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [C_PANEL, C_BG]),
            ("GRID", (0,0), (-1,-1), 0.3, C_INACTIVE),
            ("TOPPADDING",    (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ("LEFTPADDING",   (0,0), (-1,-1), 6),
            ("RIGHTPADDING",  (0,0), (-1,-1), 6),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ])
        for i in hl_rows:
            ts.add("BACKGROUND", (0, i+1), (-1, i+1), C_ACCENT)
        t = Table(data, colWidths=COL_W, repeatRows=1)
        t.setStyle(ts)
        return t

    def _sec(text):
        return [
            Spacer(1, 0.3*cm),
            Paragraph(text, s_section),
            HRFlowable(width="100%", thickness=0.5, color=C_ACCENT, spaceAfter=4),
        ]

    def _score_color(score: float):
        if score >= 0.7:
            return C_GREEN
        if score >= 0.4:
            return C_AMBER
        return C_RED

    def yn(v):
        return _("pdf.yes") if v else _("pdf.no")

    story = []

    # ── En-tête ───────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.3*cm))
    _logo_path = _assets_dir() / "neoSlice.png"
    if _logo_path.exists():
        _logo = Image(str(_logo_path), width=2.8*cm, height=2.8*cm)
        _logo.hAlign = "CENTER"
        story.append(_logo)
    else:
        story.append(Paragraph("◈  NEOSLICE", s_title))
    story.append(Spacer(1, 0.1*cm))
    story.append(Paragraph(_("pdf.full_subtitle"), style("sub2", 11, C_TEXT, align=TA_CENTER)))
    story.append(Spacer(1, 0.1*cm))
    date_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    story.append(Paragraph(
        _("pdf.header_fmt", filament=filament_name, printer=printer_name, date=date_str),
        s_sub,
    ))
    story.append(Spacer(1, 0.4*cm))

    for w in fil.get("warnings", []):
        story.append(Paragraph(f"⚠  {w}", s_warn))
        story.append(Spacer(1, 0.08*cm))

    if fil.get("warnings"):
        story.append(Spacer(1, 0.15*cm))

    # ── Section 1 : Analyse géométrique ──────────────────────────────────
    bb = analysis.bounding_box_mm
    if analysis.overall_complexity < 0.25 and not analysis.support_needed:
        verdict = _("pdf.verdict_ok")
    elif analysis.overall_complexity < 0.55:
        verdict = _("pdf.verdict_warn")
    else:
        verdict = _("pdf.verdict_bad")

    geo_rows = [
        _row(_("pdf.dimensions"),  f"{bb[0]:.1f} × {bb[1]:.1f} × {bb[2]:.1f}", "mm"),
        _row(_("pdf.volume"),      f"{analysis.volume_cm3:.2f}", "cm³"),
        _row(_("pdf.surface"),     f"{analysis.surface_area_cm2:.1f}", "cm²"),
        _row(_("pdf.verdict"),     verdict, "", "", True),
        _row(_("pdf.overhangs"),   f"{analysis.overhang_severity * 100:.0f}%",  "",
             _("pdf.oh_angle", angle=f"{analysis.max_overhang_angle:.0f}")),
        _row(_("pdf.stability"),   f"{analysis.stability_score * 100:.0f}%",    "", ""),
        _row(_("pdf.fragility"),   f"{analysis.fragility_severity * 100:.0f}%", "",
             _("pdf.min_wall", t=f"{analysis.min_wall_thickness_mm:.1f}") if analysis.has_fragile_zones else ""),
        _row(_("pdf.supports_needed"),
             _("pdf.supp_on") if analysis.support_needed else _("pdf.supp_off"),
             "", _("pdf.supp_vol", r=f"{analysis.estimated_support_ratio*100:.0f}") if analysis.support_needed else "",
             analysis.support_needed),
        _row(_("pdf.orient_suggested"),
             analysis.orientation_label or _("pdf.orient_current"), "",
             _("pdf.orient_improve", pct=f"{analysis.orientation_improvement_pct:.0f}") if analysis.orientation_improvement_pct > 1 else ""),
    ]
    story.append(KeepTogether(_sec(_("pdf.sec_geometry")) + [_table(geo_rows, {3})]))

    # ── Section 2 : Paramètres d'impression ──────────────────────────────
    height_mm = bb[2] if len(bb) > 2 else 20.0
    sup_ratio = analysis.estimated_support_ratio if analysis.support_needed else 0.0
    est_min   = config.estimated_time_minutes(analysis.volume_cm3, height_mm, sup_ratio)
    h, m = divmod(int(est_min), 60)
    time_str = f"~{h}h{m:02d}" if h > 0 else f"~{m} min"
    fil_g = config.estimated_filament_g(analysis.volume_cm3)

    param_rows = [
        _row(_("pdf.time_est"),      time_str, "", _("pdf.time_with_supp") if analysis.support_needed else ""),
        _row(_("pdf.filament_est"),  f"~{fil_g:.0f}", "g"),
        _row(_("pdf.layer_h"),       f"{config.layer_height:.2f}", "mm"),
        _row(_("pdf.infill"),        f"{config.infill_density}", "%"),
        _row(_("pdf.wall_loops"),    f"{config.wall_loops}", ""),
        _row(_("pdf.top_bot_layers"),f"{config.top_shell_layers} / {config.bottom_shell_layers}", ""),
        _row(_("pdf.outer_wall_spd"),f"{config.outer_wall_speed}", "mm/s"),
        _row(_("pdf.infill_spd"),    f"{config.infill_speed}", "mm/s"),
        _row(_("pdf.supports"),
             _("pdf.supp_off") if config.support_type == "none" else _("pdf.supp_on"),
             "", "" if config.support_type == "none" else config.support_type),
        _row(_("pdf.brim"),          f"{config.brim_width}", "mm"),
        _row(_("pdf.profile_name"),  config.neoslice_profile_name, ""),
    ]
    story.append(KeepTogether(_sec(_("pdf.sec_params")) + [_table(param_rows)]))

    # ── Section 3 : Températures filament ────────────────────────────────
    _bed_first, _bed_other = _get_bed_temps(plate_type, filament_name, fil.get("plateau", "—"))
    _plate_label = _PLATE_DISPLAY.get(plate_type, plate_type)
    story.append(KeepTogether(_sec(_("pdf.sec_filament_temp")) + [
        _table([
            _row(_("pdf.plate_selected"),  _plate_label,                 "",   ""),
            _row(_("pdf.bed_first2"),      str(_bed_first),              "°C", "", True),
            _row(_("pdf.bed_other2"),      str(_bed_other),              "°C", "", True),
            _row(_("pdf.nozzle_first2"),   fil.get("buse_1ere", "—"),   "°C", "", True),
            _row(_("pdf.nozzle_other2"),   fil.get("buse_autres", "—"), "°C", "", True),
        ], {1, 2, 3, 4})
    ]))

    # ── Section 4 : Ventilateur ───────────────────────────────────────────
    story.append(KeepTogether(_sec(_("pdf.sec_filament_fan")) + [
        _table([
            _row(_("pdf.fan_max"),    fil.get("ventilateur_max", "—"),        "%",    "", True),
            _row(_("pdf.fan_always2"),yn(fil.get("ventilation_active")),       "",    "", True),
            _row(_("pdf.fan_min2"),   fil.get("ventilateur_seuil_mini", "—"), "%"),
            _row(_("pdf.print_min_spd"), fil.get("vitesse_min_impression", "—"), "mm/s"),
        ], {0, 1})
    ]))

    # ── Section 5 : Rétraction ────────────────────────────────────────────
    ret_lon = fil.get("retraction_longueur")
    ret_vit = fil.get("retraction_vitesse")
    if ret_lon is not None:
        story.append(KeepTogether(_sec(_("pdf.sec_filament_ret")) + [
            _table([
                _row(_("pdf.retract_len2"),   f"{ret_lon}", "mm",   _("pdf.retract_force2"), True),
                _row(_("pdf.retract_speed2"), f"{ret_vit}", "mm/s", "",                      True),
            ], {0, 1})
        ]))

    sechage = fil.get("sechage", "")
    if sechage:
        story.append(Spacer(1, 0.25*cm))
        story.append(Paragraph(_("pdf.drying", value=sechage), style("sech", 9, C_AMBER)))

    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=0.3, color=C_INACTIVE))
    story.append(Spacer(1, 0.15*cm))
    from version import __version__
    story.append(Paragraph(_("pdf.generated_by", version=__version__), s_footer))

    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm,
    )

    def _draw_bg(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(C_BG)
        canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
        canvas.restoreState()

    doc.build(story, onFirstPage=_draw_bg, onLaterPages=_draw_bg)
    logger.info(f"Rapport complet PDF généré : {output_path}")
    return True
