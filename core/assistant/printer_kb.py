"""Base de faits IMPRIMANTES injectee a l'assistant Oen, de facon CIBLEE.

But : donner a Oen des faits fiables et verifies sur la machine REELLEMENT
concernee (celle configuree dans neoSlice, ou celle citee dans la question), sans
noyer le contexte du modele 7B avec tout le catalogue. On n'injecte donc que la ou
les machines pertinentes, jamais l'encyclopedie complete.

Deux niveaux :
  1. FAITS PAR MODELE (_MODELS) pour les machines les plus courantes : firmware
     (donc OU se fait la calibration), cadre ouvert/ferme (donc conseil materiau),
     extrudeur direct/bowden, nivellement auto, buse acier trempe pour les charges,
     multicouleur, slicer natif.
  2. ECOSYSTEME PAR MARQUE (_BRANDS) : ligne courte quand on ne connait pas le
     modele precis (slicer, famille de firmware, ecran, type de cadre).

Faits Bambu Lab : GENERES depuis data/printers.py (PRINTERS + printer_specs) pour
rester rigoureusement coherents avec ce que neoSlice genere lui-meme.

Style : ASCII sans accents (comme engine.py / ui_map.py). Le modele repond en
francais accentue ; ces chaines ne sont que des faits internes.
"""
from __future__ import annotations

# ── Ecosysteme par marque (faits surs, valables meme sans le modele exact) ──────
_BRANDS: dict[str, str] = {
    "bambu": (
        "Ecosysteme Bambu Lab : pilotage par l'ECRAN tactile de la machine + Bambu "
        "Studio / Bambu Handy. Calibrations largement AUTOMATIQUES (flow dynamique, "
        "compensation de vibrations, nivellement auto par capteur) lancees depuis "
        "l'ecran. Reglages d'impression dans Bambu Studio (ou OrcaSlicer). AMS = "
        "multicouleur."),
    "creality": (
        "Ecosysteme Creality : slicer Creality Print ou OrcaSlicer. Selon le modele, "
        "firmware Marlin (menu LCD sur la machine : Auto Home, Bed Leveling, Z-offset, "
        "PID) OU Klipper (K1, machines 'V3' recentes -> interface web Fluidd/Creality + "
        "printer.cfg + macros). Beaucoup de modeles ont un capteur de nivellement auto "
        "(CR-Touch)."),
    "prusa": (
        "Ecosysteme Prusa : slicer PrusaSlicer (natif), assistants et calibrations "
        "integres a l'ecran de la machine (Calibration, First Layer Calibration). "
        "Firmware maison type Marlin. Documentation officielle tres complete."),
    "anycubic": (
        "Ecosysteme Anycubic : slicer Anycubic (fork), Cura ou OrcaSlicer. Nivellement "
        "auto LeviQ. Les Kobra recentes (Kobra 3, S1) sont a base de Klipper (interface "
        "web) ; les Kobra 2 sont plutot Marlin (menu ecran)."),
    "elegoo": (
        "Ecosysteme Elegoo (FDM) : slicer Elegoo Slicer ou OrcaSlicer. Neptune 4 et "
        "modeles recents = Klipper (interface web, haute vitesse) ; Neptune 3 = Marlin "
        "(menu ecran)."),
    "sovol": (
        "Ecosysteme Sovol : slicer OrcaSlicer / Cura. SV06 = Marlin (menu LCD), "
        "direct drive tout-metal ; SV07 et SV08 = Klipper (interface web). Machines "
        "tres 'bidouillables' (souvent passees sous Klipper par l'utilisateur)."),
    "qidi": (
        "Ecosysteme Qidi : slicer Qidi Studio (fork OrcaSlicer). Machines Klipper "
        "(interface web) CoreXY, souvent FERMEES avec chambre chauffee -> adaptees aux "
        "materiaux techniques (ABS/ASA/PC/nylon)."),
    "flashforge": (
        "Ecosysteme Flashforge : slicer Orca-Flashforge / FlashPrint. Adventurer 5M et "
        "5M Pro = Klipper (interface web) CoreXY haute vitesse ; la 5M Pro est fermee."),
    "anker": (
        "Ecosysteme AnkerMake : slicer AnkerMake ou OrcaSlicer. M5 / M5C = bed slinger "
        "rapide avec camera, pilotage par l'appli et l'ecran."),
    "flsun": (
        "Ecosysteme FLSun : imprimantes DELTA (colonnes verticales), Klipper recent "
        "(interface web Mainsail/Fluidd), tres rapides. Calibration delta specifique "
        "(hauteur/rayon), nivellement automatique par sonde."),
    "voron": (
        "Ecosysteme Voron : imprimantes DIY CoreXY (kit ou auto-sourcees), 100% "
        "Klipper -> tout se regle dans printer.cfg + macros (BED_MESH_CALIBRATE, "
        "SCREWS_TILT_CALCULATE, PROBE_CALIBRATE, PID_CALIBRATE, PRESSURE_ADVANCE, "
        "SHAPER_CALIBRATE), interface web Mainsail/Fluidd. 2.4 et Trident = fermees "
        "(materiaux techniques) ; V0 = petite fermee ; Switchwire = ouverte."),
    "ratrig": (
        "Ecosysteme RatRig : kits DIY CoreXY sous Klipper (Mainsail/Fluidd, "
        "printer.cfg). V-Core = grand format, souvent ferme ; V-Minion = compacte."),
    "snapmaker": (
        "Ecosysteme Snapmaker : machines modulaires (3D / laser / CNC), slicer Luban "
        "ou OrcaSlicer. J1 et Artisan = IDEX (double extrudeur independant) fermees ; "
        "series 2.0/A350 = modulaires ouvertes."),
    "raise3d": (
        "Ecosysteme Raise3D : machines FERMEES semi-pro, slicer ideaMaker. Pro3/Pro2 = "
        "double extrudeur, E2 = IDEX. Ecran tactile embarque."),
    "ultimaker": (
        "Ecosysteme UltiMaker : slicer Cura (natif). Extrudeurs BOWDEN, double buse sur "
        "la serie S (S3/S5/S7), S5/S7 fermees. Materiaux via profils Cura, ecran "
        "embarque."),
    "artillery": (
        "Ecosysteme Artillery : slicer Cura / OrcaSlicer. Sidewinder = grand format bed "
        "slinger, direct drive (Titan). X1/X2 = Marlin (menu LCD) ; X3 recentes = "
        "Klipper (interface web)."),
    "kingroon": (
        "Ecosysteme Kingroon : machines budget, direct drive. Marlin (menu LCD) sur les "
        "KP3S ; certains modeles passent sous Klipper. Slicer Cura / OrcaSlicer."),
    "twotrees": (
        "Ecosysteme TwoTrees : machines budget CoreXY ou bed slinger. Marlin ou Klipper "
        "selon le modele. Slicer Cura / OrcaSlicer."),
    "biqu": (
        "Ecosysteme BIQU (BigTreeTech) : Hurakan = Klipper (interface web) livree pretes ; "
        "autres modeles Marlin ou Klipper. Slicer OrcaSlicer / Cura."),
    "geeetech": (
        "Ecosysteme Geeetech : machines budget i3, firmware Marlin (menu LCD), bed "
        "slinger ouvert. Slicer Cura / OrcaSlicer."),
    "tronxy": (
        "Ecosysteme Tronxy : machines budget / grand format, Marlin (menu LCD) le plus "
        "souvent, bed slinger ouvert. Slicer Cura / OrcaSlicer."),
    "lulzbot": (
        "Ecosysteme LulzBot : machines ouvertes RepRap (Marlin), slicer Cura LulzBot "
        "Edition. Extrudeur direct drive robuste."),
    "phrozen": (
        "Ecosysteme Phrozen : constructeur taiwanais surtout connu pour ses imprimantes "
        "RESINE (Sonic Mini/Mighty : la calibration y est exposition/nivellement du "
        "film, PAS un nivellement FDM). Leur machine FDM est l'Arco : Klipper "
        "(interface web), slicer type OrcaSlicer."),
}

# Alias de marque -> cle _BRANDS (pour detecter la marque dans un texte libre).
_BRAND_ALIASES: dict[str, str] = {
    "bambu": "bambu", "bambulab": "bambu",
    "creality": "creality", "ender": "creality", "cr-10": "creality", "cr10": "creality",
    "prusa": "prusa",
    "anycubic": "anycubic", "kobra": "anycubic",
    "elegoo": "elegoo", "neptune": "elegoo", "centauri": "elegoo",
    "sovol": "sovol",
    "qidi": "qidi",
    "flashforge": "flashforge", "adventurer": "flashforge",
    "anker": "anker", "ankermake": "anker",
    "flsun": "flsun",
    "voron": "voron",
    "ratrig": "ratrig", "rat rig": "ratrig",
    "snapmaker": "snapmaker",
    "raise3d": "raise3d", "raise 3d": "raise3d",
    "ultimaker": "ultimaker",
    "artillery": "artillery", "sidewinder": "artillery",
    "kingroon": "kingroon",
    "twotrees": "twotrees", "two trees": "twotrees",
    "biqu": "biqu",
    "geeetech": "geeetech",
    "tronxy": "tronxy",
    "lulzbot": "lulzbot",
    "phrozen": "phrozen", "arco": "phrozen",
}


# ── Faits par modele (machines les plus courantes) ──────────────────────────────
# Chaque entree : aliases (sous-chaines minuscules a chercher), brand (cle _BRANDS),
# facts (chaine ASCII). Les aliases les plus SPECIFIQUES doivent gagner : la
# recherche prefere l'alias le plus long.
_MODELS: list[dict] = [
    # ── Creality ────────────────────────────────────────────────────────────
    {"brand": "creality", "aliases": ["ender-3 v3 ke", "ender 3 v3 ke", "ender3 v3 ke", "ender 3 v3ke"],
     "facts": "Creality Ender-3 V3 KE : KLIPPER (interface web + ecran), bed slinger, "
              "direct drive, nivellement auto (CR-Touch) + input shaping, plateau PEI. "
              "Cadre OUVERT (pas d'enceinte) : PLA/PETG oui, ABS deconseille sans caisson."},
    {"brand": "creality", "aliases": ["ender-3 v3 se", "ender 3 v3 se", "ender3 v3 se"],
     "facts": "Creality Ender-3 V3 SE : Marlin (menu LCD), bed slinger, direct drive "
              "'Sprite', nivellement auto (CR-Touch) + capteur Z, plateau PC. Cadre "
              "OUVERT : PLA/PETG oui, ABS deconseille sans caisson. Entree de gamme."},
    {"brand": "creality", "aliases": ["ender-3 v3 plus", "ender 3 v3 plus"],
     "facts": "Creality Ender-3 V3 Plus : Klipper, plus grand plateau, direct drive, "
              "nivellement auto. Cadre ouvert : ABS deconseille sans caisson."},
    {"brand": "creality", "aliases": ["ender-3 v3", "ender 3 v3", "ender3 v3"],
     "facts": "Creality Ender-3 V3 (CoreXY) : KLIPPER (interface web + ecran), direct "
              "drive, tres rapide, nivellement auto + input shaping. Cadre OUVERT : "
              "ABS deconseille sans caisson."},
    {"brand": "creality", "aliases": ["ender-3 s1", "ender 3 s1", "ender3 s1"],
     "facts": "Creality Ender-3 S1 (/Pro/Plus) : Marlin (menu LCD), bed slinger, direct "
              "drive 'Sprite', nivellement auto CR-Touch. Cadre OUVERT : ABS a eviter "
              "sans caisson. Slicer Creality Print / OrcaSlicer."},
    {"brand": "creality", "aliases": ["ender-3 v2", "ender 3 v2", "ender3 v2"],
     "facts": "Creality Ender-3 V2 : Marlin (menu LCD), bed slinger, extrudeur BOWDEN "
              "(retraction plus longue ~4-6mm), nivellement MANUEL (molettes) sauf ajout "
              "BLTouch. Cadre OUVERT : PLA ideal, ABS a eviter sans caisson."},
    {"brand": "creality", "aliases": ["ender-3 pro", "ender 3 pro"],
     "facts": "Creality Ender-3 Pro : Marlin (menu LCD), bed slinger, BOWDEN, nivellement "
              "MANUEL. Cadre ouvert. PLA/PETG. Machine tres repandue et documentee."},
    {"brand": "creality", "aliases": ["ender-3", "ender 3", "ender3"],
     "facts": "Creality Ender-3 (stock) : Marlin (menu LCD : Auto Home, Level, PID), bed "
              "slinger, extrudeur BOWDEN (retraction ~4-6mm), nivellement MANUEL aux "
              "molettes. Cadre OUVERT : PLA ideal, ABS deconseille sans caisson. "
              "Slicer Creality Print / OrcaSlicer / Cura."},
    {"brand": "creality", "aliases": ["ender-5", "ender 5", "ender5"],
     "facts": "Creality Ender-5 : cube (plateau qui descend en Z), plus rigide que "
              "l'Ender-3, Marlin (menu LCD) selon version. Caissonnable pour l'ABS."},
    {"brand": "creality", "aliases": ["k1 max", "k1max"],
     "facts": "Creality K1 Max : KLIPPER, CoreXY FERMEE, direct drive, tres rapide, "
              "grand volume, camera IA, nivellement auto + input shaping. Buse standard "
              "laiton (option acier trempe pour CF). Enceinte fermee -> ABS/ASA OK ; "
              "pour le PLA, ouvrir/aerer. Interface web + ecran."},
    {"brand": "creality", "aliases": ["k1c", "k1 c"],
     "facts": "Creality K1C : KLIPPER, CoreXY FERMEE, direct drive, buse ACIER TREMPE "
              "d'origine (adaptee carbone/CF), rapide, nivellement auto + input shaping. "
              "Enceinte fermee -> ABS/ASA OK ; PLA : aerer."},
    {"brand": "creality", "aliases": ["k1"],
     "facts": "Creality K1 : KLIPPER, CoreXY FERMEE, direct drive, tres rapide (input "
              "shaping), nivellement auto, camera. Buse laiton standard. Enceinte fermee "
              "-> ABS/ASA OK ; pour le PLA, ouvrir/aerer. Interface web + ecran."},
    {"brand": "creality", "aliases": ["cr-10", "cr10"],
     "facts": "Creality CR-10 (series) : GRAND format, Marlin (menu LCD), bed slinger "
              "ouvert, souvent BOWDEN. Nivellement manuel (ou BLTouch selon version). "
              "PLA/PETG ; ABS difficile (grand volume ouvert)."},

    # ── Prusa ────────────────────────────────────────────────────────────────
    {"brand": "prusa", "aliases": ["mk4s", "mk4 s"],
     "facts": "Prusa MK4S : Marlin 32-bit (xBuddy), bed slinger, extrudeur Nextruder "
              "direct drive, calibration 1re couche par LOADCELL (auto Z), input shaping. "
              "Cadre OUVERT : PLA/PETG parfaits, ABS/ASA a caissonner. Slicer PrusaSlicer."},
    {"brand": "prusa", "aliases": ["mk4"],
     "facts": "Prusa MK4 : Marlin 32-bit, bed slinger, Nextruder direct drive, 1re couche "
              "auto par loadcell, input shaping (firmware recent). Cadre OUVERT : ABS a "
              "caissonner. Slicer PrusaSlicer natif."},
    {"brand": "prusa", "aliases": ["mk3s", "mk3 s", "mk3"],
     "facts": "Prusa MK3S/MK3S+ : Marlin, bed slinger, direct drive (Bondtech), sonde "
              "SuperPINDA, calibration 1re couche assistee a l'ecran. Cadre OUVERT : "
              "PLA/PETG ideal, ABS a caissonner. Reference tres documentee. PrusaSlicer."},
    {"brand": "prusa", "aliases": ["mini"],
     "facts": "Prusa MINI/MINI+ : Marlin, bed slinger compact, extrudeur (bowden court), "
              "sonde de nivellement, ecran. Cadre OUVERT : PLA/PETG. PrusaSlicer natif."},
    {"brand": "prusa", "aliases": ["core one", "core-one"],
     "facts": "Prusa CORE One : CoreXY FERMEE (enceinte), Marlin, direct drive, 1re "
              "couche auto par loadcell, input shaping. Enceinte -> ABS/ASA/PC OK ; pour "
              "le PLA, ouvrir/aerer. Slicer PrusaSlicer natif."},
    {"brand": "prusa", "aliases": ["prusa xl", "xl "],
     "facts": "Prusa XL : CoreXY grand format, jusqu'a 5 tetes (toolchanger multi-"
              "materiaux/couleurs), loadcell, semi-ouverte (enceinte en option). "
              "PrusaSlicer natif."},

    # ── Anycubic ──────────────────────────────────────────────────────────────
    {"brand": "anycubic", "aliases": ["kobra s1", "kobra-s1"],
     "facts": "Anycubic Kobra S1 : CoreXY FERMEE, base KLIPPER, direct drive, rapide, "
              "multicouleur via module ACE Pro. Enceinte -> ABS/ASA OK ; PLA : aerer. "
              "Nivellement auto LeviQ."},
    {"brand": "anycubic", "aliases": ["kobra 3 max", "kobra3 max"],
     "facts": "Anycubic Kobra 3 Max : GRAND format, base Klipper, bed slinger, direct "
              "drive, multicouleur via ACE Pro, nivellement auto LeviQ. Cadre ouvert : "
              "ABS difficile (grand volume)."},
    {"brand": "anycubic", "aliases": ["kobra 3", "kobra3"],
     "facts": "Anycubic Kobra 3 : base KLIPPER, bed slinger, direct drive, rapide, "
              "multicouleur via module ACE Pro, nivellement auto LeviQ. Cadre OUVERT : "
              "PLA/PETG ; ABS deconseille sans caisson. Slicer Anycubic / Orca."},
    {"brand": "anycubic", "aliases": ["kobra 2 pro", "kobra 2 max", "kobra 2 plus", "kobra 2 neo", "kobra 2"],
     "facts": "Anycubic Kobra 2 (Neo/Pro/Plus/Max) : Marlin (menu ecran), bed slinger, "
              "direct drive, nivellement auto LeviQ. Cadre OUVERT : PLA/PETG ; ABS a "
              "eviter sans caisson. Slicer Anycubic / Cura / Orca."},
    {"brand": "anycubic", "aliases": ["kobra"],
     "facts": "Anycubic Kobra : bed slinger, direct drive, nivellement auto LeviQ, cadre "
              "OUVERT (PLA/PETG ; ABS a caissonner). Selon la generation : Kobra 2 = "
              "Marlin (ecran), Kobra 3 / S1 = Klipper (interface web)."},

    # ── Elegoo ────────────────────────────────────────────────────────────────
    {"brand": "elegoo", "aliases": ["centauri carbon"],
     "facts": "Elegoo Centauri Carbon : CoreXY FERMEE, KLIPPER, direct drive, buse "
              "ACIER TREMPE (adaptee carbone/CF), rapide, nivellement auto. Enceinte -> "
              "ABS/ASA/PC OK ; PLA : aerer. Slicer Elegoo Slicer / Orca."},
    {"brand": "elegoo", "aliases": ["centauri"],
     "facts": "Elegoo Centauri : CoreXY FERMEE, KLIPPER, direct drive, rapide, "
              "nivellement auto. Enceinte -> ABS/ASA OK ; PLA : aerer."},
    {"brand": "elegoo", "aliases": ["neptune 4 max", "neptune 4 plus", "neptune 4 pro", "neptune 4"],
     "facts": "Elegoo Neptune 4 (Pro/Plus/Max) : KLIPPER (interface web), bed slinger, "
              "direct drive, tres rapide (input shaping), nivellement auto. Cadre "
              "OUVERT : PLA/PETG ; ABS a caissonner. Slicer Elegoo Slicer / Orca."},
    {"brand": "elegoo", "aliases": ["neptune 3", "neptune 3 pro", "neptune 3 plus", "neptune 3 max"],
     "facts": "Elegoo Neptune 3 (Pro/Plus/Max) : Marlin (menu ecran), bed slinger, "
              "direct drive, nivellement auto. Cadre OUVERT : PLA/PETG ; ABS a eviter."},

    # ── Sovol ─────────────────────────────────────────────────────────────────
    {"brand": "sovol", "aliases": ["sv08"],
     "facts": "Sovol SV08 : CoreXY (base Voron 2.4), KLIPPER, direct drive, grand "
              "volume, tres rapide, caissonnable. Interface web Klipper. Kit a monter."},
    {"brand": "sovol", "aliases": ["sv07"],
     "facts": "Sovol SV07 (/Plus) : KLIPPER (interface web), bed slinger, direct drive, "
              "rapide (input shaping), nivellement auto, hotend tout-metal. Cadre "
              "OUVERT : ABS a caissonner."},
    {"brand": "sovol", "aliases": ["sv06 plus", "sv06plus"],
     "facts": "Sovol SV06 Plus : Marlin (menu LCD), bed slinger, direct drive tout-"
              "metal (~300C), nivellement auto, plus grand volume que la SV06. Souvent "
              "passee sous Klipper. Cadre OUVERT."},
    {"brand": "sovol", "aliases": ["sv06"],
     "facts": "Sovol SV06 : Marlin (menu LCD), bed slinger, direct drive TOUT-METAL "
              "(jusqu'a ~300C, donc PETG/ASA plus facile), nivellement auto, plateau "
              "PEI. Cadre OUVERT : ABS a caissonner. Tres bon rapport qualite/prix."},

    # ── Qidi ──────────────────────────────────────────────────────────────────
    {"brand": "qidi", "aliases": ["q1 pro", "q1pro"],
     "facts": "Qidi Q1 Pro : CoreXY FERMEE avec CHAMBRE CHAUFFEE (~60C), KLIPPER, direct "
              "drive, rapide. Adaptee ABS/ASA/PC/nylon. Slicer Qidi Studio (Orca)."},
    {"brand": "qidi", "aliases": ["plus4", "plus 4"],
     "facts": "Qidi Plus4 : CoreXY FERMEE, CHAMBRE CHAUFFEE active (jusqu'a ~65C), "
              "KLIPPER, buse haute temperature. Concue pour materiaux techniques "
              "(PC/nylon/PA-CF). Slicer Qidi Studio."},
    {"brand": "qidi", "aliases": ["x-max 3", "xmax 3", "x-max3"],
     "facts": "Qidi X-Max 3 : CoreXY FERMEE grand format, CHAMBRE CHAUFFEE, KLIPPER, "
              "rapide. Materiaux techniques OK. Slicer Qidi Studio."},
    {"brand": "qidi", "aliases": ["x-plus 3", "xplus 3", "x-plus3"],
     "facts": "Qidi X-Plus 3 : CoreXY FERMEE, CHAMBRE CHAUFFEE, KLIPPER, direct drive, "
              "rapide. Adaptee ABS/ASA/PC/nylon. Slicer Qidi Studio (Orca)."},
    {"brand": "qidi", "aliases": ["x-smart 3", "xsmart 3"],
     "facts": "Qidi X-Smart 3 : CoreXY compacte FERMEE, KLIPPER, direct drive, rapide. "
              "Enceinte -> ABS/ASA OK. Slicer Qidi Studio."},

    # ── Phrozen ───────────────────────────────────────────────────────────────
    {"brand": "phrozen", "aliases": ["arco"],
     "facts": "Phrozen Arco : imprimante FDM (la seule FDM de Phrozen, connu pour la "
              "resine), KLIPPER (interface web), plateau 300x300 mm, rapide, "
              "multicouleur via le module Chroma Kit. Slicer type OrcaSlicer. "
              "Calibrations depuis l'ecran/interface web (nivellement auto)."},

    # ── Flashforge ────────────────────────────────────────────────────────────
    {"brand": "flashforge", "aliases": ["creator 5 pro", "creator5 pro"],
     "facts": "Flashforge Creator 5 Pro : base KLIPPER (interface web), plateau "
              "256x256 mm, rapide. Slicer Orca-Flashforge / OrcaSlicer. Calibrations "
              "(nivellement auto, input shaping) depuis l'ecran ou l'interface web."},
    {"brand": "flashforge", "aliases": ["creator 5", "creator5"],
     "facts": "Flashforge Creator 5 : base KLIPPER (interface web), plateau 256x256 mm, "
              "rapide. Slicer Orca-Flashforge / OrcaSlicer. Calibrations (nivellement "
              "auto, input shaping) depuis l'ecran ou l'interface web."},
    {"brand": "flashforge", "aliases": ["adventurer 5m pro", "5m pro"],
     "facts": "Flashforge Adventurer 5M Pro : CoreXY FERMEE, KLIPPER, direct drive, "
              "tres rapide, filtration. Enceinte -> ABS/ASA OK ; PLA : aerer. Slicer "
              "Orca-Flashforge / FlashPrint."},
    {"brand": "flashforge", "aliases": ["adventurer 5m", "5m"],
     "facts": "Flashforge Adventurer 5M : CoreXY, KLIPPER, direct drive, tres rapide "
              "(input shaping), nivellement auto. Version de base OUVERTE (ABS a "
              "caissonner). Slicer Orca-Flashforge."},

    # ── Anker ─────────────────────────────────────────────────────────────────
    {"brand": "anker", "aliases": ["m5c", "m5 c"],
     "facts": "AnkerMake M5C : bed slinger rapide, direct drive, pilotage par appli "
              "(pas d'ecran complet), bouton unique. Cadre OUVERT : ABS a caissonner. "
              "Slicer AnkerMake / OrcaSlicer."},
    {"brand": "anker", "aliases": ["m5"],
     "facts": "AnkerMake M5 : bed slinger rapide, direct drive, ecran tactile + camera "
              "IA, nivellement auto. Cadre OUVERT : PLA/PETG ; ABS a caissonner."},

    # ── Snapmaker ─────────────────────────────────────────────────────────────
    {"brand": "snapmaker", "aliases": ["artisan"],
     "facts": "Snapmaker Artisan : modulaire (3D/laser/CNC), en mode 3D = IDEX (double "
              "extrudeur independant) FERME. Materiaux techniques OK. Slicer Luban / Orca."},
    {"brand": "snapmaker", "aliases": ["j1"],
     "facts": "Snapmaker J1 : IDEX (double extrudeur independant) FERME, rapide, "
              "modes copie/miroir. Enceinte -> ABS/ASA OK. Slicer Luban / OrcaSlicer."},

    # ── Artillery ─────────────────────────────────────────────────────────────
    {"brand": "artillery", "aliases": ["sidewinder x3", "sw x3"],
     "facts": "Artillery Sidewinder X3 : bed slinger grand format, base KLIPPER "
              "(interface web) sur les versions recentes, direct drive. Cadre ouvert."},
    {"brand": "artillery", "aliases": ["sidewinder x2", "sidewinder x1", "sidewinder"],
     "facts": "Artillery Sidewinder (X1/X2) : GRAND format bed slinger, Marlin (menu "
              "LCD), direct drive (Titan), plateau AC rapide a chauffer. Cadre ouvert : "
              "PLA/PETG ; ABS difficile (grand volume)."},

    # ── UltiMaker ─────────────────────────────────────────────────────────────
    {"brand": "ultimaker", "aliases": ["s5", "s7", "s3"],
     "facts": "UltiMaker serie S (S3/S5/S7) : FERMEES, double buse BOWDEN (retraction "
              "longue), slicer Cura natif, profils materiaux robustes. Semi-pro."},
]


def _norm(s: str) -> str:
    return (s or "").lower().replace("_", " ")


def _bambu_fact(name: str) -> str:
    """Genere un fait Bambu depuis les donnees du code (coherence garantie)."""
    from data.printers import PRINTERS, printer_specs
    p = PRINTERS.get(name)
    if not p:
        return ""
    sp = printer_specs(name)
    ferme = p.get("enceinte")
    slinger = sp.get("bed_slinger")
    parts = [f"Bambu Lab {name} :"]
    parts.append("CoreXY" if not slinger else "bed slinger (serie A)")
    parts.append("ENCEINTE FERMEE" if ferme else "cadre OUVERT (open frame)")
    if p.get("double_extrudeur"):
        parts.append("double extrudeur")
    if p.get("multi_couleur"):
        cmax = p.get("couleurs_max")
        parts.append(f"multicouleur via AMS{f' (jusqu a {cmax})' if cmax else ''}")
    parts.append(f"buse max {p.get('buse_max_temp')}C, plateau max {p.get('plateau_max_temp')}C")
    vol = p.get("volume")
    if vol:
        parts.append(f"volume {vol}")
    base = ", ".join(parts[:1]) + " " + ", ".join(parts[1:]) + "."
    # Conseil enceinte coherent avec la regle generale.
    if ferme:
        base += (" Enceinte fermee : ABS/ASA/PC/nylon OK ; pour le PLA/PETG, OUVRIR la "
                 "porte et retirer le capot du haut (evite le fluage thermique).")
    else:
        base += (" Cadre ouvert : PLA/PETG ideal ; pour l'ABS/ASA il faut un caisson "
                 "(pas d'enceinte d'origine).")
    base += (" Calibrations automatiques depuis l'ecran + Bambu Studio ; neoSlice ne "
             "pilote pas la machine.")
    return base


# Alias Bambu -> cle PRINTERS.
_BAMBU_ALIASES: dict[str, str] = {
    "x1 carbon": "X1 Carbon", "x1c": "X1 Carbon", "x1-carbon": "X1 Carbon",
    "x1e": "X1E", "x2d": "X2D", "x1 ": "X1 Carbon",
    "p1s": "P1S", "p2s": "P2S", "p1p": "P1", "p1 ": "P1",
    "a1 mini": "A1 Mini", "a1mini": "A1 Mini", "a2l": "A2L", "a1 ": "A1", "a1": "A1",
    "h2s": "H2S", "h2c": "H2C", "h2d pro": "H2D Pro", "h2d": "H2D",
}


def _match_models(text: str) -> list[tuple[str, str]]:
    """Renvoie [(facts, brand)] pour les modeles detectes, du plus specifique au
    moins specifique, sans doublon de famille (l'alias le plus long gagne)."""
    hits: list[tuple[str, str, str]] = []   # (alias_matche, facts, brand)
    for entry in _MODELS:
        for al in entry["aliases"]:
            if al in text:
                hits.append((al, entry["facts"], entry["brand"]))
                break
    # Bambu (genere)
    for al, key in _BAMBU_ALIASES.items():
        if al in text:
            f = _bambu_fact(key)
            if f:
                hits.append((al, f, "bambu"))
    # Trie par specificite (alias le plus long d'abord)
    hits.sort(key=lambda h: len(h[0]), reverse=True)
    out: list[tuple[str, str]] = []
    used_aliases: list[str] = []
    seen_facts: set[str] = set()
    for al, facts, brand in hits:
        # Ignore si un alias deja retenu contient celui-ci (meme famille, moins precis)
        if any(al in u or u in al for u in used_aliases):
            continue
        if facts in seen_facts:
            continue
        used_aliases.append(al)
        seen_facts.add(facts)
        out.append((facts, brand))
        if len(out) >= 2:      # au plus 2 machines -> contexte leger
            break
    return out


def _match_brands(text: str, already: set[str]) -> list[str]:
    found: list[str] = []
    for al, key in _BRAND_ALIASES.items():
        if key in already:
            continue
        if al in text and key not in found and key in _BRANDS:
            found.append(key)
    return found[:1]           # au plus 1 ligne d'ecosysteme en complement


def facts_for(query: str, printer: str = "", max_chars: int = 1600) -> str:
    """Bloc de faits imprimante a injecter, CIBLE sur la machine configuree dans
    neoSlice (`printer`) et/ou celle citee dans `query`. Chaine vide si rien de sur.

    On privilegie la machine CONFIGUREE (contexte reel) : ses faits passent en tete.
    """
    text = _norm(printer) + "  " + _norm(query)
    if not text.strip():
        return ""
    models = _match_models(text)
    brands_present = {b for _f, b in models}

    blocks: list[str] = [f for f, _b in models]
    # Complement ecosysteme uniquement si aucun modele precis trouve pour cette marque.
    for key in _match_brands(text, brands_present):
        blocks.append(_BRANDS[key])

    if not blocks:
        return ""

    out, total = [], 0
    for b in blocks:
        if total + len(b) > max_chars:
            break
        out.append(b)
        total += len(b)
    if not out:
        return ""
    return ("FAITS IMPRIMANTE (verifies, fiables : appuie-toi dessus et ne les "
            "contredis pas avec ta memoire ; tu ne les RECITES pas, tu t'en sers pour "
            "repondre juste). Si la machine de l'utilisateur n'est pas decrite ici et "
            "que le modele change la reponse, demande la marque et le modele exacts :\n\n"
            + "\n\n".join(out))
