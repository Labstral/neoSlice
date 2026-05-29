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
    "app.title":            "NEOSLICE",
    "app.subtitle":         "AI-POWERED 3D PRINT OPTIMIZER",
    "app.beta":             "BÊTA",
    "app.btn_new_piece":    "↺  NOUVELLE PIÈCE",
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
    "export.btn":               "↓  EXPORTER .3MF  →  BAMBU STUDIO",
    "export.dialog_title":      "Enregistrer le fichier .3MF",
    "export.dialog_filter":     "Fichiers 3MF (*.3mf)",
    "export.success_title":     "✓   Fichier 3MF généré avec succès",
    "export.success_info":      (
        "Les paramètres d'impression (qualité, vitesse, supports…) sont intégrés dans le 3MF.<br>"
        "Les paramètres du <b>filament</b> (températures, ventilation, débit) doivent être "
        "configurés manuellement dans Bambu Studio."
    ),
    "export.dlg_title":         "Fichier .3MF généré",
    "export.btn_bambu":         "  Ouvrir dans Bambu Studio",
    "export.btn_pdf":           "  Fiche filament PDF",
    "export.btn_close":         "Fermer",

    # ── DropZone ─────────────────────────────────────────────────────────────
    "drop.main_locked":     "VALIDEZ L'IMPRIMANTE",
    "drop.sub_locked":      "et le filament pour continuer\nÉtape ①",
    "drop.main":            "GLISSER FICHIER STL",
    "drop.sub":             "ou cliquer pour parcourir",
    "drop.dialog_title":    "Ouvrir un fichier STL",
    "drop.dialog_filter":   "Fichiers 3D (*.stl *.obj);;Tous les fichiers (*)",
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
    "analysis.verdict_warn":"⚠  CONFIGURATION ADAPTÉE — CONTRÔLER DANS BAMBU STUDIO",
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
    "analysis.lite_mode_warn":  "⚠ Mode Économique — surplombs non analysés · vérifiez les supports dans Bambu Studio",

    "analysis.tip_oh":   (
        "Surplombs : zones inclinées à plus de 45° sans matière en-dessous.\n"
        "Élevé → activez les supports dans Bambu Studio pour éviter l'effondrement."
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
    "viewer.show_plate":        "▦  Plateau",
    "viewer.auto_rotate":       "⟳  Rotation auto",
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

    # UI
    "intent.lock_msg":          "Chargez un fichier STL\npour accéder aux réglages",
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
    "preview.support_tree":         "Supports arborescents",
    "preview.support_normal":       "Supports normaux",
    "preview.temps_fmt":            "{nozzle}°C buse / {bed}°C plateau",

    # Sections
    "preview.sec_mission":      "MISSION PROFILE",
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
    "settings.orient_suggest":  "Suggérer l'orientation optimale",
    "settings.sec_export":      "EXPORT",
    "settings.folder_ph":       "Dossier Téléchargements (par défaut)",
    "settings.printer_none":    "(aucune)",
    "settings.browse_title":    "Choisir le dossier d'export",
    "settings.restart_notice":  "⚠  Redémarrage requis pour appliquer la langue",

    # ── Welcome Dialog ────────────────────────────────────────────────────────
    "welcome.title":            "neoSlice",
    "welcome.subtitle":         "AI-POWERED 3D PRINT OPTIMIZER",
    "welcome.beta":             "BÊTA",
    "welcome.copyright":        "© 2026 Emmanuel Percheron",
    "welcome.message":          (
        "Merci d'avoir téléchargé <b>neoSlice</b> !<br>"
        "Ce logiciel a été entièrement conçu et développé par <b>Emmanuel Percheron</b>, "
        "pour simplifier et optimiser l'impression 3D avec les imprimantes Bambu Lab.<br><br>"
        "J'espère sincèrement qu'il vous sera utile dans vos projets."
    ),
    "welcome.beta_box":         (
        "<b style='color:{amber}'>⚠  Version Bêta</b><br>"
        "<span style='color:{label}'>Ce logiciel est en développement actif. "
        "Des correctifs et de nouvelles fonctionnalités seront apportés régulièrement. "
        "Si vous rencontrez un problème, n'hésitez pas à le signaler.</span>"
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
        "d'impression optimaux pour vos imprimantes Bambu Lab.\n\n"
        "Ce guide vous présente les étapes du workflow.\n"
        "Adaptez le <b>mode de performance</b> dans les paramètres "
        "<span style='font-family:Segoe MDL2 Assets;font-size:10pt;'>&#xE713;</span>"
        " selon votre machine.\n"
        "Cliquez sur <b>Suivant</b> pour commencer."
    ),
    "tuto.1.title": "① Configuration — Imprimante & Filament",
    "tuto.1.body":  (
        "Sélectionnez votre <b>imprimante cible</b> et votre <b>diamètre de buse</b>, "
        "puis cliquez sur <b>VALIDER →</b>.\n"
        "Faites de même pour votre <b>filament</b>.\n\n"
        "neoSlice adapte automatiquement les paramètres selon le matériau choisi."
    ),
    "tuto.2.title": "② Import STL",
    "tuto.2.body":  (
        "Glissez votre <b>fichier STL</b> dans cette zone, ou cliquez pour ouvrir "
        "l'explorateur de fichiers.\n\n"
        "neoSlice analyse automatiquement la géométrie :\n"
        "<b>surplombs · stabilité · zones fragiles</b>\n"
        "<b>volume & dimensions · orientation optimale</b>\n\n"
        "En <b>mode Économique</b>, l'analyse des surplombs est désactivée — "
        "vérifiez les supports directement dans Bambu Studio.\n\n"
        "Une suggestion de rotation est affichée si elle améliore significativement "
        "l'imprimabilité."
    ),
    "tuto.3.title": "③ Instruction Mission",
    "tuto.3.body":  (
        "Ouvrez chaque accordéon pour choisir vos critères :\n"
        "<b>Qualité · Résistance · Vitesse · Adhérence · Usage · Mode</b>\n\n"
        "Le groupe <b>Mode</b> permet d'activer :\n"
        "— <b>Silencieux</b> : vitesses –40 % pour moins de bruit\n"
        "— <b>Multicolore AMS</b> : active la <b>prime tower</b> "
        "(tour de purge qui stabilise les changements de couleur) et le <b>flush</b> "
        "(purge automatique de la buse entre chaque filament)\n\n"
        "Sauvegardez vos combinaisons favorites en présets, "
        "puis cliquez sur <b>GÉNÉRER CONFIGURATION →</b>."
    ),
    "tuto.4.title": "④ Export vers Bambu Studio",
    "tuto.4.body":  (
        "Une fois la configuration générée, le <b>bouton d'export</b> s'active.\n\n"
        "neoSlice génère un fichier <b>.3MF</b> avec tous les paramètres optimisés "
        "selon votre matériau et la géométrie de la pièce.\n\n"
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
    "pdf.verdict_warn":     "CONFIGURATION ADAPTÉE — CONTRÔLER DANS BAMBU STUDIO",
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
        "manuelle dans Bambu Studio."
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
    "settings.perf_full_desc":       "Toutes les analyses sont actives : surplombs, stabilité, fragilité et optimisation d'orientation. Rotation auto activée par défaut.",
    "settings.perf_balanced_desc":   "Analyses surplombs et stabilité actives. Optimisation d'orientation désactivée (gain de temps notable).",
    "settings.perf_lite_desc":       "Seule l'analyse de stabilité est active. Surplombs et orientation désactivés. Rotation auto désactivée. Recommandé pour les PC lents.",
    "settings.restart_btn":          "Redémarrer maintenant",

    "settings.sec_updates":          "MISES À JOUR",
    "settings.update_check_btn":     "Vérifier maintenant",
    "settings.update_checking":      "Vérification en cours…",
    "settings.update_uptodate":      "neoSlice est à jour ✓",
    "settings.update_found":         "Mise à jour disponible !",
}

# ── English ───────────────────────────────────────────────────────────────────

_EN: dict[str, str] = {

    # ── Application / TopBar ──────────────────────────────────────────────────
    "app.title":            "NEOSLICE",
    "app.subtitle":         "AI-POWERED 3D PRINT OPTIMIZER",
    "app.beta":             "BETA",
    "app.btn_new_piece":    "↺  NEW PART",
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
    "export.btn":               "↓  EXPORT .3MF  →  BAMBU STUDIO",
    "export.dialog_title":      "Save .3MF file",
    "export.dialog_filter":     "3MF Files (*.3mf)",
    "export.success_title":     "✓   3MF file generated successfully",
    "export.success_info":      (
        "Print parameters (quality, speed, supports…) are embedded in the 3MF.<br>"
        "The <b>filament</b> parameters (temperatures, cooling, flow rate) must be "
        "configured manually in Bambu Studio."
    ),
    "export.dlg_title":         ".3MF file generated",
    "export.btn_bambu":         "  Open in Bambu Studio",
    "export.btn_pdf":           "  Filament PDF sheet",
    "export.btn_close":         "Close",

    # ── DropZone ─────────────────────────────────────────────────────────────
    "drop.main_locked":     "CONFIRM PRINTER",
    "drop.sub_locked":      "and filament to continue\nStep ①",
    "drop.main":            "DROP STL FILE",
    "drop.sub":             "or click to browse",
    "drop.dialog_title":    "Open an STL file",
    "drop.dialog_filter":   "3D Files (*.stl *.obj);;All files (*)",
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
    "analysis.verdict_warn":"⚠  CONFIGURATION ADAPTED — CHECK IN BAMBU STUDIO",
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
    "analysis.lite_mode_warn":  "⚠ Lite mode — overhangs not analyzed · check supports in Bambu Studio",

    "analysis.tip_oh":   (
        "Overhangs: areas angled more than 45° with no material below.\n"
        "High → enable supports in Bambu Studio to prevent collapse."
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
    "viewer.show_plate":        "▦  Build plate",
    "viewer.auto_rotate":       "⟳  Auto rotate",
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

    "intent.lock_msg":          "Load an STL file\nto access settings",
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
    "preview.temps_fmt":            "{nozzle}°C nozzle / {bed}°C bed",

    "preview.sec_mission":      "MISSION PROFILE",
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
    "settings.orient_suggest":  "Suggest optimal orientation",
    "settings.sec_export":      "EXPORT",
    "settings.folder_ph":       "Downloads folder (default)",
    "settings.printer_none":    "(none)",
    "settings.browse_title":    "Choose export folder",
    "settings.restart_notice":  "⚠  Restart required to apply language",

    # ── Welcome Dialog ────────────────────────────────────────────────────────
    "welcome.title":            "neoSlice",
    "welcome.subtitle":         "AI-POWERED 3D PRINT OPTIMIZER",
    "welcome.beta":             "BETA",
    "welcome.copyright":        "© 2026 Emmanuel Percheron",
    "welcome.message":          (
        "Thank you for downloading <b>neoSlice</b>!<br>"
        "This software was entirely designed and developed by <b>Emmanuel Percheron</b>, "
        "to simplify and optimize 3D printing with Bambu Lab printers.<br><br>"
        "I sincerely hope it proves useful in your projects."
    ),
    "welcome.beta_box":         (
        "<b style='color:{amber}'>⚠  Beta Version</b><br>"
        "<span style='color:{label}'>This software is in active development. "
        "Fixes and new features will be added regularly. "
        "If you encounter an issue, don't hesitate to report it.</span>"
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
        "parameters for your Bambu Lab printers.\n\n"
        "This guide walks you through the workflow.\n"
        "Adjust the <b>performance mode</b> in settings "
        "<span style='font-family:Segoe MDL2 Assets;font-size:10pt;'>&#xE713;</span>"
        " to match your machine.\n"
        "Click <b>Next</b> to get started."
    ),
    "tuto.1.title": "① Configuration — Printer & Filament",
    "tuto.1.body":  (
        "Select your <b>target printer</b> and <b>nozzle diameter</b>, "
        "then click <b>CONFIRM →</b>.\n"
        "Do the same for your <b>filament</b>.\n\n"
        "neoSlice automatically adapts parameters based on the chosen material."
    ),
    "tuto.2.title": "② STL Import",
    "tuto.2.body":  (
        "Drag your <b>STL file</b> into this area, or click to open the file browser.\n\n"
        "neoSlice automatically analyzes the geometry:\n"
        "<b>overhangs · stability · fragile zones</b>\n"
        "<b>volume & dimensions · optimal orientation</b>\n\n"
        "In <b>Lite mode</b>, overhang analysis is disabled — "
        "check supports directly in Bambu Studio.\n\n"
        "An orientation suggestion is displayed if it significantly improves printability."
    ),
    "tuto.3.title": "③ Mission Instruction",
    "tuto.3.body":  (
        "Open each accordion to choose your criteria:\n"
        "<b>Quality · Strength · Speed · Adhesion · Usage · Mode</b>\n\n"
        "The <b>Mode</b> group lets you enable:\n"
        "— <b>Silent</b>: speeds –40% for quieter printing\n"
        "— <b>Multicolor AMS</b>: enables the <b>prime tower</b> "
        "(purge tower that stabilizes color changes) and <b>flush</b> "
        "(automatic nozzle purge between filaments)\n\n"
        "Save your favorite combinations as presets, "
        "then click <b>GENERATE CONFIGURATION →</b>."
    ),
    "tuto.4.title": "④ Export to Bambu Studio",
    "tuto.4.body":  (
        "Once the configuration is generated, the <b>export button</b> is activated.\n\n"
        "neoSlice generates a <b>.3MF</b> file with all parameters optimized "
        "for your material and part geometry.\n\n"
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
    "pdf.verdict_warn":     "CONFIGURATION ADAPTED — CHECK IN BAMBU STUDIO",
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
        "configuration in Bambu Studio."
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
    "settings.perf_full_desc":       "All analyses active: overhangs, stability, fragility and orientation optimizer. Auto-rotation enabled by default.",
    "settings.perf_balanced_desc":   "Overhang and stability analyses active. Orientation optimizer disabled (significant time saving).",
    "settings.perf_lite_desc":       "Stability analysis only. Overhangs and orientation disabled. Auto-rotation disabled. Recommended for slow PCs.",
    "settings.restart_btn":          "Restart now",

    "settings.sec_updates":          "UPDATES",
    "settings.update_check_btn":     "Check now",
    "settings.update_checking":      "Checking…",
    "settings.update_uptodate":      "neoSlice is up to date ✓",
    "settings.update_found":         "Update available!",
}

# ── Engine ────────────────────────────────────────────────────────────────────

_current: dict[str, str] = _FR


def set_lang(lang: str) -> None:
    global _current
    if lang == "en":
        _current = _EN
    else:
        _current = _FR


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
