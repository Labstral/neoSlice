"""Génère la fiche de réglages filament et le rapport complet en PDF avec reportlab."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from core.geometry.analysis_report import AnalysisReport
    from core.parameters.print_config import PrintConfig


def generate_filament_pdf(
    filament_name: str,
    printer_name: str,
    output_path: Path,
) -> bool:
    """Génère le PDF et retourne True si succès."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.colors import HexColor, white, black
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph,
            Spacer, HRFlowable,
        )
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
    except ImportError:
        logger.error("reportlab non installé — pip install reportlab")
        return False

    from data.filaments import FILAMENTS

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
            Paragraph("Paramètre", style("hdr", 8, C_MUTED, bold=True)),
            Paragraph("Valeur",    style("hdr", 8, C_MUTED, bold=True)),
            Paragraph("Unité",     style("hdr", 8, C_MUTED, bold=True)),
            Paragraph("Note",      style("hdr", 8, C_MUTED, bold=True)),
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
            row_idx = i + 1  # +1 pour le header
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

    # ── Contenu ───────────────────────────────────────────────────────────
    story = []

    # En-tête
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("◈  NEOSLICE", s_title))
    story.append(Spacer(1, 0.15*cm))
    story.append(Paragraph("Fiche de réglages filament", style("sub2", 11, C_TEXT, align=TA_CENTER)))
    story.append(Spacer(1, 0.15*cm))
    date_str = datetime.now().strftime("%d/%m/%Y")
    story.append(Paragraph(
        f"Filament : <b>{filament_name}</b>  |  Imprimante : <b>{printer_name}</b>  |  {date_str}",
        s_sub,
    ))
    story.append(Spacer(1, 0.5*cm))

    # Warnings
    warnings = fil.get("warnings", [])
    if warnings:
        for w in warnings:
            story.append(Paragraph(f"⚠  {w}", s_warn))
            story.append(Spacer(1, 0.1*cm))
        story.append(Spacer(1, 0.2*cm))

    # ── Section 1 : Informations de base ──────────────────────────────────
    story.extend(_section_title("Onglet Filament › Informations de base"))
    rapport = fil.get("rapport_debit", 0.98)
    hl_rapport = {0} if rapport != 1.0 else set()
    story.append(_table([
        _row("Rapport de débit",        f"{rapport:.2f}", "",   "Ajuster si sous/sur-extrusion", rapport != 1.0),
        _row("Température de ramollissement", fil.get("ramollissement", "—"), "°C", ""),
    ], hl_rapport))

    # ── Section 2 : Températures ──────────────────────────────────────────
    story.extend(_section_title("Onglet Filament › Température d'impression"))
    story.append(_table([
        _row("Textured PEI Plate — 1ère couche",  fil.get("plateau", "—"),       "°C", "HIGHLIGHT", True),
        _row("Textured PEI Plate — autres couches", fil.get("plateau", "—"),     "°C", "HIGHLIGHT", True),
        _row("Buse — 1ère couche",                 fil.get("buse_1ere", "—"),    "°C", "HIGHLIGHT", True),
        _row("Buse — Autres couches",               fil.get("buse_autres", "—"), "°C", "HIGHLIGHT", True),
    ], {0, 1, 2, 3}))

    # ── Section 3 : Vitesse volumétrique ─────────────────────────────────
    story.extend(_section_title("Onglet Filament › Vitesse volumétrique"))
    story.append(_table([
        _row("Vitesse volumétrique maximale",   fil.get("volumetrique_max", "—"), "mm³/s", ""),
        _row("Vitesse volumétrique adaptative", "Désactivée", "", ""),
    ]))

    # ── Section 4 : Ventilateur ───────────────────────────────────────────
    story.extend(_section_title("Onglet Refroidissement › Ventilateur de pièce"))

    def yn(v): return "Oui" if v else "Non"

    vent_rows = [
        _row("Ventilateur 1ère couche",           "0",                                    "%",    "Ne jamais ventiler 1ère couche"),
        _row("Seuil mini du ventilateur",          fil.get("ventilateur_seuil_mini", "—"), "%",    ""),
        _row("Seuil vitesse MAX ventilateur",      fil.get("ventilateur_max", "—"),        "%",    "", True),
        _row("Ventilation toujours active",        yn(fil.get("ventilation_active")),      "",     "", True),
        _row("Ralentir pour refroidir",            yn(fil.get("ralentir_refroidir")),      "",     ""),
        _row("Ne pas ralentir parois externes",    yn(fil.get("ne_pas_ralentir_parois")), "",     "", True),
        _row("Vitesse d'impression minimale",      fil.get("vitesse_min_impression", "—"), "mm/s", ""),
        _row("Forcer ventilation surplombs",       yn(fil.get("forcer_ventilation_surplombs")), "", ""),
        _row("Ventiler surplombs dépassant",       fil.get("ventiler_surplombs_depassant", "—"), "%", ""),
        _row("Vitesse ventilateur surplombs",      fil.get("ventilateur_surplombs", "—"), "%",    ""),
    ]
    story.append(_table(vent_rows, {2, 3, 5}))

    # ── Section 5 : Rétraction ────────────────────────────────────────────
    story.extend(_section_title("Onglet Forçage des réglages › Rétraction"))

    ret_lon = fil.get("retraction_longueur")
    ret_vit = fil.get("retraction_vitesse")
    ret_rei = fil.get("retraction_reinsertion")
    ret_dist = fil.get("retraction_distance_coupe")
    force_ret = ret_lon is not None

    ret_rows = [
        _row("Longueur de rétraction",     f"{ret_lon} mm" if ret_lon else "N/A (géré auto)", "",     "FORCER si indiqué" if force_ret else "", force_ret),
        _row("Vitesse de rétraction",      f"{ret_vit}" if ret_vit else "N/A",                "mm/s", "", force_ret),
        _row("Vitesse de réinsertion",     f"{ret_rei}" if ret_rei else "N/A",                "mm/s", "", force_ret),
        _row("Rétraction longue (coupe)",  yn(fil.get("retraction_longue_coupe", False)),     "",     ""),
        _row("Distance rétraction coupe",  f"{ret_dist}" if ret_dist else "N/A",              "mm",   ""),
    ]
    hl_ret = {0, 1, 2} if force_ret else set()
    story.append(_table(ret_rows, hl_ret))

    # Note séchage
    sechage = fil.get("sechage", "")
    if sechage:
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph(f"Séchage recommandé : {sechage}", style("sech", 9, C_AMBER)))

    # Note finale
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=0.3, color=C_INACTIVE))
    story.append(Spacer(1, 0.15*cm))
    story.append(Paragraph(
        "Les paramètres d'impression (qualité, vitesse, supports, adhérence) sont intégrés "
        "dans le fichier 3MF généré par neoSlice et ne nécessitent pas de configuration "
        "manuelle dans Bambu Studio.",
        s_note,
    ))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("Généré par neoSlice v0.1.0", s_footer))

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
) -> bool:
    """Rapport complet : analyse géométrique + paramètres + filament."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.colors import HexColor, white
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph,
            Spacer, HRFlowable,
        )
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
    except ImportError:
        logger.error("reportlab non installé — pip install reportlab")
        return False

    from data.filaments import FILAMENTS

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
        hdr = [Paragraph(h, style(f"h{h}", 8, C_MUTED, bold=True))
               for h in ("Paramètre", "Valeur", "Unité", "Note")]
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

    story = []

    # ── En-tête ───────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("◈  NEOSLICE", s_title))
    story.append(Spacer(1, 0.1*cm))
    story.append(Paragraph("Rapport d'impression complet", style("sub2", 11, C_TEXT, align=TA_CENTER)))
    story.append(Spacer(1, 0.1*cm))
    date_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    story.append(Paragraph(
        f"Filament : <b>{filament_name}</b>  |  Imprimante : <b>{printer_name}</b>  |  {date_str}",
        s_sub,
    ))
    story.append(Spacer(1, 0.4*cm))

    warnings = fil.get("warnings", [])
    for w in warnings:
        story.append(Paragraph(f"⚠  {w}", s_warn))
        story.append(Spacer(1, 0.08*cm))

    # ── Section 1 : Analyse géométrique ──────────────────────────────────
    story.extend(_sec("Analyse géométrique"))
    bb = analysis.bounding_box_mm
    verdict = ("PRÊT À IMPRIMER" if analysis.overall_complexity < 0.25 and not analysis.support_needed
               else "VÉRIFIER AVANT IMPRESSION" if analysis.overall_complexity < 0.55
               else "PIÈCE COMPLEXE")
    geo_rows = [
        _row("Dimensions (X × Y × Z)", f"{bb[0]:.1f} × {bb[1]:.1f} × {bb[2]:.1f}", "mm"),
        _row("Volume pièce",  f"{analysis.volume_cm3:.2f}", "cm³"),
        _row("Surface",       f"{analysis.surface_area_cm2:.1f}", "cm²"),
        _row("Verdict global", verdict, "", "", True),
        _row("Surplombs",     f"{analysis.overhang_severity * 100:.0f}%",  "", f"Angle max {analysis.max_overhang_angle:.0f}°"),
        _row("Stabilité",     f"{analysis.stability_score * 100:.0f}%",    "", ""),
        _row("Fragilité",     f"{analysis.fragility_severity * 100:.0f}%", "", f"Paroi min {analysis.min_wall_thickness_mm:.1f} mm" if analysis.has_fragile_zones else ""),
        _row("Supports requis", "OUI" if analysis.support_needed else "NON",
             "", f"Volume estimé {analysis.estimated_support_ratio*100:.0f}%", analysis.support_needed),
        _row("Orientation conseillée", analysis.orientation_label or "Actuelle (Z+)", "",
             f"+{analysis.orientation_improvement_pct:.0f}%" if analysis.orientation_improvement_pct > 1 else ""),
    ]
    story.append(_table(geo_rows, {3}))

    # ── Section 2 : Paramètres d'impression ──────────────────────────────
    story.extend(_sec("Paramètres d'impression (générés par neoSlice)"))
    height_mm = bb[2] if len(bb) > 2 else 20.0
    sup_ratio = analysis.estimated_support_ratio if analysis.support_needed else 0.0
    est_min   = config.estimated_time_minutes(analysis.volume_cm3, height_mm, sup_ratio)
    h, m = divmod(int(est_min), 60)
    time_str = f"~{h}h{m:02d}" if h > 0 else f"~{m} min"
    fil_g = config.estimated_filament_g(analysis.volume_cm3)

    param_rows = [
        _row("Temps estimé",        time_str,                             "", "avec supports" if analysis.support_needed else ""),
        _row("Filament estimé",     f"~{fil_g:.0f}",                     "g"),
        _row("Hauteur de couche",   f"{config.layer_height:.2f}",        "mm"),
        _row("Remplissage",         f"{config.infill_density}",          "%"),
        _row("Boucles de paroi",    f"{config.wall_loops}",              ""),
        _row("Couches sup./inf.",   f"{config.top_shell_layers} / {config.bottom_shell_layers}", ""),
        _row("Vitesse paroi ext.",  f"{config.outer_wall_speed}",        "mm/s"),
        _row("Vitesse remplissage", f"{config.infill_speed}",            "mm/s"),
        _row("Supports",            "Activés" if config.enable_support else "Désactivés",
             "", config.support_type if config.enable_support else ""),
        _row("Adhérence (brim)",    f"{config.brim_width}",              "mm"),
        _row("Profil neoSlice",     config.neoslice_profile_name,        ""),
    ]
    story.append(_table(param_rows))

    # ── Section 3 : Températures filament ────────────────────────────────
    story.extend(_sec("Réglages filament — Températures"))
    story.append(_table([
        _row("Plateau — 1ère couche",    fil.get("plateau", "—"),       "°C", "", True),
        _row("Plateau — autres couches", fil.get("plateau", "—"),       "°C", "", True),
        _row("Buse — 1ère couche",       fil.get("buse_1ere", "—"),     "°C", "", True),
        _row("Buse — autres couches",    fil.get("buse_autres", "—"),   "°C", "", True),
    ], {0, 1, 2, 3}))

    # ── Section 4 : Ventilateur ───────────────────────────────────────────
    story.extend(_sec("Réglages filament — Ventilateur"))
    def yn(v): return "Oui" if v else "Non"
    story.append(_table([
        _row("Vitesse MAX ventilateur",   fil.get("ventilateur_max", "—"),   "%", "", True),
        _row("Ventilation toujours active", yn(fil.get("ventilation_active")), "", "", True),
        _row("Seuil mini ventilateur",    fil.get("ventilateur_seuil_mini", "—"), "%"),
        _row("Vitesse d'impression min.", fil.get("vitesse_min_impression", "—"), "mm/s"),
    ], {0, 1}))

    # ── Section 5 : Rétraction ────────────────────────────────────────────
    ret_lon = fil.get("retraction_longueur")
    ret_vit = fil.get("retraction_vitesse")
    if ret_lon is not None:
        story.extend(_sec("Réglages filament — Rétraction"))
        story.append(_table([
            _row("Longueur de rétraction", f"{ret_lon}", "mm", "FORCER", True),
            _row("Vitesse de rétraction",  f"{ret_vit}", "mm/s", "", True),
        ], {0, 1}))

    sechage = fil.get("sechage", "")
    if sechage:
        story.append(Spacer(1, 0.25*cm))
        story.append(Paragraph(f"Séchage recommandé : {sechage}", style("sech", 9, C_AMBER)))

    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=0.3, color=C_INACTIVE))
    story.append(Spacer(1, 0.15*cm))
    story.append(Paragraph("Généré par neoSlice v0.1.0", s_footer))

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
