"""Système de traduction neoSlice — FR / EN.

Usage :
    from core.i18n import _
    label = _("drop.main")
    msg   = _("orient.apply_fmt", label="Z+", improvement=35.0)

La langue est chargée une fois au démarrage depuis prefs.json.
Un changement de langue nécessite un redémarrage.
"""
from __future__ import annotations

# ── Français ──────────────────────────────────────────────────────────────────

_FR: dict[str, str] = {

    # ── Application / TopBar ──────────────────────────────────────────────────
    "app.title":            "neoSlice",
    "app.subtitle":         "AI-POWERED 3D PRINT OPTIMIZER",
    "app.btn_new_piece":    "↺  NOUVELLE PIÈCE",
    "app.btn_diag":         "DIAGNOSTIC IA",
    "app.tip_feedback":     "Envoyer un retour / signaler un bug",
    "app.tip_guide":        "Guide d'utilisation",
    "app.tip_coffee":       "À propos / Soutenir le développement",
    "app.tip_settings":     "Paramètres",

    # ── StatusBar ─────────────────────────────────────────────────────────────
    "status.initial":           "SYSTÈME PRÊT — SÉLECTIONNER L'IMPRIMANTE CIBLE  ①",
    "status.ready":             "PRÊT — GLISSER UN NOUVEAU FICHIER STL",
    "status.loading":           "Modèle chargé — {name} — analyse en cours...",
    "status.analysis_ok":       "Analyse OK ({ms:.0f} ms){oh_tag} — Réglages suggérés · affinez votre intention ③",
    "status.analysis_err":      "Erreur analyse : {msg}",
    "status.analysis_timeout":  "Analyse interrompue (timeout 60 s) — relancez l'application si le problème persiste",
    "status.printer_confirmed": "Imprimante confirmée — sélectionner le filament  ②",
    "status.filament_confirmed":"Filament confirmé — charger un fichier STL  ③",
    "status.orient_applying":   "Application de l'orientation...",
    "status.orient_done":       "Orientation appliquée — mise à jour de l'analyse...",
    "status.orient_reset":      "Orientation réinitialisée — ré-analyse en cours...",
    "status.orient_err":        "Erreur orientation : {msg}",
    "status.exporting":         "Export en cours...",
    "status.export_ok":         ".3MF exporté",
    "status.export_ok_warn":    ".3MF exporté ({msg})",
    "status.export_err":        "Erreur export : {msg}",
    "status.gen_err":           "Erreur génération : {msg}",
    "status.oh_tag":            " | surplombs {pct:.1f}%",

    # ── Export / Success Dialog ────────────────────────────────────────────────
    "export.btn":               "↓  EXPORTER .3MF  →  {slicer}",
    "export.dialog_title":      "Enregistrer le fichier .3MF",
    "export.dialog_filter":     "Fichiers 3MF (*.3mf)",
    "export.success_title":     "✓   Fichier 3MF généré avec succès",
    "export.success_info":      (
        "Les paramètres d'impression (qualité, vitesse, supports…) sont intégrés dans le 3MF.<br>"
        "Les paramètres du <b>filament</b> (températures, ventilation, débit) doivent être "
        "configurés manuellement dans votre slicer."
    ),
    "export.dlg_title":         "Fichier .3MF généré",
    "export.btn_bambu":         "  Ouvrir dans Bambu Studio",
    "export.btn_orca":          "  Ouvrir dans OrcaSlicer",
    "export.btn_prusa":         "  Ouvrir dans PrusaSlicer",
    "export.btn_pdf":           "  Fiche filament PDF",
    "export.btn_close":         "Fermer",

    # ── DropZone ─────────────────────────────────────────────────────────────
    "drop.main_locked":     "VALIDEZ L'IMPRIMANTE",
    "drop.sub_locked":      "et le filament pour continuer",
    "drop.step_locked":     "Étape ①",
    "drop.main":            "GLISSER FICHIER STL / 3MF",
    "drop.sub":             "ou cliquer pour parcourir",
    "drop.dialog_title":    "Ouvrir un fichier 3D",
    "drop.dialog_filter":   "Fichiers 3D (*.stl *.obj *.3mf);;Tous les fichiers (*)",
    "drop.reopen":          "↺  Réouvrir : {name}",
    "drop.sub_loaded":      "cliquer pour changer",

    # ── AnalysisPanel ────────────────────────────────────────────────────────
    "analysis.dot_system":  "SYSTÈME",
    "analysis.dot_stl":     "STL",
    "analysis.dot_analysis":"ANALYSE",
    "analysis.dot_gen":     "GÉNÉRATION",
    "analysis.gauge_oh":    "Surplombs",
    "analysis.gauge_stab":  "Stabilité",
    "analysis.gauge_frag":  "Fragilité",
    "analysis.gauge_supp":  "Vol. support",
    "analysis.default_val": "———",
    "analysis.dim_x":       "X",
    "analysis.dim_y":       "Y",
    "analysis.dim_z":       "Z",
    "analysis.vol":         "VOL",
    "analysis.faces":       "FACES",
    "analysis.orient_btn":  "↻  Appliquer l'orientation recommandée",
    "analysis.progress_init": "Initialisation...",
    "analysis.verdict_ok":  "✓  PRÊT À IMPRIMER",
    "analysis.verdict_warn":"⚠  CONFIGURATION ADAPTÉE — CONTRÔLER DANS VOTRE SLICER",
    "analysis.verdict_bad": "⛔  PIÈCE COMPLEXE — ATTENTION",

    "analysis.status_floating":   "⛔ Régions flottantes — supports générés automatiquement",
    "analysis.status_supp_req":   "⚠ Supports requis ({pct:.1f}% surplombs)",
    "analysis.status_supp_mod":   "⚠ Surplombs modérés ({pct:.1f}%) — vérifier supports",
    "analysis.status_oh_ok":      "✓ Pas de surplombs significatifs",
    "analysis.status_stab_low":   "⚠ Stabilité faible — brim ajouté à la configuration",
    "analysis.status_stab_med":   "⚠ Stabilité modérée — brim conseillé",
    "analysis.status_stab_ok":    "✓ Stable — brim non nécessaire",
    "analysis.status_frag":       "⚠ Parois fines — min {min_t} mm (rec. {rec_t} mm)",
    "analysis.status_flat":       "⚠ Pièce plate — risque warping",
    "analysis.status_orient":     "↻ Orientation optimale : {label} (+{imp:.0f}%)",
    "analysis.orient_apply_fmt":  "↻  Appliquer — {label}  (+{imp:.0f}%)",
    "analysis.loading_label":     "◌  ANALYSE EN COURS",
    "analysis.loading_pct":       "ANALYSE EN COURS",
    "analysis.orientation_applied_info": "Brim large (10+ mm) et plateau chauffé recommandés.",
    "analysis.disabled":        "DÉSACTIVÉ",
    "analysis.lite_mode_warn":  "⚠ Mode Économique — surplombs non analysés · vérifiez les supports dans votre slicer",

    "analysis.tip_oh":   (
        "Surplombs : zones inclinées à plus de 45° sans matière en-dessous.\n"
        "Élevé → activez les supports dans votre slicer pour éviter l'effondrement."
    ),
    "analysis.tip_stab": (
        "Stabilité sur le plateau : plus c'est haut, mieux la pièce tient.\n"
        "Faible → risque de décollement en cours d'impression → utilisez un brim."
    ),
    "analysis.tip_frag": (
        "Épaisseur minimale des parois détectée dans la pièce.\n"
        "La valeur affichée est l'épaisseur réelle (en mm).\n"
        "En dessous de 1,2 mm → risque de cassure ou mauvaise impression → augmentez les parois."
    ),
    "analysis.tip_supp": (
        "Volume de matière support nécessaire par rapport à la pièce.\n"
        "Élevé → plus de filament consommé et temps d'impression plus long."
    ),

    # ── Viewer 3D ─────────────────────────────────────────────────────────────
    "viewer.loading_default":   "ANALYSE EN COURS...",
    "viewer.loading_sub":       "CALCUL EN COURS — VEUILLEZ PATIENTER",
    "viewer.no_pyvista":        "Visualisation 3D\n\nInstallez pyvistaqt pour activer le viewer :\npip install pyvistaqt",
    "viewer.show_plate":        "Plateau",
    "viewer.auto_rotate":       "Rotation auto",
    "viewer.orient_btn":        "↻  Appliquer l'orientation optimale",
    "viewer.orient_optimal":    "✓  Orientation actuelle : optimale",
    "viewer.orient_apply_lbl":  "↻  {label}",
    "viewer.orient_reset":      "↩  Réinitialiser l'orientation",
    "viewer.loading_orient":    "OPTIMISATION DE L'ORIENTATION...",
    "viewer.loading_analysis":  "ANALYSE DE LA PIÈCE EN COURS...",

    # ── IntentSelector ────────────────────────────────────────────────────────
    # Groupes
    "intent.group_quality":     "QUALITÉ",
    "intent.group_strength":    "RÉSISTANCE",
    "intent.group_speed":       "VITESSE",
    "intent.group_adhesion":    "ADHÉRENCE",
    "intent.group_usage":       "USAGE",
    "intent.group_mode":        "MODE",

    # Qualité
    "intent.q_draft":           "Brouillon",
    "intent.q_draft_desc":      "0.28mm — prototype uniquement",
    "intent.q_standard":        "Standard",
    "intent.q_standard_desc":   "0.20mm — équilibre vitesse / qualité",
    "intent.q_fine":            "Fine",
    "intent.q_fine_desc":       "0.12mm — bonne finition de surface",
    "intent.q_ultra":           "Ultra Fine",
    "intent.q_ultra_desc":      "0.08mm — finition maximale, lent",

    # Résistance
    "intent.s_light":           "Légère",
    "intent.s_light_desc":      "Parois minimales, économie de matière",
    "intent.s_standard":        "Standard",
    "intent.s_standard_desc":   "Solidité normale pour usage courant",
    "intent.s_strong":          "Renforcée",
    "intent.s_strong_desc":     "Parois + infill augmentés (cubic)",
    "intent.s_ultra":           "Ultra Solide",
    "intent.s_ultra_desc":      "Résistance maximale — gyroid 80%",

    # Vitesse
    "intent.sp_standard":       "Standard",
    "intent.sp_standard_desc":  "Vitesses Bambu Lab recommandées",
    "intent.sp_fast":           "Rapide",
    "intent.sp_fast_desc":      "+50% vitesse — qualité légèrement réduite",
    "intent.sp_ultra":          "Ultra Rapide",
    "intent.sp_ultra_desc":     "Vitesse maximale — prototype seulement",

    # Adhérence
    "intent.a_none":            "Aucune",
    "intent.a_none_desc":       "Pas de brim — pièce stable uniquement",
    "intent.a_brim5":           "Brim 5mm",
    "intent.a_brim5_desc":      "Brim standard — stabilité modérée",
    "intent.a_brim10":          "Brim 10mm",
    "intent.a_brim10_desc":     "Brim large — pièces hautes ou fragiles",

    # Usage
    "intent.u_indoor":          "Intérieur standard",
    "intent.u_indoor_desc":     "Paramètres PLA optimaux",
    "intent.u_outdoor":         "Extérieur / UV",
    "intent.u_outdoor_desc":    "Gyroid renforcé, températures PETG/ASA",
    "intent.u_visible":         "Finition visible",
    "intent.u_visible_desc":    "Ironing, coutures dans le dos",
    "intent.u_precision":       "Assemblage précis",
    "intent.u_precision_desc":  "Arachne + compensation XY serrée",

    # Mode
    "intent.m_standard":        "Standard",
    "intent.m_standard_desc":   "Aucun mode spécial",
    "intent.m_silent":          "Silencieux",
    "intent.m_silent_desc":     "Vitesses -40% — impression discrète",
    "intent.m_multicolor":      "Multicolore (AMS)",
    "intent.m_multicolor_desc": "Prime tower + flush optimisé",

    "intent.group_support":      "SUPPORTS",
    "intent.sup_auto":           "Auto",
    "intent.sup_auto_desc":      "Le logiciel décide selon la géométrie",
    "intent.sup_classic":        "Classique",
    "intent.sup_classic_desc":   "Colonnes standards, faciles à retirer",
    "intent.sup_tree":           "Arborescent",
    "intent.sup_tree_desc":      "Organique, moins de marques sur la pièce",
    "intent.sup_none":          "Sans support",
    "intent.sup_none_desc":     "Force l'absence de supports même si la pièce en a besoin",

    # UI
    "intent.lock_msg":          "CHARGEZ UN FICHIER STL",
    "intent.lock_sub":          "pour accéder aux réglages",
    "intent.lock_step":         "Étape ②",
    "intent.presets_header":    "★  MES PRÉSETS",
    "intent.presets_empty":     "Aucun préset — sauvegardez vos réglages favoris",
    "intent.auto_select_msg":   "✦  Réglages pré-sélectionnés selon l'analyse — modifiez-les si besoin",
    "intent.btn_save":          "★  SAUVEGARDER",
    "intent.btn_generate":      "GÉNÉRER CONFIGURATION →",
    "intent.btn_conflicts":     "⛔  RÉSOLVEZ LES CONFLITS",
    "intent.btn_loading":       "◌  GÉNÉRATION EN COURS...",
    "intent.save_dialog_title": "Sauvegarder le préset",
    "intent.save_dialog_label": "Nom du préset :",

    # Conflits
    "intent.conflict_ultra_fine_ultra_fast": (
        "Ultra Fine + Ultra Rapide sont incompatibles — la qualité sera celle du Brouillon."
    ),
    "intent.conflict_ultra_fine_ultra_fast_hint": (
        "Essayez : Fine + Rapide  ou  Standard + Ultra Rapide"
    ),
    "intent.conflict_fine_fast_warn": (
        "Ultra Fine avec vitesse Rapide peut dégrader légèrement la finition."
    ),
    "intent.conflict_fine_fast_hint": "Compromis : Fine + Rapide pour un bon équilibre",
    "intent.conflict_fine_ultra_fast": (
        "Fine + Ultra Rapide donnera effectivement une qualité Standard."
    ),
    "intent.conflict_fine_ultra_fast_hint": (
        "Compromis : Fine + Rapide  ou  Standard + Ultra Rapide"
    ),
    "intent.conflict_ultra_solid_ultra_fast": (
        "Ultra Solide + Ultra Rapide sont incompatibles — les parois épaisses ont besoin de temps."
    ),
    "intent.conflict_ultra_solid_ultra_fast_hint": (
        "Essayez : Renforcée + Rapide  ou  Ultra Solide + Standard"
    ),
    "intent.conflict_solid_light": "Ultra Solide et Légère sont contradictoires.",
    "intent.conflict_solid_light_hint": "Choisissez l'un ou l'autre selon votre besoin",
    "intent.conflict_light_outdoor": (
        "Une pièce Légère est déconseillée pour un usage extérieur."
    ),
    "intent.conflict_light_outdoor_hint": (
        "Recommandé : Standard ou Renforcée + Extérieur"
    ),
    "intent.conflict_draft_visible": (
        "Brouillon + Finition visible : la résolution 0.28mm ne donnera pas une belle finition."
    ),
    "intent.conflict_draft_visible_hint": (
        "Utilisez au minimum la qualité Standard pour une pièce visible"
    ),
    "intent.conflict_ultra_fast_visible": (
        "Ultra Rapide dégrade les coutures et la finition de surface."
    ),
    "intent.conflict_ultra_fast_visible_hint": (
        "Recommandé : Standard ou Rapide pour une pièce visible"
    ),

    # ── ParamsPreview ────────────────────────────────────────────────────────
    "preview.empty_title":  "AUCUN PARAMÈTRE GÉNÉRÉ",
    "preview.empty_desc":   (
        "Importez un fichier STL\npuis décrivez votre intention\n"
        "pour générer la configuration."
    ),
    "preview.summary_title":        "EN RÉSUMÉ",
    "preview.row_time":             "Temps estimé",
    "preview.row_filament":         "Filament estimé",
    "preview.row_quality":          "Qualité d'impression",
    "preview.row_strength":         "Solidité / remplissage",
    "preview.row_adhesion":         "Adhérence plateau",
    "preview.row_supports":         "Supports",
    "preview.row_temps":            "Températures",
    "preview.quality_ultra":        "Ultra Fine ({h} mm)",
    "preview.quality_fine":         "Fine ({h} mm)",
    "preview.quality_standard":     "Standard ({h} mm)",
    "preview.quality_draft":        "Brouillon ({h} mm)",
    "preview.fill_light":           "Léger — {d} %",
    "preview.fill_standard":        "Standard — {d} %",
    "preview.fill_strong":          "Renforcé — {d} %",
    "preview.fill_dense":           "Très dense — {d} %",
    "preview.adhesion_none":        "Sans brim",
    "preview.adhesion_brim":        "Brim {w} mm",
    "preview.support_none":         "Sans support",
    "preview.support_tree":         "Arborescent",
    "preview.support_normal":       "Supports normaux",
    "preview.support_classic":      "Classique",
    "preview.support_auto_none":    "Auto — Sans support",
    "preview.support_auto_tree":    "Auto — Arborescent",
    "preview.support_auto_normal":  "Auto — Classique",
    "preview.support_forced_none":  "Sans support (forcé)",
    "preview.temps_fmt":            "{nozzle}°C buse / {bed}°C plateau",

    # Sections
    "preview.sec_mission":      "MISSION PROFILE",
    "preview.lbl_printer":      "IMPRIMANTE",
    "preview.lbl_profile":      "PROFIL",
    "preview.lbl_intent":       "INTENTION",
    "preview.lbl_confidence":   "CONFIANCE",

    "preview.sec_layers":       "COUCHES",
    "preview.lbl_layer_h":      "HAUTEUR COUCHE",
    "preview.lbl_first_layer":  "PREMIÈRE COUCHE",
    "preview.lbl_wall_gen":     "GÉNÉRATEUR PAROI",
    "preview.lbl_wall_seq":     "SÉQUENCE PAROI",

    "preview.sec_structure":    "STRUCTURE",
    "preview.lbl_walls":        "PAROIS",
    "preview.lbl_top_shells":   "COQUES SUP.",
    "preview.lbl_bot_shells":   "COQUES INF.",
    "preview.lbl_single_top":   "PAROI UNIQUE DESSUS",
    "preview.val_yes":          "OUI",
    "preview.val_no":           "NON",

    "preview.sec_infill":       "REMPLISSAGE",
    "preview.lbl_density":      "DENSITÉ",
    "preview.lbl_pattern":      "MOTIF",
    "preview.lbl_surface":      "SURFACE",

    "preview.sec_speeds":       "VITESSES",
    "preview.lbl_outer_wall":   "PAROI EXT.",
    "preview.lbl_inner_wall":   "PAROI INT.",
    "preview.lbl_infill":       "REMPLISSAGE",
    "preview.lbl_first_c":      "PREMIÈRE C.",
    "preview.lbl_top_surf":     "SURFACE SUP.",
    "preview.lbl_bridge":       "PONT",

    "preview.sec_finish":       "FINITION",
    "preview.lbl_seam":         "COUTURES",
    "preview.lbl_ironing":      "IRONING",
    "preview.lbl_iron_speed":   "VITESSE IRON.",
    "preview.lbl_iron_flow":    "FLUX IRON.",
    "preview.lbl_elep_foot":    "COMPENS. ÉLÉP.",
    "preview.lbl_xy_comp":      "COMPENS. XY",

    "preview.sec_adhesion":     "ADHÉRENCE",
    "preview.lbl_brim_type":    "TYPE BRIM",
    "preview.lbl_brim_w":       "LARGEUR",

    "preview.sec_material":     "MATÉRIAU & MACHINE",
    "preview.lbl_nozzle":       "BUSE",
    "preview.lbl_bed":          "PLATEAU",
    "preview.lbl_supports":     "SUPPORTS",
    "preview.lbl_threshold":    "SEUIL",
    "preview.lbl_plate_only":   "PLATEAU ONLY",
    "preview.supp_tree":        "Arborescents",
    "preview.supp_normal":      "Normaux",
    "preview.supp_classic":     "Classique",
    "preview.lbl_prime_tower":  "PRIME TOWER",
    "preview.val_active":       "ACTIVÉE",
    "preview.lbl_flush_ams":    "FLUSH AMS",
    "preview.val_infill":       "INFILL",

    "preview.sec_estimates":    "ESTIMATIONS",
    "preview.lbl_filament_est": "FILAMENT EST.",
    "preview.lbl_time_est":     "TEMPS EST.",
    "preview.lbl_volume":       "VOLUME PIÈCE",

    # ── Splash Screen ────────────────────────────────────────────────────────
    "splash.loading":       "Chargement en cours...",
    "splash.tagline":       "AI-Powered 3D Print Optimizer",

    # ── Filament / Printer Selector ───────────────────────────────────────────
    "selector.lbl_printer":        "IMPRIMANTE CIBLE",
    "selector.lbl_filament":       "FILAMENT",
    "selector.lbl_plate":          "PLATEAU",
    "selector.validate_btn":       "VALIDER",
    "selector.nozzle_tip":         "Diamètre de buse installée sur l'imprimante",
    "selector.plate_tip":          "Type de surface du plateau installé sur l'imprimante",
    "selector.hint_printer_first": "→ Validez d'abord votre imprimante",
    "selector.compat_ok":          "✓  Compatible avec {printer}",
    "selector.compat_incompat":    "✕  {filament} incompatible avec {printer}",
    "selector.warn_enclosure":     "Enceinte requise — {printer} est ouvert",
    "selector.warn_ams":           "AMS incompatible — chargement direct requis",
    "selector.warn_bed":           "Plateau requis {req}°C > max {max}°C",

    # ── Settings Dialog ───────────────────────────────────────────────────────
    "settings.title":           "PARAMÈTRES",
    "settings.sec_appearance":  "APPARENCE",
    "settings.dark_theme":      "Thème sombre",
    "settings.language":        "Langue",
    "settings.sec_print":       "IMPRESSION 3D",
    "settings.printer_default": "Imprimante par défaut",
    "settings.slicer_output":   "Slicer de sortie",
    "settings.slicer_bambu":    "Bambu Studio",
    "settings.slicer_orca":     "OrcaSlicer",
    "settings.slicer_prusa":    "PrusaSlicer",
    "settings.orient_suggest":  "Suggérer l'orientation optimale",
    "settings.sec_export":      "EXPORT",
    "settings.folder_ph":       "Dossier Téléchargements (par défaut)",
    "settings.printer_none":    "(aucune)",
    "settings.browse_title":    "Choisir le dossier d'export",
    "settings.restart_notice":  "⚠  Redémarrage requis pour appliquer les changements",

    # ── Welcome Dialog ────────────────────────────────────────────────────────
    "welcome.title":            "neoSlice",
    "welcome.subtitle":         "AI-POWERED 3D PRINT OPTIMIZER",
    "welcome.copyright":        "© 2026 Emmanuel Percheron",
    "welcome.message":          (
        "Merci d'avoir téléchargé <b>neoSlice</b> !<br>"
        "Ce logiciel a été entièrement conçu et développé par <b>Emmanuel Percheron</b>, "
        "pour simplifier et optimiser l'impression 3D avec votre imprimante — Bambu Lab, "
        "Creality, Prusa, Anycubic et bien d'autres.<br><br>"
        "J'espère sincèrement qu'il vous sera utile dans vos projets."
    ),
    "welcome.coffee_title":     "☕  Ce logiciel est <b>entièrement gratuit</b> et le restera.",
    "welcome.coffee_sub":       "Si vous souhaitez soutenir le développement :",
    "welcome.coffee_btn":       "♥   Me soutenir sur Buy Me a Coffee",
    "welcome.no_show":          "Ne plus afficher ce message",
    "welcome.start_btn":        "Commencer →",

    # ── Tutorial ──────────────────────────────────────────────────────────────
    "tuto.skip":    "Passer le guide",
    "tuto.prev":    "← Précédent",
    "tuto.next":    "Suivant →",
    "tuto.finish":  "Terminer  ✓",

    "tuto.0.title": "Bienvenue dans neoSlice",
    "tuto.0.body":  (
        "neoSlice analyse votre fichier STL et génère automatiquement les paramètres "
        "d'impression optimaux pour votre imprimante — Bambu Lab, Creality, Prusa, "
        "Anycubic et bien d'autres.\n\n"
        "Ce guide vous présente les étapes du workflow.\n"
        "Adaptez le <b>mode de performance</b> dans les paramètres "
        "<span style='font-family:Segoe MDL2 Assets;font-size:10pt;'>&#xE713;</span>"
        " selon votre machine.\n"
        "Cliquez sur <b>Suivant</b> pour commencer."
    ),
    "tuto.1.title": "① Configuration — Imprimante, Filament & Plateau",
    "tuto.1.body":  (
        "Sélectionnez votre <b>imprimante cible</b> et votre <b>diamètre de buse</b>, "
        "puis cliquez sur <b>VALIDER</b>.\n"
        "Faites de même pour votre <b>filament</b>.\n\n"
        "Choisissez ensuite votre <b>type de plateau</b> — neoSlice adapte "
        "automatiquement les températures et l'adhérence."
    ),
    "tuto.2.title": "② Import STL / OBJ / 3MF",
    "tuto.2.body":  (
        "Glissez votre <b>fichier STL, OBJ ou 3MF</b> dans cette zone, ou cliquez pour ouvrir "
        "l'explorateur de fichiers.\n\n"
        "neoSlice analyse automatiquement la géométrie :\n"
        "<b>surplombs · stabilité · zones fragiles</b>\n"
        "<b>volume & dimensions · orientation optimale</b>"
    ),
    "tuto.3.title": "③ Instruction Mission",
    "tuto.3.body":  (
        "Ouvrez chaque accordéon pour choisir vos critères :\n"
        "<b>Qualité · Résistance · Vitesse · Supports · Adhérence · Usage · Mode</b>\n\n"
        "Le groupe <b>Mode</b> permet d'activer :\n"
        "— <b>Silencieux</b> : vitesses –40 % pour moins de bruit\n"
        "— <b>Multicolore AMS</b> : active la <b>prime tower</b> "
        "(tour de purge qui stabilise les changements de couleur) et le <b>flush</b> "
        "(purge automatique de la buse entre chaque filament)\n\n"
        "Sauvegardez vos combinaisons favorites en présets, "
        "puis cliquez sur <b>GÉNÉRER CONFIGURATION →</b>."
    ),
    "tuto.4.title": "④ Export vers votre slicer",
    "tuto.4.body":  (
        "Une fois la configuration générée, le <b>bouton d'export</b> s'active.\n\n"
        "neoSlice génère un fichier <b>.3MF</b> avec tous les paramètres optimisés "
        "selon votre matériau et la géométrie de la pièce.\n\n"
        "Choisissez votre <b>slicer de sortie</b> dans les réglages (Bambu Studio, "
        "OrcaSlicer ou PrusaSlicer) : le fichier s'ouvrira dans le bon logiciel.\n\n"
        "Des <b>alertes matériau</b> peuvent apparaître dans le panneau d'analyse : "
        "risque de warping, séchage recommandé, incompatibilité AMS…"
    ),
    "tuto.5.title": "⑤ Barre de titre",
    "tuto.5.body":  (
        "Raccourcis disponibles à tout moment :<br><br>"
        "<table cellspacing='0' cellpadding='0' width='100%'>"
        "<tr><td width='28' valign='top' style='padding-top:1px;'>"
        "<span style='font-family:\"Segoe MDL2 Assets\";font-size:11pt;color:#E8F4FF;'>&#xE8BD;</span>"
        "</td><td valign='top'>Signaler un bug ou partager votre expérience. "
        "Ouvre un formulaire en ligne&nbsp;; vos retours sont lus personnellement.</td></tr>"
        "<tr><td colspan='2' height='10'></td></tr>"
        "<tr><td width='28' valign='top' style='padding-top:1px;'>"
        "<b style='color:#E8F4FF;font-size:11pt;'>?</b></td>"
        "<td valign='top'>Relancer ce tutoriel.</td></tr>"
        "<tr><td colspan='2' height='10'></td></tr>"
        "<tr><td width='28' valign='top' style='padding-top:2px;'>&#x2615;</td>"
        "<td valign='top'>Soutenir le développement du logiciel via un don volontaire.</td></tr>"
        "<tr><td colspan='2' height='10'></td></tr>"
        "<tr><td width='28' valign='top' style='padding-top:2px;'>"
        "<span style='font-family:\"Segoe MDL2 Assets\";font-size:11pt;color:#E8F4FF;'>&#xE713;</span>"
        "</td>"
        "<td valign='top'>Paramètres : <b>langue</b>, <b>mode de performance</b> "
        "(Complet / Équilibré / Économique), dossier d'export. "
        "Un redémarrage est proposé automatiquement si nécessaire.</td></tr>"
        "</table>"
    ),

    # ── Mise à jour ───────────────────────────────────────────────────────────
    "update.title":         "Mise à jour disponible",
    "update.body":          "neoSlice <b>v{new}</b> est disponible.<br>Vous utilisez actuellement la version <b>v{cur}</b>.",
    "update.notes_label":   "Nouveautés :",
    "update.btn_install":    "Mettre à jour maintenant",
    "update.btn_later":      "Plus tard",
    "update.downloading":    "Téléchargement : {pct}%",
    "update.installing":     "Lancement de l'installation…",
    "update.failed":         "Échec du téléchargement.",
    "update.btn_retry":      "Réessayer",

    # ── PDF ───────────────────────────────────────────────────────────────────
    "pdf.col_param":        "Paramètre",
    "pdf.col_value":        "Valeur",
    "pdf.col_unit":         "Unité",
    "pdf.col_note":         "Note",

    "pdf.filament_subtitle":    "Fiche de réglages filament",
    "pdf.full_subtitle":        "Rapport d'impression complet",

    "pdf.sec_base":         "Onglet Filament › Informations de base",
    "pdf.flow_ratio":       "Rapport de débit",
    "pdf.flow_note":        "Ajuster si sous/sur-extrusion",
    "pdf.softening_temp":   "Température de ramollissement",

    "pdf.sec_temp":         "Onglet Filament › Température d'impression",
    "pdf.plate_selected":   "Type de plateau",
    "pdf.bed_first":        "Plateau — 1ère couche",
    "pdf.bed_other":        "Plateau — autres couches",
    "pdf.nozzle_first":     "Buse — 1ère couche",
    "pdf.nozzle_other":     "Buse — Autres couches",

    "pdf.sec_vol":          "Onglet Filament › Vitesse volumétrique",
    "pdf.vol_max":          "Vitesse volumétrique maximale",
    "pdf.vol_adaptive":     "Vitesse volumétrique adaptative",
    "pdf.vol_disabled":     "Désactivée",

    "pdf.sec_fan":          "Onglet Refroidissement › Ventilateur de pièce",
    "pdf.fan_first_layer":  "Ventilateur 1ère couche",
    "pdf.fan_first_note":   "Ne jamais ventiler 1ère couche",
    "pdf.fan_min":          "Seuil mini du ventilateur",
    "pdf.fan_max_thresh":   "Seuil vitesse MAX ventilateur",
    "pdf.fan_always":       "Ventilation toujours active",
    "pdf.fan_slow_cool":    "Ralentir pour refroidir",
    "pdf.fan_no_slow_outer":"Ne pas ralentir parois externes",
    "pdf.fan_min_speed":    "Vitesse d'impression minimale",
    "pdf.fan_force_oh":     "Forcer ventilation surplombs",
    "pdf.fan_oh_thresh":    "Ventiler surplombs dépassant",
    "pdf.fan_oh_speed":     "Vitesse ventilateur surplombs",

    "pdf.sec_retract":      "Onglet Forçage des réglages › Rétraction",
    "pdf.retract_len":      "Longueur de rétraction",
    "pdf.retract_force":    "FORCER si indiqué",
    "pdf.retract_speed":    "Vitesse de rétraction",
    "pdf.retract_dsp":      "Vitesse de réinsertion",
    "pdf.retract_long":     "Rétraction longue (coupe)",
    "pdf.retract_long_dist":"Distance rétraction coupe",
    "pdf.drying":           "Séchage recommandé : {value}",

    "pdf.sec_geometry":     "Analyse géométrique",
    "pdf.dimensions":       "Dimensions (X × Y × Z)",
    "pdf.volume":           "Volume pièce",
    "pdf.surface":          "Surface",
    "pdf.verdict":          "Verdict global",
    "pdf.verdict_ok":       "PRÊT À IMPRIMER",
    "pdf.verdict_warn":     "CONFIGURATION ADAPTÉE — CONTRÔLER DANS VOTRE SLICER",
    "pdf.verdict_bad":      "PIÈCE COMPLEXE",
    "pdf.overhangs":        "Surplombs",
    "pdf.oh_angle":         "Angle max {angle}°",
    "pdf.stability":        "Stabilité",
    "pdf.fragility":        "Fragilité",
    "pdf.min_wall":         "Paroi min {t} mm",
    "pdf.supports_needed":  "Supports requis",
    "pdf.supp_vol":         "Volume estimé {r}%",
    "pdf.orient_suggested": "Orientation conseillée",
    "pdf.orient_current":   "Actuelle (Z+)",
    "pdf.orient_improve":   "+{pct}%",

    "pdf.sec_params":       "Paramètres d'impression (générés par neoSlice)",
    "pdf.time_est":         "Temps estimé",
    "pdf.time_with_supp":   "avec supports",
    "pdf.filament_est":     "Filament estimé",
    "pdf.layer_h":          "Hauteur de couche",
    "pdf.infill":           "Remplissage",
    "pdf.wall_loops":       "Boucles de paroi",
    "pdf.top_bot_layers":   "Couches sup./inf.",
    "pdf.outer_wall_spd":   "Vitesse paroi ext.",
    "pdf.infill_spd":       "Vitesse remplissage",
    "pdf.supports":         "Supports",
    "pdf.supp_off":         "Désactivés",
    "pdf.supp_on":          "Activés",
    "pdf.brim":             "Adhérence (brim)",
    "pdf.profile_name":     "Profil neoSlice",

    "pdf.sec_filament_temp":"Réglages filament — Températures",
    "pdf.bed_first2":       "Plateau — 1ère couche",
    "pdf.bed_other2":       "Plateau — autres couches",
    "pdf.nozzle_first2":    "Buse — 1ère couche",
    "pdf.nozzle_other2":    "Buse — autres couches",

    "pdf.sec_filament_fan": "Réglages filament — Ventilateur",
    "pdf.fan_max":          "Vitesse MAX ventilateur",
    "pdf.fan_always2":      "Ventilation toujours active",
    "pdf.fan_min2":         "Seuil mini ventilateur",
    "pdf.print_min_spd":    "Vitesse d'impression min.",

    "pdf.sec_filament_ret": "Réglages filament — Rétraction",
    "pdf.retract_len2":     "Longueur de rétraction",
    "pdf.retract_force2":   "FORCER",
    "pdf.retract_speed2":   "Vitesse de rétraction",

    "pdf.yes":              "Oui",
    "pdf.no":               "Non",
    "pdf.na":               "N/A",
    "pdf.na_auto":          "N/A (géré auto)",
    "pdf.header_fmt":       "Filament : {filament}  |  Imprimante : {printer}  |  {date}",
    "pdf.footer_note":      (
        "Les paramètres d'impression (qualité, vitesse, supports, adhérence) sont intégrés "
        "dans le fichier 3MF généré par neoSlice et ne nécessitent pas de configuration "
        "manuelle dans votre slicer."
    ),
    "pdf.generated_by":     "Généré par neoSlice v{version}",

    # ── Splash ────────────────────────────────────────────────────────────────
    "splash.loading":       "Chargement en cours...",
    "splash.tagline":       "AI-Powered 3D Print Optimizer",

    # ── Settings / Performance ────────────────────────────────────────────────
    "settings.sec_performance":      "PERFORMANCE",
    "settings.perf_mode":            "Mode de performance",
    "settings.perf_full":            "Complet",
    "settings.perf_balanced":        "Équilibré",
    "settings.perf_lite":            "Économique",
    "settings.perf_test_btn":        "Tester ma configuration",
    "settings.perf_testing":         "Test en cours...",
    "settings.perf_result_full":     "Config rapide — mode Complet recommandé ✓",
    "settings.perf_result_balanced": "Config moyenne — mode Équilibré recommandé",
    "settings.perf_result_lite":     "Config lente — mode Économique recommandé",
    "settings.perf_full_desc":       "Toutes les analyses sont actives : surplombs, stabilité et fragilité.",
    "settings.perf_balanced_desc":   "Analyses surplombs et stabilité actives. Optimisation d'orientation désactivée (gain de temps notable).",
    "settings.perf_lite_desc":       "Seule l'analyse de stabilité est active. Surplombs et orientation désactivés. Recommandé pour les PC lents.",
    "settings.restart_btn":          "Redémarrer maintenant",

    "settings.sec_updates":          "MISES À JOUR",
    "settings.update_check_btn":     "Vérifier maintenant",
    "settings.update_checking":      "Vérification en cours…",
    "settings.update_uptodate":      "neoSlice est à jour ✓",
    "settings.update_found":         "Mise à jour disponible !",

    # ── neoSlice Pro / Licence ────────────────────────────────────────────────
    "pro.paywall_subtitle":          "Vous avez utilisé vos diagnostics photo gratuits.\nDébloquez les diagnostics illimités.",
    "pro.price_suffix":              "{price} · paiement unique, à vie",
    "pro.unlock_btn":                "Débloquer neoSlice Pro",
    "pro.already_bought":            "Déjà acheté ? Collez votre clé de licence",
    "pro.key_placeholder":           "XXXX-XXXX-XXXX-XXXX",
    "pro.activate_btn":              "Activer",
    "pro.later_btn":                 "Plus tard",
    "pro.activating":                "Activation en cours…",
    "pro.thanks_title_end":          "activé !",
    "pro.thanks_subtitle":           "Merci pour votre soutien ! Voici ce que vous venez de débloquer :",
    "pro.benefit_unlimited":         "Diagnostics photo par IA illimités",
    "pro.benefit_corrections":       "Corrections appliquées à votre config en un clic",
    "pro.benefit_lifetime":          "Accès à vie, sur 3 appareils",
    "pro.benefit_support":           "Vous soutenez le développement de neoSlice",
    "pro.thanks_btn":                "Commencer",
    "pro.trial_counter":             "Essais gratuits : {restants}/{total}",
    "pro.coming_soon_short":         "Bientôt disponible",
    "pro.coming_soon_text":          "neoSlice Pro arrive très bientôt !",
    "pro.coming_soon_info":          "Le diagnostic photo par IA et le calculateur de devis seront disponibles dans une prochaine mise à jour.\n\nMerci de votre patience !",
    "pro.settings_status_pro":       "Activé ✓ — diagnostics photo illimités, à vie",
    "pro.settings_status_free":      "Version gratuite — {restants}/{total} diagnostics gratuits restants",
    "pro.settings_btn_upgrade":      "Passer à neoSlice Pro",
    "pro.settings_btn_deactivate":   "Désactiver cet appareil",
    "license.empty_key":             "Veuillez coller votre clé de licence.",
    "license.already_active":        "neoSlice Pro est déjà actif sur cet appareil.",
    "license.activated":             "neoSlice Pro activé. Merci pour votre soutien !",
    "license.refused":               "Clé refusée (erreur {code}).",
    "license.server_error":          "Erreur serveur (HTTP {code}).",
    "license.no_connection":         "Pas de connexion Internet — l'activation se fait une fois en ligne.",
    "license.no_connection_retry":   "Pas de connexion Internet — réessayez en ligne.",
    "license.unexpected":            "Erreur inattendue : {error}",
    "license.invalid_or_max":        "Clé invalide ou déjà utilisée sur le nombre maximum d'appareils.",
    "license.removed":               "Licence retirée de cet appareil.",
    "license.deactivated":           "Appareil désactivé — emplacement d'activation libéré.",

    # ── Diagnostic photo ──────────────────────────────────────────────────────
    "diag.uncertain_title":          "Analyse incertaine",
    "diag.uncertain_desc":           "Le modèle n'est pas assez sûr pour se prononcer. Reprenez une photo plus nette : cadrez bien la zone du défaut, bonne lumière, fond neutre, pas de flou.",
    "diag.mode_photo":               "Analyser une photo",
    "diag.mode_manual":              "Je connais le problème",
    "diag.manual_pick":              "Quel problème rencontrez-vous ?",
    "diag.manual_show":              "VOIR LES CORRECTIONS",
    "diag.manual_badge":             "Sélectionné manuellement",
    "diag.consent_revoke_note":      "Vous pouvez révoquer votre accord à tout moment dans les paramètres.",
    "diag.model_unavailable":        "Modèle non disponible — vérifiez votre connexion internet.",
    "diag.analyzing":                "Analyse en cours…",
    "diag.downloading_model":        "Téléchargement du modèle amélioré… {pct}%",

    # ── Espace Pro (gestion d'atelier) ─────────────────────────────────────────
    "pro.space_btn":                 "ESPACE PRO",
    "pro.space_tooltip":             "Gestion d'atelier : bobines, devis, clients, facturation",
    "pro.hub_title":                 "Espace Pro — Gestion d'atelier",
    "pro.tab_spools":                "Bobines",
    "pro.tab_quote":                 "Devis",
    "pro.tab_clients":               "Clients",
    "pro.tab_invoice":               "Facturation",
    "pro.tab_dashboard":             "Tableau de bord",
    "pro.tab_orders":                "Commandes",
    "pro.tab_products":              "Articles",
    "pro.edit":                      "Modifier",
    # ── Commandes (file de production) ──
    "ord.new":            "Nouvelle commande",
    "ord.none":           "Aucune commande pour l'instant.",
    "ord.intro":          "Suivez vos commandes de la prise en charge à l'encaissement.",
    "ord.client":         "Client",
    "ord.status":         "Statut",
    "ord.due":            "Échéance",
    "ord.spool":          "Bobine (déduction du stock)",
    "ord.grams":          "Filament (g)",
    "ord.notes":          "Notes",
    "ord.label":          "Désignation",
    "ord.save":           "Enregistrer la commande",
    "ord.create_title":   "Nouvelle commande",
    "ord.edit_title":     "Modifier la commande",
    "ord.advance":        "Avancer →",
    "ord.to_invoice":     "Facturer",
    "ord.delete":         "Supprimer la commande",
    "ord.delete_confirm": "Supprimer la commande {number} ?",
    "ord.from_quote":     "→ Commande",
    "ord.cancel_order":   "Annuler la commande",
    "ord.no_client":      "— Sans client —",
    "ord.no_spool":       "— Aucune (pas de déduction) —",
    "ord.section_active": "EN COURS",
    "ord.section_done":   "TERMINÉES / ARCHIVÉES",
    "ord.due_in":         "dans {n} j",
    "ord.overdue_days":   "retard {n} j",
    "ord.status_todo":      "À faire",
    "ord.status_printing":  "En impression",
    "ord.status_done":      "Terminé",
    "ord.status_delivered": "Livré",
    "ord.status_paid":      "Payé",
    "ord.status_cancelled": "Annulé",
    "ord.created":        "Commande {number} créée.",
    "ord.stock_note":     "Le stock est déduit automatiquement au passage en « En impression ».",
    "ord.consumptions":   "Consommation filament (1 ligne par couleur)",
    "ord.add_color":      "＋ Ajouter une couleur",
    "ord.pdf":            "Bon",
    "ord.total":          "TOTAL",
    "ordpdf.title":       "BON DE PRODUCTION",
    "ordpdf.footer":      "Document de production interne — neoSlice",
    "ordpdf.unassigned":  "(bobine non assignée)",
    "ord.est_mono":       "Mono-couleur : estimation pré-remplie — corrigez d'après votre slicer si besoin.",
    "ord.fill_multi":     "Multi-couleur : pas d'estimation possible — saisissez la consommation de chaque couleur.",
    # ── Articles (catalogue récurrent) ──
    "art.new":            "Nouvel article",
    "art.none":           "Aucun article. Créez vos produits récurrents pour les insérer en 1 clic.",
    "art.intro":          "Vos produits récurrents : enregistrez-les une fois, réutilisez-les partout.",
    "art.name":           "Nom de l'article",
    "art.price":          "Prix (HT)",
    "art.grams":          "Filament (g)",
    "art.duration":       "Durée (h)",
    "art.notes":          "Notes",
    "art.save":           "Enregistrer l'article",
    "art.create_title":   "Nouvel article",
    "art.edit_title":     "Modifier l'article",
    "art.delete":         "Supprimer",
    "art.delete_confirm": "Supprimer l'article « {name} » ?",
    # ── Relances / échéances factures ──
    "fact.overdue":       "EN RETARD",
    "fact.relance":       "Relancer",
    "fact.echeance":      "Échéance",
    "fact.relance_title": "Relance de paiement",
    "fact.copy":          "Copier",
    "fact.relance_done":  "Relance enregistrée. Copiez le message ci-dessous pour votre client :",
    "fact.relance_msg":   "Bonjour,\n\nSauf erreur de notre part, la facture {number} d'un montant de {amount} reste impayée (échéance : {due}).\nNous vous remercions de bien vouloir procéder à son règlement.\n\nCordialement,\n{company}",
    # ── Tableau de bord (production / retards / rapport) ──
    "dash.sec_orders":    "PRODUCTION",
    "dash.orders_active": "Commandes en cours",
    "dash.orders_todo":   "À imprimer",
    "dash.month_billed":  "CA du mois",
    "dash.overdue":       "Factures en retard",
    "dash.overdue_amount":"Montant dû en retard",
    "dash.report_title":  "CHIFFRE D'AFFAIRES — 6 DERNIERS MOIS",
    "dash.export":        "Exporter la compta (CSV)",
    "dash.export_done":   "Export comptable enregistré : {path}",
    "dash.export_none":   "Aucune facture à exporter.",
    "dash.legend_paid":   "Encaissé",
    "dash.legend_billed": "Facturé (en attente)",
    # ── Stock / réappro ──
    "spool.threshold":    "Seuil de réappro (g)",
    "shop.title":         "LISTE DE COURSES",
    "shop.none":          "Stock OK — rien à racheter.",
    "shop.remaining":     "restant {g} g",
    "shop.missing":       "racheter 1 bobine de {g} g",
    "pro.coming_soon":               "Bientôt disponible",
    "pro.coming_soon_desc":          "Ce module arrive dans une prochaine mise à jour.",
    "pro.backup":                    "Sauvegarder mes données",
    "pro.backup_done":               "Données sauvegardées : {path}",
    "pro.export":                    "Exporter mes données",
    "pro.import":                    "Importer des données",
    "pro.export_done":               "Données exportées : {path}",
    "pro.import_confirm":            "Importer remplacera vos données actuelles (bobines, devis…). Une copie de secours est conservée. Continuer ?",
    "pro.import_done":               "{n} fichier(s) importé(s). Données restaurées.",
    "pro.autosave":                  "💾 Sauvegarde automatique",
    # Inventaire bobines
    "spool.add":                     "Ajouter une bobine",
    "spool.edit":                    "Modifier la bobine",
    "spool.delete":                  "Supprimer",
    "spool.delete_confirm":          "Supprimer cette bobine définitivement ?",
    "spool.empty":                   "Aucune bobine pour l'instant.\nAjoutez votre première bobine pour suivre votre stock.",
    "spool.save":                    "Enregistrer",
    "spool.cancel":                  "Annuler",
    "spool.material":                "Matériau",
    "spool.brand":                   "Marque",
    "spool.color":                   "Couleur",
    "spool.color_name":              "Nom de la couleur",
    "spool.finish":                  "Finition",
    "spool.total_g":                 "Poids neuf (g)",
    "spool.remaining_g":             "Poids restant (g)",
    "spool.tare_g":                  "Poids bobine vide (g)",
    "spool.cost_total":              "Prix payé",
    "spool.cost_kg":                 "Coût/kg",
    "spool.vendor":                  "Fournisseur",
    "spool.purchase_date":           "Date d'achat",
    "spool.location":                "Emplacement",
    "spool.lot":                     "N° de lot",
    "spool.notes":                   "Notes",
    "spool.remaining":               "restant",
    "spool.low_stock":               "Stock bas",
    "spool.low_stock_banner":        "{n} bobine(s) en stock bas",
    "spool.section_id":              "Identité",
    "spool.section_stock":           "Stock & coût",
    "spool.section_extra":           "Détails",
    # Déduction après export
    "spool.deduct_title":            "Filament utilisé",
    "spool.deduct_prompt":           "Déduire ~{g} g de votre stock ?",
    "spool.deduct_choose":           "Bobine à décompter",
    "spool.deduct_none":             "Ne pas décompter",
    "spool.deduct_ok":               "{g} g déduits de {name}",
    "spool.use_for_quote":           "Bobine (coût auto)",

    # ── Facturation (Espace Pro) ───────────────────────────────────────────────
    "fact.status_draft":   "Brouillon",
    "fact.status_sent":    "Envoyée",
    "fact.status_paid":    "Payée",
    "fact.sec_company":    "Ma société",
    "fact.sec_new":        "Nouvelle facture",
    "fact.sec_saved":      "Factures enregistrées",
    "fact.c_name":         "Nom / raison sociale",
    "fact.c_form":         "Forme juridique",
    "fact.c_address":      "Adresse",
    "fact.c_zip":          "Code postal",
    "fact.c_city":         "Ville",
    "fact.c_email":        "E-mail",
    "fact.c_phone":        "Téléphone",
    "fact.c_taxid":        "N° fiscal / TVA",
    "fact.legal_section":  "Mentions légales (selon le pays)",
    "fact.f_siret":        "N° SIRET",
    "fact.f_rcs":          "RCS / RM",
    "fact.f_capital":      "Capital social",
    "fact.f_regime":       "Régime TVA",
    "fact.regime_normal":  "Assujetti à la TVA",
    "fact.regime_franchise": "Franchise en base (art. 293 B)",
    "fact.f_steuernr":     "Steuernummer",
    "fact.f_handelsreg":   "Registre du commerce (Handelsregister)",
    "fact.f_bce":          "N° BCE",
    "fact.f_rcsl":         "N° RCS Luxembourg",
    "fact.f_companyno":    "Company number",
    "fact.f_busno":        "Business Number (GST/HST)",
    "fact.f_kvk":          "N° KvK",
    "fact.f_rea":          "N° REA",
    "fact.f_nif":          "NIF / CIF",
    "fact.f_firmenbuch":   "N° Firmenbuch (FN)",
    "fact.f_recovery":     "Frais de recouvrement (retard)",
    "fact.doc_lang":       "Langue des documents",
    "fact.doc_lang_auto":  "Auto (selon le pays)",
    "fact.c_iban":         "IBAN",
    "fact.c_terms":        "Conditions de paiement",
    "fact.country":        "Pays",
    "fact.save_company":   "💾  Enregistrer la société",
    "fact.company_saved":  "Informations de société enregistrées.",
    "fact.client":         "Client",
    "fact.bill_country":   "Pays de facturation",
    "fact.date":           "Date",
    "fact.due":            "Échéance",
    "fact.vat_rate":       "Taux de TVA (%)",
    "fact.discount":       "Remise (%)",
    "fact.col_desig":      "Désignation",
    "fact.col_qty":        "Qté",
    "fact.col_pu":         "PU HT",
    "fact.add_line":       "＋ Ajouter une ligne",
    "fact.notes_ph":       "Notes / message (facultatif)…",
    "fact.total_ht":       "Total HT",
    "fact.discount_l":     "Remise",
    "fact.vat":            "TVA",
    "fact.total_ttc":      "TOTAL TTC",
    "fact.net_ht":         "Net HT",
    "fact.save_invoice":   "Enregistrer la facture",
    "fact.gen_pdf":        "Générer le PDF",
    "fact.empty":          "Aucune facture enregistrée.",
    "fact.need_line":      "Ajoutez au moins une ligne.",
    "fact.invoice":        "Facture",
    "fact.saved_msg":      "Facture {number} enregistrée.",
    "fact.delete":         "Supprimer",
    "fact.delete_confirm": "Supprimer la facture {number} ?",
    "fact.pdf":            "PDF",
    "fact.pdf_invoice":    "FACTURE",
    "fact.pdf_num":        "N°",
    "fact.pdf_billto":     "Facturé à",
    "fact.pdf_your_company": "Votre société",
    "fact.pdf_footer":     "Facture générée par neoSlice",
    "fact.from_quote":     "D'après le devis {number}.",
    "fact.client_select":  "Client enregistré",
    "fact.client_none":    "— Saisie manuelle —",
    "fact.client_save":    "＋ Enregistrer ce client",
    "fact.client_saved":   "Client ajouté au répertoire.",

    # ── Clients (mini-CRM) ─────────────────────────────────────────────────────
    "client.add":            "Ajouter un client",
    "client.edit":           "Modifier le client",
    "client.delete":         "Supprimer",
    "client.delete_confirm": "Supprimer ce client ? (ses devis/factures sont conservés)",
    "client.empty":          "Aucun client.\nAjoutez votre premier client ou enregistrez-en un depuis une facture.",
    "client.save":           "Enregistrer",
    "client.cancel":         "Annuler",
    "client.name":           "Nom du contact",
    "client.company":        "Société",
    "client.address":        "Adresse",
    "client.zip":            "Code postal",
    "client.city":           "Ville",
    "client.country":        "Pays",
    "client.email":          "E-mail",
    "client.phone":          "Téléphone",
    "client.taxid":          "N° fiscal / TVA",
    "client.notes":          "Notes",
    "client.n_quotes":       "{n} devis",
    "client.n_invoices":     "{n} factures",
    "client.billed":         "Facturé",
    "client.paid":           "Payé",
    "client.due":            "Dû",
    "client.history":        "Historique",
    "client.section_quotes": "Devis",
    "client.section_invoices": "Factures",
    "client.back":           "← Retour aux clients",
    "client.open":           "Ouvrir la fiche",

    # ── Tableau de bord ────────────────────────────────────────────────────────
    "dash.sec_activity":   "ACTIVITÉ",
    "dash.sec_docs":       "DOCUMENTS",
    "dash.sec_stock":      "STOCK FILAMENT",
    "dash.billed":         "Chiffre d'affaires",
    "dash.paid":           "Encaissé",
    "dash.due":            "En attente",
    "dash.invoices":       "Factures",
    "dash.unpaid":         "dont {n} impayée(s)",
    "dash.quotes":         "Devis",
    "dash.clients":        "Clients",
    "dash.spools":         "Bobines",
    "dash.stock_g":        "Filament restant",
    "dash.stock_value":    "Valeur du stock",
    "dash.low_stock":      "{n} en stock bas",
    "dash.welcome":        "Bienvenue dans votre Espace Pro",
    "dash.welcome_sub":    "Gérez vos bobines, devis, factures et clients — tout est local et sauvegardé automatiquement.",

    # ── Calculateur de coût / devis (Pro) ──────────────────────────────────────
    "cost.btn":                      "DEVIS",
    "cost.tooltip":                  "Calculer le coût de revient et générer un devis",
    "cost.title":                    "CALCULATEUR DE COÛT",
    "cost.save_quote":               "ENREGISTRER LE DEVIS",
    "cost.quote_saved":              "Devis {number} enregistré.",
    "cost.saved_quotes":             "Devis enregistrés",
    "cost.no_quotes":                "Aucun devis enregistré.",
    "cost.to_invoice":               "→ Facture",
    "cost.to_invoice_full":          "Convertir en facture",
    "cost.converted":                "Converti → facture {number}",
    "cost.del":                      "Supprimer",
    "cost.del_quote_confirm":        "Supprimer le devis {number} ?",
    "cost.section_rates":            "MES TARIFS (enregistrés)",
    "cost.rates_note":               "Valeurs pré-remplies indicatives (moyennes 2025-2026) — ajustez selon votre contrat et un wattmètre pour plus de précision.",
    "cost.section_print":            "CETTE IMPRESSION",
    "cost.part_name":                "Nom de la pièce",
    "cost.quantity":                 "Quantité",
    "cost.country":                  "Pays",
    "cost.currency":                 "Devise",
    "cost.kwh":                      "Électricité ({cur}/kWh)",
    "cost.filament_price":           "Filament ({cur}/kg)",
    "cost.machine_price":            "Prix machine ({cur})",
    "cost.machine_life":             "Durée de vie machine (h)",
    "cost.labor_rate":               "Taux horaire ({cur}/h)",
    "cost.failure":                  "Taux d'échec (%)",
    "cost.margin":                   "Marge bénéfice (%)",
    "cost.packaging":                "Emballage ({cur}/pièce)",
    "cost.weight":                   "Poids (g / pièce)",
    "cost.time":                     "Durée (h / pièce)",
    "cost.labor_min":                "Main d'œuvre (min)",
    "cost.power":                    "Puissance imprimante (W)",
    "cost.estimated_note":           "⚠️ Poids et durée estimés automatiquement par neoSlice — pour un devis fiable, remplacez-les par les chiffres exacts affichés par votre slicer après découpe.",
    "cost.row_material":             "Matière",
    "cost.row_electricity":          "Électricité",
    "cost.row_wear":                 "Usure machine",
    "cost.row_labor":                "Main d'œuvre",
    "cost.row_packaging":            "Emballage",
    "cost.row_failure":              "Marge échec",
    "cost.total":                    "COÛT DE REVIENT",
    "cost.distribution":             "RÉPARTITION DES COÛTS",
    "cost.suggested_prices":         "PRIX SUGGÉRÉS",
    "cost.tier_eco":                 "Éco",
    "cost.tier_standard":            "Standard",
    "cost.tier_premium":             "Premium",
    "cost.tier_custom":              "Perso",
    "cost.margin_row":               "Marge",
    "cost.sale_price":               "PRIX DE VENTE CONSEILLÉ",
    "cost.total_qty":                "Total ({n} pièces)",
    "cost.export_pdf":               "EXPORTER LE DEVIS (PDF)",
    "cost.close":                    "Fermer",
    "cost.quote_heading":            "DEVIS",
    "cost.quote_part":               "Pièce",
    "cost.quote_date":               "Date",
    "cost.quote_qty":                "Quantité",
    "cost.pdf_saved":                "Devis enregistré : {path}",
    "cost.pdf_error":                "Impossible de créer le PDF : {error}",
    "cost.quote_disclaimer":         "Estimation établie à titre indicatif, sous réserve de modification. Valable 30 jours à compter de la date d'émission.",
}

# ── English ───────────────────────────────────────────────────────────────────

_EN: dict[str, str] = {

    # ── Application / TopBar ──────────────────────────────────────────────────
    "app.title":            "neoSlice",
    "app.subtitle":         "AI-POWERED 3D PRINT OPTIMIZER",
    "app.btn_new_piece":    "↺  NEW PART",
    "app.btn_diag":         "AI DIAGNOSTIC",
    "app.tip_feedback":     "Send feedback / report a bug",
    "app.tip_guide":        "User guide",
    "app.tip_coffee":       "About / Support development",
    "app.tip_settings":     "Settings",

    # ── StatusBar ─────────────────────────────────────────────────────────────
    "status.initial":           "SYSTEM READY — SELECT TARGET PRINTER  ①",
    "status.initial":           "SYSTEM READY — SELECT TARGET PRINTER",
    "status.ready":             "READY — DROP A NEW STL FILE",
    "status.loading":           "Model loaded — {name} — analyzing...",
    "status.analysis_ok":       "Analysis OK ({ms:.0f} ms){oh_tag} — Settings suggested · refine your intent ③",
    "status.analysis_err":      "Analysis error: {msg}",
    "status.analysis_timeout":  "Analysis timed out (60 s) — restart the app if the issue persists",
    "status.printer_confirmed": "Printer confirmed — select filament  ②",
    "status.filament_confirmed":"Filament confirmed — load an STL file  ③",
    "status.orient_applying":   "Applying orientation...",
    "status.orient_done":       "Orientation applied — updating analysis...",
    "status.orient_reset":      "Orientation reset — re-analyzing...",
    "status.orient_err":        "Orientation error: {msg}",
    "status.exporting":         "Exporting...",
    "status.export_ok":         ".3MF exported",
    "status.export_ok_warn":    ".3MF exported ({msg})",
    "status.export_err":        "Export error: {msg}",
    "status.gen_err":           "Generation error: {msg}",
    "status.oh_tag":            " | overhangs {pct:.1f}%",

    # ── Export / Success Dialog ────────────────────────────────────────────────
    "export.btn":               "↓  EXPORT .3MF  →  {slicer}",
    "export.dialog_title":      "Save .3MF file",
    "export.dialog_filter":     "3MF Files (*.3mf)",
    "export.success_title":     "✓   3MF file generated successfully",
    "export.success_info":      (
        "Print parameters (quality, speed, supports…) are embedded in the 3MF.<br>"
        "The <b>filament</b> parameters (temperatures, cooling, flow rate) must be "
        "configured manually in your slicer."
    ),
    "export.dlg_title":         ".3MF file generated",
    "export.btn_bambu":         "  Open in Bambu Studio",
    "export.btn_orca":          "  Open in OrcaSlicer",
    "export.btn_prusa":         "  Open in PrusaSlicer",
    "export.btn_pdf":           "  Filament PDF sheet",
    "export.btn_close":         "Close",

    # ── DropZone ─────────────────────────────────────────────────────────────
    "drop.main_locked":     "CONFIRM PRINTER",
    "drop.sub_locked":      "and filament to continue",
    "drop.step_locked":     "Step ①",
    "drop.main":            "DROP STL / 3MF FILE",
    "drop.sub":             "or click to browse",
    "drop.dialog_title":    "Open a 3D file",
    "drop.dialog_filter":   "3D Files (*.stl *.obj *.3mf);;All files (*)",
    "drop.reopen":          "↺  Reopen: {name}",
    "drop.sub_loaded":      "click to change",

    # ── AnalysisPanel ────────────────────────────────────────────────────────
    "analysis.dot_system":  "SYSTEM",
    "analysis.dot_stl":     "STL",
    "analysis.dot_analysis":"ANALYSIS",
    "analysis.dot_gen":     "GENERATION",
    "analysis.gauge_oh":    "Overhangs",
    "analysis.gauge_stab":  "Stability",
    "analysis.gauge_frag":  "Fragility",
    "analysis.gauge_supp":  "Supp. vol.",
    "analysis.default_val": "———",
    "analysis.dim_x":       "X",
    "analysis.dim_y":       "Y",
    "analysis.dim_z":       "Z",
    "analysis.vol":         "VOL",
    "analysis.faces":       "FACES",
    "analysis.orient_btn":  "↻  Apply recommended orientation",
    "analysis.progress_init": "Initializing...",
    "analysis.verdict_ok":  "✓  READY TO PRINT",
    "analysis.verdict_warn":"⚠  CONFIGURATION ADAPTED — CHECK IN YOUR SLICER",
    "analysis.verdict_bad": "⛔  COMPLEX PART — CAUTION",

    "analysis.status_floating":   "⛔ Floating regions — supports generated automatically",
    "analysis.status_supp_req":   "⚠ Supports required ({pct:.1f}% overhangs)",
    "analysis.status_supp_mod":   "⚠ Moderate overhangs ({pct:.1f}%) — check supports",
    "analysis.status_oh_ok":      "✓ No significant overhangs",
    "analysis.status_stab_low":   "⚠ Low stability — brim added to configuration",
    "analysis.status_stab_med":   "⚠ Moderate stability — brim advised",
    "analysis.status_stab_ok":    "✓ Stable — brim not needed",
    "analysis.status_frag":       "⚠ Thin walls — min {min_t} mm (rec. {rec_t} mm)",
    "analysis.status_flat":       "⚠ Flat part — warping risk",
    "analysis.status_orient":     "↻ Optimal orientation: {label} (+{imp:.0f}%)",
    "analysis.orient_apply_fmt":  "↻  Apply — {label}  (+{imp:.0f}%)",
    "analysis.loading_label":     "◌  ANALYZING",
    "analysis.loading_pct":       "ANALYZING",
    "analysis.orientation_applied_info": "Wide brim (10+ mm) and heated bed recommended.",
    "analysis.disabled":        "DISABLED",
    "analysis.lite_mode_warn":  "⚠ Lite mode — overhangs not analyzed · check supports in your slicer",

    "analysis.tip_oh":   (
        "Overhangs: areas angled more than 45° with no material below.\n"
        "High → enable supports in your slicer to prevent collapse."
    ),
    "analysis.tip_stab": (
        "Bed stability: the higher the score, the better the part holds.\n"
        "Low → risk of detachment during printing → use a brim."
    ),
    "analysis.tip_frag": (
        "Minimum wall thickness detected in the part.\n"
        "The displayed value is the actual thickness (in mm).\n"
        "Below 1.2 mm → risk of breakage or poor printing → increase wall count."
    ),
    "analysis.tip_supp": (
        "Volume of support material needed relative to the part.\n"
        "High → more filament consumed and longer print time."
    ),

    # ── Viewer 3D ─────────────────────────────────────────────────────────────
    "viewer.loading_default":   "ANALYZING...",
    "viewer.loading_sub":       "COMPUTING — PLEASE WAIT",
    "viewer.no_pyvista":        "3D Viewer\n\nInstall pyvistaqt to enable the viewer:\npip install pyvistaqt",
    "viewer.show_plate":        "Build plate",
    "viewer.auto_rotate":       "Auto rotate",
    "viewer.orient_btn":        "↻  Apply optimal orientation",
    "viewer.orient_optimal":    "✓  Current orientation: optimal",
    "viewer.orient_apply_lbl":  "↻  {label}",
    "viewer.orient_reset":      "↩  Reset orientation",
    "viewer.loading_orient":    "OPTIMIZING ORIENTATION...",
    "viewer.loading_analysis":  "ANALYZING PART...",

    # ── IntentSelector ────────────────────────────────────────────────────────
    "intent.group_quality":     "QUALITY",
    "intent.group_strength":    "STRENGTH",
    "intent.group_speed":       "SPEED",
    "intent.group_adhesion":    "ADHESION",
    "intent.group_usage":       "USAGE",
    "intent.group_mode":        "MODE",

    "intent.q_draft":           "Draft",
    "intent.q_draft_desc":      "0.28mm — prototypes only",
    "intent.q_standard":        "Standard",
    "intent.q_standard_desc":   "0.20mm — speed / quality balance",
    "intent.q_fine":            "Fine",
    "intent.q_fine_desc":       "0.12mm — good surface finish",
    "intent.q_ultra":           "Ultra Fine",
    "intent.q_ultra_desc":      "0.08mm — maximum finish, slow",

    "intent.s_light":           "Light",
    "intent.s_light_desc":      "Minimal walls, material saving",
    "intent.s_standard":        "Standard",
    "intent.s_standard_desc":   "Normal strength for everyday use",
    "intent.s_strong":          "Reinforced",
    "intent.s_strong_desc":     "More walls + infill (cubic)",
    "intent.s_ultra":           "Ultra Strong",
    "intent.s_ultra_desc":      "Maximum strength — gyroid 80%",

    "intent.sp_standard":       "Standard",
    "intent.sp_standard_desc":  "Bambu Lab recommended speeds",
    "intent.sp_fast":           "Fast",
    "intent.sp_fast_desc":      "+50% speed — slightly reduced quality",
    "intent.sp_ultra":          "Ultra Fast",
    "intent.sp_ultra_desc":     "Maximum speed — prototypes only",

    "intent.a_none":            "None",
    "intent.a_none_desc":       "No brim — stable parts only",
    "intent.a_brim5":           "Brim 5mm",
    "intent.a_brim5_desc":      "Standard brim — moderate stability",
    "intent.a_brim10":          "Brim 10mm",
    "intent.a_brim10_desc":     "Wide brim — tall or fragile parts",

    "intent.u_indoor":          "Indoor standard",
    "intent.u_indoor_desc":     "Optimal PLA parameters",
    "intent.u_outdoor":         "Outdoor / UV",
    "intent.u_outdoor_desc":    "Reinforced gyroid, PETG/ASA temps",
    "intent.u_visible":         "Visible finish",
    "intent.u_visible_desc":    "Ironing, seams at the back",
    "intent.u_precision":       "Precision assembly",
    "intent.u_precision_desc":  "Arachne + tight XY compensation",

    "intent.m_standard":        "Standard",
    "intent.m_standard_desc":   "No special mode",
    "intent.m_silent":          "Silent",
    "intent.m_silent_desc":     "Speeds -40% — quiet printing",
    "intent.m_multicolor":      "Multicolor (AMS)",
    "intent.m_multicolor_desc": "Prime tower + optimized flush",

    "intent.group_support":      "SUPPORTS",
    "intent.sup_auto":           "Auto",
    "intent.sup_auto_desc":      "Software decides based on geometry",
    "intent.sup_classic":        "Classic",
    "intent.sup_classic_desc":   "Standard columns, easy to remove",
    "intent.sup_tree":           "Tree",
    "intent.sup_tree_desc":      "Organic, fewer marks on the part",
    "intent.sup_none":          "No support",
    "intent.sup_none_desc":     "Forces no supports even if geometry requires them",

    "intent.lock_msg":          "LOAD AN STL FILE",
    "intent.lock_sub":          "to access the settings",
    "intent.lock_step":         "Step ②",
    "intent.presets_header":    "★  MY PRESETS",
    "intent.presets_empty":     "No presets — save your favorite settings",
    "intent.auto_select_msg":   "✦  Settings pre-selected from analysis — adjust as needed",
    "intent.btn_save":          "★  SAVE",
    "intent.btn_generate":      "GENERATE CONFIGURATION →",
    "intent.btn_conflicts":     "⛔  RESOLVE CONFLICTS",
    "intent.btn_loading":       "◌  GENERATING...",
    "intent.save_dialog_title": "Save preset",
    "intent.save_dialog_label": "Preset name:",

    "intent.conflict_ultra_fine_ultra_fast": (
        "Ultra Fine + Ultra Fast are incompatible — quality will match Draft."
    ),
    "intent.conflict_ultra_fine_ultra_fast_hint": (
        "Try: Fine + Fast  or  Standard + Ultra Fast"
    ),
    "intent.conflict_fine_fast_warn": (
        "Ultra Fine with Fast speed may slightly degrade surface finish."
    ),
    "intent.conflict_fine_fast_hint": "Compromise: Fine + Fast for a good balance",
    "intent.conflict_fine_ultra_fast": (
        "Fine + Ultra Fast will effectively yield Standard quality."
    ),
    "intent.conflict_fine_ultra_fast_hint": (
        "Compromise: Fine + Fast  or  Standard + Ultra Fast"
    ),
    "intent.conflict_ultra_solid_ultra_fast": (
        "Ultra Strong + Ultra Fast are incompatible — thick walls need time."
    ),
    "intent.conflict_ultra_solid_ultra_fast_hint": (
        "Try: Reinforced + Fast  or  Ultra Strong + Standard"
    ),
    "intent.conflict_solid_light": "Ultra Strong and Light are contradictory.",
    "intent.conflict_solid_light_hint": "Choose one based on your needs",
    "intent.conflict_light_outdoor": (
        "A Light part is not recommended for outdoor use."
    ),
    "intent.conflict_light_outdoor_hint": (
        "Recommended: Standard or Reinforced + Outdoor"
    ),
    "intent.conflict_draft_visible": (
        "Draft + Visible finish: 0.28mm resolution won't give a nice finish."
    ),
    "intent.conflict_draft_visible_hint": (
        "Use at least Standard quality for a visible part"
    ),
    "intent.conflict_ultra_fast_visible": (
        "Ultra Fast degrades seams and surface finish."
    ),
    "intent.conflict_ultra_fast_visible_hint": (
        "Recommended: Standard or Fast for a visible part"
    ),

    # ── ParamsPreview ────────────────────────────────────────────────────────
    "preview.empty_title":  "NO PARAMETERS GENERATED",
    "preview.empty_desc":   (
        "Import an STL file\nthen describe your intent\n"
        "to generate the configuration."
    ),
    "preview.summary_title":        "SUMMARY",
    "preview.row_time":             "Estimated time",
    "preview.row_filament":         "Estimated filament",
    "preview.row_quality":          "Print quality",
    "preview.row_strength":         "Strength / infill",
    "preview.row_adhesion":         "Bed adhesion",
    "preview.row_supports":         "Supports",
    "preview.row_temps":            "Temperatures",
    "preview.quality_ultra":        "Ultra Fine ({h} mm)",
    "preview.quality_fine":         "Fine ({h} mm)",
    "preview.quality_standard":     "Standard ({h} mm)",
    "preview.quality_draft":        "Draft ({h} mm)",
    "preview.fill_light":           "Light — {d} %",
    "preview.fill_standard":        "Standard — {d} %",
    "preview.fill_strong":          "Reinforced — {d} %",
    "preview.fill_dense":           "Very dense — {d} %",
    "preview.adhesion_none":        "No brim",
    "preview.adhesion_brim":        "Brim {w} mm",
    "preview.support_none":         "No supports",
    "preview.support_tree":         "Tree supports",
    "preview.support_normal":       "Normal supports",
    "preview.support_classic":      "Normal",
    "preview.supp_classic":         "Normal",
    "preview.support_auto_none":    "Auto — No support",
    "preview.support_auto_tree":    "Auto — Tree",
    "preview.support_auto_normal":  "Auto — Normal",
    "preview.support_forced_none":  "No support (forced)",
    "preview.temps_fmt":            "{nozzle}°C nozzle / {bed}°C bed",

    "preview.sec_mission":      "MISSION PROFILE",
    "preview.lbl_printer":      "PRINTER",
    "preview.lbl_profile":      "PROFILE",
    "preview.lbl_intent":       "INTENT",
    "preview.lbl_confidence":   "CONFIDENCE",

    "preview.sec_layers":       "LAYERS",
    "preview.lbl_layer_h":      "LAYER HEIGHT",
    "preview.lbl_first_layer":  "FIRST LAYER",
    "preview.lbl_wall_gen":     "WALL GENERATOR",
    "preview.lbl_wall_seq":     "WALL ORDER",

    "preview.sec_structure":    "STRUCTURE",
    "preview.lbl_walls":        "WALLS",
    "preview.lbl_top_shells":   "TOP SHELLS",
    "preview.lbl_bot_shells":   "BOT. SHELLS",
    "preview.lbl_single_top":   "SINGLE TOP WALL",
    "preview.val_yes":          "YES",
    "preview.val_no":           "NO",

    "preview.sec_infill":       "INFILL",
    "preview.lbl_density":      "DENSITY",
    "preview.lbl_pattern":      "PATTERN",
    "preview.lbl_surface":      "SURFACE",

    "preview.sec_speeds":       "SPEEDS",
    "preview.lbl_outer_wall":   "OUTER WALL",
    "preview.lbl_inner_wall":   "INNER WALL",
    "preview.lbl_infill":       "INFILL",
    "preview.lbl_first_c":      "FIRST LAYER",
    "preview.lbl_top_surf":     "TOP SURFACE",
    "preview.lbl_bridge":       "BRIDGE",

    "preview.sec_finish":       "FINISH",
    "preview.lbl_seam":         "SEAM",
    "preview.lbl_ironing":      "IRONING",
    "preview.lbl_iron_speed":   "IRON SPEED",
    "preview.lbl_iron_flow":    "IRON FLOW",
    "preview.lbl_elep_foot":    "ELEPH. FOOT",
    "preview.lbl_xy_comp":      "XY COMP.",

    "preview.sec_adhesion":     "ADHESION",
    "preview.lbl_brim_type":    "BRIM TYPE",
    "preview.lbl_brim_w":       "WIDTH",

    "preview.sec_material":     "MATERIAL & MACHINE",
    "preview.lbl_nozzle":       "NOZZLE",
    "preview.lbl_bed":          "BED",
    "preview.lbl_supports":     "SUPPORTS",
    "preview.lbl_threshold":    "THRESHOLD",
    "preview.lbl_plate_only":   "PLATE ONLY",
    "preview.supp_tree":        "Tree",
    "preview.supp_normal":      "Normal",
    "preview.lbl_prime_tower":  "PRIME TOWER",
    "preview.val_active":       "ACTIVE",
    "preview.lbl_flush_ams":    "FLUSH AMS",
    "preview.val_infill":       "INFILL",

    "preview.sec_estimates":    "ESTIMATES",
    "preview.lbl_filament_est": "FILAMENT EST.",
    "preview.lbl_time_est":     "TIME EST.",
    "preview.lbl_volume":       "PART VOLUME",

    # ── Filament / Printer Selector ───────────────────────────────────────────
    "selector.lbl_printer":        "TARGET PRINTER",
    "selector.lbl_filament":       "FILAMENT",
    "selector.lbl_plate":          "BUILD PLATE",
    "selector.validate_btn":       "CONFIRM",
    "selector.nozzle_tip":         "Nozzle diameter installed on the printer",
    "selector.plate_tip":          "Build plate surface type installed on the printer",
    "selector.hint_printer_first": "← Confirm your printer first",
    "selector.compat_ok":          "✓  Compatible with {printer}",
    "selector.compat_incompat":    "✕  {filament} incompatible with {printer}",
    "selector.warn_enclosure":     "Enclosure required — {printer} is open",
    "selector.warn_ams":           "AMS incompatible — direct loading required",
    "selector.warn_bed":           "Bed requires {req}°C > max {max}°C",

    # ── Settings Dialog ───────────────────────────────────────────────────────
    "settings.title":           "SETTINGS",
    "settings.sec_appearance":  "APPEARANCE",
    "settings.dark_theme":      "Dark theme",
    "settings.language":        "Language",
    "settings.sec_print":       "3D PRINTING",
    "settings.printer_default": "Default printer",
    "settings.slicer_output":   "Output slicer",
    "settings.slicer_bambu":    "Bambu Studio",
    "settings.slicer_orca":     "OrcaSlicer",
    "settings.slicer_prusa":    "PrusaSlicer",
    "settings.orient_suggest":  "Suggest optimal orientation",
    "settings.sec_export":      "EXPORT",
    "settings.folder_ph":       "Downloads folder (default)",
    "settings.printer_none":    "(none)",
    "settings.browse_title":    "Choose export folder",
    "settings.restart_notice":  "⚠  Restart required to apply changes",

    # ── Welcome Dialog ────────────────────────────────────────────────────────
    "welcome.title":            "neoSlice",
    "welcome.subtitle":         "AI-POWERED 3D PRINT OPTIMIZER",
    "welcome.copyright":        "© 2026 Emmanuel Percheron",
    "welcome.message":          (
        "Thank you for downloading <b>neoSlice</b>!<br>"
        "This software was entirely designed and developed by <b>Emmanuel Percheron</b>, "
        "to simplify and optimize 3D printing with your printer — Bambu Lab, Creality, "
        "Prusa, Anycubic and many more.<br><br>"
        "I sincerely hope it proves useful in your projects."
    ),
    "welcome.coffee_title":     "☕  This software is <b>completely free</b> and will stay that way.",
    "welcome.coffee_sub":       "If you'd like to support development:",
    "welcome.coffee_btn":       "♥   Support me on Buy Me a Coffee",
    "welcome.no_show":          "Don't show this again",
    "welcome.start_btn":        "Get started →",

    # ── Tutorial ──────────────────────────────────────────────────────────────
    "tuto.skip":    "Skip guide",
    "tuto.prev":    "← Previous",
    "tuto.next":    "Next →",
    "tuto.finish":  "Finish  ✓",

    "tuto.0.title": "Welcome to neoSlice",
    "tuto.0.body":  (
        "neoSlice analyzes your STL file and automatically generates optimal print "
        "parameters for your printer — Bambu Lab, Creality, Prusa, Anycubic and many more.\n\n"
        "This guide walks you through the workflow.\n"
        "Adjust the <b>performance mode</b> in settings "
        "<span style='font-family:Segoe MDL2 Assets;font-size:10pt;'>&#xE713;</span>"
        " to match your machine.\n"
        "Click <b>Next</b> to get started."
    ),
    "tuto.1.title": "① Configuration — Printer, Filament & Bed",
    "tuto.1.body":  (
        "Select your <b>target printer</b> and <b>nozzle diameter</b>, "
        "then click <b>CONFIRM</b>.\n"
        "Do the same for your <b>filament</b>.\n\n"
        "Then choose your <b>bed plate type</b> — neoSlice will automatically "
        "adapt temperatures and adhesion settings."
    ),
    "tuto.2.title": "② STL / OBJ / 3MF Import",
    "tuto.2.body":  (
        "Drag your <b>STL, OBJ or 3MF file</b> into this area, or click to open the file browser.\n\n"
        "neoSlice automatically analyzes the geometry:\n"
        "<b>overhangs · stability · fragile zones</b>\n"
        "<b>volume & dimensions · optimal orientation</b>"
    ),
    "tuto.3.title": "③ Mission Instruction",
    "tuto.3.body":  (
        "Open each accordion to choose your criteria:\n"
        "<b>Quality · Strength · Speed · Supports · Adhesion · Usage · Mode</b>\n\n"
        "The <b>Mode</b> group lets you enable:\n"
        "— <b>Silent</b>: speeds –40% for quieter printing\n"
        "— <b>Multicolor AMS</b>: enables the <b>prime tower</b> "
        "(purge tower that stabilizes color changes) and <b>flush</b> "
        "(automatic nozzle purge between filaments)\n\n"
        "Save your favorite combinations as presets, "
        "then click <b>GENERATE CONFIGURATION →</b>."
    ),
    "tuto.4.title": "④ Export to your slicer",
    "tuto.4.body":  (
        "Once the configuration is generated, the <b>export button</b> is activated.\n\n"
        "neoSlice generates a <b>.3MF</b> file with all parameters optimized "
        "for your material and part geometry.\n\n"
        "Pick your <b>output slicer</b> in settings (Bambu Studio, OrcaSlicer or "
        "PrusaSlicer): the file opens in the right software.\n\n"
        "<b>Material alerts</b> may appear in the analysis panel: "
        "warping risk, recommended drying, AMS incompatibility…"
    ),
    "tuto.5.title": "⑤ Title Bar",
    "tuto.5.body":  (
        "Shortcuts always available:<br><br>"
        "<table cellspacing='0' cellpadding='0' width='100%'>"
        "<tr><td width='28' valign='top' style='padding-top:1px;'>"
        "<span style='font-family:\"Segoe MDL2 Assets\";font-size:11pt;color:#E8F4FF;'>&#xE8BD;</span>"
        "</td><td valign='top'>Report a bug or share your experience. "
        "Opens an online form; your feedback is read personally.</td></tr>"
        "<tr><td colspan='2' height='10'></td></tr>"
        "<tr><td width='28' valign='top' style='padding-top:1px;'>"
        "<b style='color:#E8F4FF;font-size:11pt;'>?</b></td>"
        "<td valign='top'>Relaunch this tutorial.</td></tr>"
        "<tr><td colspan='2' height='10'></td></tr>"
        "<tr><td width='28' valign='top' style='padding-top:2px;'>&#x2615;</td>"
        "<td valign='top'>Support the software's development with a voluntary donation.</td></tr>"
        "<tr><td colspan='2' height='10'></td></tr>"
        "<tr><td width='28' valign='top' style='padding-top:2px;'>"
        "<span style='font-family:\"Segoe MDL2 Assets\";font-size:11pt;color:#E8F4FF;'>&#xE713;</span>"
        "</td>"
        "<td valign='top'>Settings: <b>language</b>, <b>performance mode</b> "
        "(Full / Balanced / Lite), export folder. "
        "A restart is automatically suggested when needed.</td></tr>"
        "</table>"
    ),

    # ── Mise à jour ───────────────────────────────────────────────────────────
    "update.title":         "Update available",
    "update.body":          "neoSlice <b>v{new}</b> is available.<br>You are currently running version <b>v{cur}</b>.",
    "update.notes_label":   "What's new:",
    "update.btn_install":    "Update now",
    "update.btn_later":      "Later",
    "update.downloading":    "Downloading: {pct}%",
    "update.installing":     "Launching installer…",
    "update.failed":         "Download failed.",
    "update.btn_retry":      "Retry",

    # ── PDF ───────────────────────────────────────────────────────────────────
    "pdf.col_param":        "Parameter",
    "pdf.col_value":        "Value",
    "pdf.col_unit":         "Unit",
    "pdf.col_note":         "Note",

    "pdf.filament_subtitle":    "Filament settings sheet",
    "pdf.full_subtitle":        "Full print report",

    "pdf.sec_base":         "Filament tab › Basic information",
    "pdf.flow_ratio":       "Flow ratio",
    "pdf.flow_note":        "Adjust if under/over-extrusion",
    "pdf.softening_temp":   "Softening temperature",

    "pdf.sec_temp":         "Filament tab › Print temperature",
    "pdf.plate_selected":   "Plate type",
    "pdf.bed_first":        "Bed — 1st layer",
    "pdf.bed_other":        "Bed — other layers",
    "pdf.nozzle_first":     "Nozzle — 1st layer",
    "pdf.nozzle_other":     "Nozzle — Other layers",

    "pdf.sec_vol":          "Filament tab › Volumetric speed",
    "pdf.vol_max":          "Maximum volumetric speed",
    "pdf.vol_adaptive":     "Adaptive volumetric speed",
    "pdf.vol_disabled":     "Disabled",

    "pdf.sec_fan":          "Cooling tab › Part cooling fan",
    "pdf.fan_first_layer":  "Fan 1st layer",
    "pdf.fan_first_note":   "Never cool 1st layer",
    "pdf.fan_min":          "Fan minimum threshold",
    "pdf.fan_max_thresh":   "Fan MAX speed threshold",
    "pdf.fan_always":       "Fan always on",
    "pdf.fan_slow_cool":    "Slow down to cool",
    "pdf.fan_no_slow_outer":"Don't slow outer walls",
    "pdf.fan_min_speed":    "Minimum print speed",
    "pdf.fan_force_oh":     "Force fan for overhangs",
    "pdf.fan_oh_thresh":    "Fan overhangs beyond",
    "pdf.fan_oh_speed":     "Overhang fan speed",

    "pdf.sec_retract":      "Advanced tab › Retraction",
    "pdf.retract_len":      "Retraction length",
    "pdf.retract_force":    "FORCE if indicated",
    "pdf.retract_speed":    "Retraction speed",
    "pdf.retract_dsp":      "Deretraction speed",
    "pdf.retract_long":     "Long retraction (cut)",
    "pdf.retract_long_dist":"Long retraction distance",
    "pdf.drying":           "Recommended drying: {value}",

    "pdf.sec_geometry":     "Geometric analysis",
    "pdf.dimensions":       "Dimensions (X × Y × Z)",
    "pdf.volume":           "Part volume",
    "pdf.surface":          "Surface",
    "pdf.verdict":          "Overall verdict",
    "pdf.verdict_ok":       "READY TO PRINT",
    "pdf.verdict_warn":     "CONFIGURATION ADAPTED — CHECK IN YOUR SLICER",
    "pdf.verdict_bad":      "COMPLEX PART",
    "pdf.overhangs":        "Overhangs",
    "pdf.oh_angle":         "Max angle {angle}°",
    "pdf.stability":        "Stability",
    "pdf.fragility":        "Fragility",
    "pdf.min_wall":         "Min wall {t} mm",
    "pdf.supports_needed":  "Supports required",
    "pdf.supp_vol":         "Est. volume {r}%",
    "pdf.orient_suggested": "Suggested orientation",
    "pdf.orient_current":   "Current (Z+)",
    "pdf.orient_improve":   "+{pct}%",

    "pdf.sec_params":       "Print parameters (generated by neoSlice)",
    "pdf.time_est":         "Estimated time",
    "pdf.time_with_supp":   "with supports",
    "pdf.filament_est":     "Estimated filament",
    "pdf.layer_h":          "Layer height",
    "pdf.infill":           "Infill",
    "pdf.wall_loops":       "Wall loops",
    "pdf.top_bot_layers":   "Top/bot. layers",
    "pdf.outer_wall_spd":   "Outer wall speed",
    "pdf.infill_spd":       "Infill speed",
    "pdf.supports":         "Supports",
    "pdf.supp_off":         "Disabled",
    "pdf.supp_on":          "Enabled",
    "pdf.brim":             "Adhesion (brim)",
    "pdf.profile_name":     "neoSlice profile",

    "pdf.sec_filament_temp":"Filament settings — Temperatures",
    "pdf.bed_first2":       "Bed — 1st layer",
    "pdf.bed_other2":       "Bed — other layers",
    "pdf.nozzle_first2":    "Nozzle — 1st layer",
    "pdf.nozzle_other2":    "Nozzle — other layers",

    "pdf.sec_filament_fan": "Filament settings — Fan",
    "pdf.fan_max":          "Max fan speed",
    "pdf.fan_always2":      "Fan always on",
    "pdf.fan_min2":         "Min fan threshold",
    "pdf.print_min_spd":    "Min print speed",

    "pdf.sec_filament_ret": "Filament settings — Retraction",
    "pdf.retract_len2":     "Retraction length",
    "pdf.retract_force2":   "FORCE",
    "pdf.retract_speed2":   "Retraction speed",

    "pdf.yes":              "Yes",
    "pdf.no":               "No",
    "pdf.na":               "N/A",
    "pdf.na_auto":          "N/A (auto-managed)",
    "pdf.header_fmt":       "Filament: {filament}  |  Printer: {printer}  |  {date}",
    "pdf.footer_note":      (
        "Print parameters (quality, speed, supports, adhesion) are embedded "
        "in the 3MF file generated by neoSlice and do not require manual "
        "configuration in your slicer."
    ),
    "pdf.generated_by":     "Generated by neoSlice v{version}",

    # ── Splash ────────────────────────────────────────────────────────────────
    "splash.loading":       "Loading...",
    "splash.tagline":       "AI-Powered 3D Print Optimizer",

    # ── Settings / Performance ────────────────────────────────────────────────
    "settings.sec_performance":      "PERFORMANCE",
    "settings.perf_mode":            "Performance mode",
    "settings.perf_full":            "Full",
    "settings.perf_balanced":        "Balanced",
    "settings.perf_lite":            "Lite",
    "settings.perf_test_btn":        "Test my configuration",
    "settings.perf_testing":         "Testing...",
    "settings.perf_result_full":     "Fast config — Full mode recommended ✓",
    "settings.perf_result_balanced": "Mid-range config — Balanced mode recommended",
    "settings.perf_result_lite":     "Slow config — Lite mode recommended",
    "settings.perf_full_desc":       "All analyses active: overhangs, stability and fragility.",
    "settings.perf_balanced_desc":   "Overhang and stability analyses active. Orientation optimizer disabled (significant time saving).",
    "settings.perf_lite_desc":       "Stability analysis only. Overhangs and orientation disabled. Recommended for slow PCs.",
    "settings.restart_btn":          "Restart now",

    "settings.sec_updates":          "UPDATES",
    "settings.update_check_btn":     "Check now",
    "settings.update_checking":      "Checking…",
    "settings.update_uptodate":      "neoSlice is up to date ✓",
    "settings.update_found":         "Update available!",

    # ── neoSlice Pro / License ────────────────────────────────────────────────
    "pro.paywall_subtitle":          "You've used your free photo diagnostics.\nUnlock unlimited diagnostics.",
    "pro.price_suffix":              "{price} · one-time payment, lifetime",
    "pro.unlock_btn":                "Unlock neoSlice Pro",
    "pro.already_bought":            "Already purchased? Paste your license key",
    "pro.key_placeholder":           "XXXX-XXXX-XXXX-XXXX",
    "pro.activate_btn":              "Activate",
    "pro.later_btn":                 "Later",
    "pro.activating":                "Activating…",
    "pro.thanks_title_end":          "activated!",
    "pro.thanks_subtitle":           "Thank you for your support! Here's what you just unlocked:",
    "pro.benefit_unlimited":         "Unlimited AI photo diagnostics",
    "pro.benefit_corrections":       "Fixes applied to your config in one click",
    "pro.benefit_lifetime":          "Lifetime access, on 3 devices",
    "pro.benefit_support":           "You support neoSlice's development",
    "pro.thanks_btn":                "Get started",
    "pro.trial_counter":             "Free trials: {restants}/{total}",
    "pro.coming_soon_short":         "Coming soon",
    "pro.coming_soon_text":          "neoSlice Pro is coming very soon!",
    "pro.coming_soon_info":          "AI photo diagnostics and the quote calculator will be available in an upcoming update.\n\nThank you for your patience!",
    "pro.settings_status_pro":       "Active ✓ — unlimited photo diagnostics, lifetime",
    "pro.settings_status_free":      "Free version — {restants}/{total} free diagnostics left",
    "pro.settings_btn_upgrade":      "Upgrade to neoSlice Pro",
    "pro.settings_btn_deactivate":   "Deactivate this device",
    "license.empty_key":             "Please paste your license key.",
    "license.already_active":        "neoSlice Pro is already active on this device.",
    "license.activated":             "neoSlice Pro activated. Thank you for your support!",
    "license.refused":               "Key rejected (error {code}).",
    "license.server_error":          "Server error (HTTP {code}).",
    "license.no_connection":         "No internet connection — activation happens once online.",
    "license.no_connection_retry":   "No internet connection — please try again online.",
    "license.unexpected":            "Unexpected error: {error}",
    "license.invalid_or_max":        "Invalid key or already used on the maximum number of devices.",
    "license.removed":               "License removed from this device.",
    "license.deactivated":           "Device deactivated — activation slot freed.",

    # ── Diagnostic photo ──────────────────────────────────────────────────────
    "diag.uncertain_title":          "Uncertain analysis",
    "diag.uncertain_desc":           "The model isn't confident enough to decide. Take a clearer photo: frame the defect area well, good lighting, neutral background, no blur.",
    "diag.mode_photo":               "Analyze a photo",
    "diag.mode_manual":              "I know the problem",
    "diag.manual_pick":              "Which problem are you facing?",
    "diag.manual_show":              "SHOW CORRECTIONS",
    "diag.manual_badge":             "Manually selected",
    "diag.consent_revoke_note":      "You can revoke your consent at any time in the settings.",
    "diag.model_unavailable":        "Model unavailable — check your internet connection.",
    "diag.analyzing":                "Analyzing…",
    "diag.downloading_model":        "Downloading improved model… {pct}%",

    # ── Pro workspace (workshop management) ────────────────────────────────────
    "pro.space_btn":                 "PRO SPACE",
    "pro.space_tooltip":             "Workshop management: spools, quotes, clients, invoicing",
    "pro.hub_title":                 "Pro Space — Workshop management",
    "pro.tab_spools":                "Spools",
    "pro.tab_quote":                 "Quote",
    "pro.tab_clients":               "Clients",
    "pro.tab_invoice":               "Invoicing",
    "pro.tab_dashboard":             "Dashboard",
    "pro.tab_orders":                "Orders",
    "pro.tab_products":              "Products",
    "pro.edit":                      "Edit",
    # ── Orders (production queue) ──
    "ord.new":            "New order",
    "ord.none":           "No orders yet.",
    "ord.intro":          "Track your orders from intake to payment.",
    "ord.client":         "Client",
    "ord.status":         "Status",
    "ord.due":            "Due date",
    "ord.spool":          "Spool (stock deduction)",
    "ord.grams":          "Filament (g)",
    "ord.notes":          "Notes",
    "ord.label":          "Description",
    "ord.save":           "Save order",
    "ord.create_title":   "New order",
    "ord.edit_title":     "Edit order",
    "ord.advance":        "Advance →",
    "ord.to_invoice":     "Invoice",
    "ord.delete":         "Delete order",
    "ord.delete_confirm": "Delete order {number}?",
    "ord.from_quote":     "→ Order",
    "ord.cancel_order":   "Cancel order",
    "ord.no_client":      "— No client —",
    "ord.no_spool":       "— None (no deduction) —",
    "ord.section_active": "IN PROGRESS",
    "ord.section_done":   "COMPLETED / ARCHIVED",
    "ord.due_in":         "in {n} d",
    "ord.overdue_days":   "{n} d late",
    "ord.status_todo":      "To do",
    "ord.status_printing":  "Printing",
    "ord.status_done":      "Done",
    "ord.status_delivered": "Delivered",
    "ord.status_paid":      "Paid",
    "ord.status_cancelled": "Cancelled",
    "ord.created":        "Order {number} created.",
    "ord.stock_note":     "Stock is deducted automatically when moving to “Printing”.",
    "ord.consumptions":   "Filament usage (1 line per color)",
    "ord.add_color":      "＋ Add a color",
    "ord.pdf":            "Work order",
    "ord.total":          "TOTAL",
    "ordpdf.title":       "WORK ORDER",
    "ordpdf.footer":      "Internal production document — neoSlice",
    "ordpdf.unassigned":  "(spool unassigned)",
    "ord.est_mono":       "Single color: estimate pre-filled — adjust to your slicer if needed.",
    "ord.fill_multi":     "Multi-color: no estimate possible — enter each color's usage.",
    # ── Products (recurring catalog) ──
    "art.new":            "New product",
    "art.none":           "No products yet. Create your recurring items to insert them in 1 click.",
    "art.intro":          "Your recurring products: save once, reuse everywhere.",
    "art.name":           "Product name",
    "art.price":          "Price (excl. tax)",
    "art.grams":          "Filament (g)",
    "art.duration":       "Duration (h)",
    "art.notes":          "Notes",
    "art.save":           "Save product",
    "art.create_title":   "New product",
    "art.edit_title":     "Edit product",
    "art.delete":         "Delete",
    "art.delete_confirm": "Delete product “{name}”?",
    # ── Invoice reminders / due dates ──
    "fact.overdue":       "OVERDUE",
    "fact.relance":       "Send reminder",
    "fact.echeance":      "Due date",
    "fact.relance_title": "Payment reminder",
    "fact.copy":          "Copy",
    "fact.relance_done":  "Reminder logged. Copy the message below for your client:",
    "fact.relance_msg":   "Hello,\n\nUnless we are mistaken, invoice {number} for {amount} remains unpaid (due date: {due}).\nWe would be grateful if you could arrange payment.\n\nBest regards,\n{company}",
    # ── Dashboard (production / overdue / report) ──
    "dash.sec_orders":    "PRODUCTION",
    "dash.orders_active": "Active orders",
    "dash.orders_todo":   "To print",
    "dash.month_billed":  "This month",
    "dash.overdue":       "Overdue invoices",
    "dash.overdue_amount":"Amount overdue",
    "dash.report_title":  "REVENUE — LAST 6 MONTHS",
    "dash.export":        "Export accounting (CSV)",
    "dash.export_done":   "Accounting export saved: {path}",
    "dash.export_none":   "No invoice to export.",
    "dash.legend_paid":   "Collected",
    "dash.legend_billed": "Billed (pending)",
    # ── Stock / reorder ──
    "spool.threshold":    "Reorder threshold (g)",
    "shop.title":         "SHOPPING LIST",
    "shop.none":          "Stock OK — nothing to reorder.",
    "shop.remaining":     "{g} g left",
    "shop.missing":       "reorder 1 spool of {g} g",
    "pro.coming_soon":               "Coming soon",
    "pro.coming_soon_desc":          "This module is coming in a future update.",
    "pro.backup":                    "Back up my data",
    "pro.backup_done":               "Data backed up: {path}",
    "pro.export":                    "Export my data",
    "pro.import":                    "Import data",
    "pro.export_done":               "Data exported: {path}",
    "pro.import_confirm":            "Importing will replace your current data (spools, quotes…). A backup copy is kept. Continue?",
    "pro.import_done":               "{n} file(s) imported. Data restored.",
    "pro.autosave":                  "💾 Auto-save on",
    # Spool inventory
    "spool.add":                     "Add a spool",
    "spool.edit":                    "Edit spool",
    "spool.delete":                  "Delete",
    "spool.delete_confirm":          "Delete this spool permanently?",
    "spool.empty":                   "No spools yet.\nAdd your first spool to track your stock.",
    "spool.save":                    "Save",
    "spool.cancel":                  "Cancel",
    "spool.material":                "Material",
    "spool.brand":                   "Brand",
    "spool.color":                   "Color",
    "spool.color_name":              "Color name",
    "spool.finish":                  "Finish",
    "spool.total_g":                 "New weight (g)",
    "spool.remaining_g":             "Remaining weight (g)",
    "spool.tare_g":                  "Empty spool weight (g)",
    "spool.cost_total":              "Price paid",
    "spool.cost_kg":                 "Cost/kg",
    "spool.vendor":                  "Vendor",
    "spool.purchase_date":           "Purchase date",
    "spool.location":                "Location",
    "spool.lot":                     "Lot no.",
    "spool.notes":                   "Notes",
    "spool.remaining":               "left",
    "spool.low_stock":               "Low stock",
    "spool.low_stock_banner":        "{n} spool(s) low on stock",
    "spool.section_id":              "Identity",
    "spool.section_stock":           "Stock & cost",
    "spool.section_extra":           "Details",
    "spool.deduct_title":            "Filament used",
    "spool.deduct_prompt":           "Deduct ~{g} g from your stock?",
    "spool.deduct_choose":           "Spool to deduct from",
    "spool.deduct_none":             "Don't deduct",
    "spool.deduct_ok":               "{g} g deducted from {name}",
    "spool.use_for_quote":           "Spool (auto cost)",

    # ── Invoicing (Pro Space) ──────────────────────────────────────────────────
    "fact.status_draft":   "Draft",
    "fact.status_sent":    "Sent",
    "fact.status_paid":    "Paid",
    "fact.sec_company":    "My company",
    "fact.sec_new":        "New invoice",
    "fact.sec_saved":      "Saved invoices",
    "fact.c_name":         "Name / company",
    "fact.c_form":         "Legal form",
    "fact.c_address":      "Address",
    "fact.c_zip":          "Postal code",
    "fact.c_city":         "City",
    "fact.c_email":        "Email",
    "fact.c_phone":        "Phone",
    "fact.c_taxid":        "Tax / VAT no.",
    "fact.legal_section":  "Legal mentions (by country)",
    "fact.f_siret":        "SIRET No.",
    "fact.f_rcs":          "Trade register (RCS/RM)",
    "fact.f_capital":      "Share capital",
    "fact.f_regime":       "VAT regime",
    "fact.regime_normal":  "VAT registered",
    "fact.regime_franchise": "VAT-exempt (small business, art. 293 B)",
    "fact.f_steuernr":     "Tax number (Steuernummer)",
    "fact.f_handelsreg":   "Commercial register (Handelsregister)",
    "fact.f_bce":          "Company No. (BCE)",
    "fact.f_rcsl":         "Trade register (RCSL)",
    "fact.f_companyno":    "Company number",
    "fact.f_busno":        "Business Number (GST/HST)",
    "fact.f_kvk":          "KvK No.",
    "fact.f_rea":          "REA No.",
    "fact.f_nif":          "NIF / CIF",
    "fact.f_firmenbuch":   "Company register (FN)",
    "fact.f_recovery":     "Late-payment recovery fee",
    "fact.doc_lang":       "Document language",
    "fact.doc_lang_auto":  "Auto (by country)",
    "fact.c_iban":         "IBAN",
    "fact.c_terms":        "Payment terms",
    "fact.country":        "Country",
    "fact.save_company":   "💾  Save company",
    "fact.company_saved":  "Company details saved.",
    "fact.client":         "Client",
    "fact.bill_country":   "Billing country",
    "fact.date":           "Date",
    "fact.due":            "Due date",
    "fact.vat_rate":       "VAT rate (%)",
    "fact.discount":       "Discount (%)",
    "fact.col_desig":      "Description",
    "fact.col_qty":        "Qty",
    "fact.col_pu":         "Unit price",
    "fact.add_line":       "＋ Add a line",
    "fact.notes_ph":       "Notes / message (optional)…",
    "fact.total_ht":       "Subtotal (excl. tax)",
    "fact.discount_l":     "Discount",
    "fact.vat":            "VAT",
    "fact.total_ttc":      "TOTAL (incl. tax)",
    "fact.net_ht":         "Net (excl. tax)",
    "fact.save_invoice":   "Save invoice",
    "fact.gen_pdf":        "Generate PDF",
    "fact.empty":          "No invoices saved yet.",
    "fact.need_line":      "Add at least one line.",
    "fact.invoice":        "Invoice",
    "fact.saved_msg":      "Invoice {number} saved.",
    "fact.delete":         "Delete",
    "fact.delete_confirm": "Delete invoice {number}?",
    "fact.pdf":            "PDF",
    "fact.pdf_invoice":    "INVOICE",
    "fact.pdf_num":        "No.",
    "fact.pdf_billto":     "Bill to",
    "fact.pdf_your_company": "Your company",
    "fact.pdf_footer":     "Invoice generated by neoSlice",
    "fact.from_quote":     "Based on quote {number}.",
    "fact.client_select":  "Saved client",
    "fact.client_none":    "— Manual entry —",
    "fact.client_save":    "＋ Save this client",
    "fact.client_saved":   "Client added to directory.",

    # ── Clients (light CRM) ────────────────────────────────────────────────────
    "client.add":            "Add a client",
    "client.edit":           "Edit client",
    "client.delete":         "Delete",
    "client.delete_confirm": "Delete this client? (their quotes/invoices are kept)",
    "client.empty":          "No clients yet.\nAdd your first client or save one from an invoice.",
    "client.save":           "Save",
    "client.cancel":         "Cancel",
    "client.name":           "Contact name",
    "client.company":        "Company",
    "client.address":        "Address",
    "client.zip":            "Postal code",
    "client.city":           "City",
    "client.country":        "Country",
    "client.email":          "Email",
    "client.phone":          "Phone",
    "client.taxid":          "Tax / VAT no.",
    "client.notes":          "Notes",
    "client.n_quotes":       "{n} quotes",
    "client.n_invoices":     "{n} invoices",
    "client.billed":         "Billed",
    "client.paid":           "Paid",
    "client.due":            "Due",
    "client.history":        "History",
    "client.section_quotes": "Quotes",
    "client.section_invoices": "Invoices",
    "client.back":           "← Back to clients",
    "client.open":           "Open profile",

    # ── Dashboard ──────────────────────────────────────────────────────────────
    "dash.sec_activity":   "ACTIVITY",
    "dash.sec_docs":       "DOCUMENTS",
    "dash.sec_stock":      "FILAMENT STOCK",
    "dash.billed":         "Revenue",
    "dash.paid":           "Collected",
    "dash.due":            "Outstanding",
    "dash.invoices":       "Invoices",
    "dash.unpaid":         "incl. {n} unpaid",
    "dash.quotes":         "Quotes",
    "dash.clients":        "Clients",
    "dash.spools":         "Spools",
    "dash.stock_g":        "Filament left",
    "dash.stock_value":    "Stock value",
    "dash.low_stock":      "{n} low on stock",
    "dash.welcome":        "Welcome to your Pro Space",
    "dash.welcome_sub":    "Manage your spools, quotes, invoices and clients — all local and auto-saved.",

    # ── Cost / quote calculator (Pro) ──────────────────────────────────────────
    "cost.btn":                      "QUOTE",
    "cost.tooltip":                  "Calculate cost price and generate a quote",
    "cost.title":                    "COST CALCULATOR",
    "cost.save_quote":               "SAVE QUOTE",
    "cost.quote_saved":              "Quote {number} saved.",
    "cost.saved_quotes":             "Saved quotes",
    "cost.no_quotes":                "No quotes saved yet.",
    "cost.to_invoice":               "→ Invoice",
    "cost.to_invoice_full":          "Convert to invoice",
    "cost.converted":                "Converted → invoice {number}",
    "cost.del":                      "Delete",
    "cost.del_quote_confirm":        "Delete quote {number}?",
    "cost.section_rates":            "MY RATES (saved)",
    "cost.rates_note":               "Pre-filled values are indicative (2025-2026 averages) — adjust to your contract and a power meter for more accuracy.",
    "cost.section_print":            "THIS PRINT",
    "cost.part_name":                "Part name",
    "cost.quantity":                 "Quantity",
    "cost.country":                  "Country",
    "cost.currency":                 "Currency",
    "cost.kwh":                      "Electricity ({cur}/kWh)",
    "cost.filament_price":           "Filament ({cur}/kg)",
    "cost.machine_price":            "Machine price ({cur})",
    "cost.machine_life":             "Machine lifespan (h)",
    "cost.labor_rate":               "Hourly rate ({cur}/h)",
    "cost.failure":                  "Failure rate (%)",
    "cost.margin":                   "Profit margin (%)",
    "cost.packaging":                "Packaging ({cur}/part)",
    "cost.weight":                   "Weight (g / part)",
    "cost.time":                     "Print time (h / part)",
    "cost.labor_min":                "Labor (min)",
    "cost.power":                    "Printer power (W)",
    "cost.estimated_note":           "⚠️ Weight and time auto-estimated by neoSlice — for an accurate quote, replace them with the exact figures shown by your slicer after slicing.",
    "cost.row_material":             "Material",
    "cost.row_electricity":          "Electricity",
    "cost.row_wear":                 "Machine wear",
    "cost.row_labor":                "Labor",
    "cost.row_packaging":            "Packaging",
    "cost.row_failure":              "Failure buffer",
    "cost.total":                    "COST PRICE",
    "cost.distribution":             "COST BREAKDOWN",
    "cost.suggested_prices":         "SUGGESTED PRICES",
    "cost.tier_eco":                 "Eco",
    "cost.tier_standard":            "Standard",
    "cost.tier_premium":             "Premium",
    "cost.tier_custom":              "Custom",
    "cost.margin_row":               "Margin",
    "cost.sale_price":               "SUGGESTED SALE PRICE",
    "cost.total_qty":                "Total ({n} pcs)",
    "cost.export_pdf":               "EXPORT QUOTE (PDF)",
    "cost.close":                    "Close",
    "cost.quote_heading":            "QUOTE",
    "cost.quote_part":               "Part",
    "cost.quote_date":               "Date",
    "cost.quote_qty":                "Quantity",
    "cost.pdf_saved":                "Quote saved: {path}",
    "cost.pdf_error":                "Could not create PDF: {error}",
    "cost.quote_disclaimer":         "Estimate provided for information, subject to change. Valid for 30 days from the date of issue.",
}

# ── Engine ────────────────────────────────────────────────────────────────────

_current: dict[str, str] = _FR


def set_lang(lang: str) -> None:
    global _current
    if lang == "en":
        _current = _EN
    else:
        _current = _FR


def lang() -> str:
    """Code de la langue active ('en' ou 'fr')."""
    return "en" if _current is _EN else "fr"


def _(key: str, **kwargs) -> str:
    """Retourne la traduction du key dans la langue active."""
    s = _current.get(key) or _FR.get(key, key)
    if kwargs:
        try:
            return s.format(**kwargs)
        except (KeyError, ValueError):
            return s
    return s


# Initialiser depuis les prefs au démarrage
try:
    from core.prefs import PREFS as _p
    set_lang(_p.get("lang", "fr"))
except Exception:
    pass
