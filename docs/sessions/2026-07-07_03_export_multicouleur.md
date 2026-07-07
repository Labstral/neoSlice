# Export multicouleur (Pro) : etat complet (2026-07-07)

Fonction Pro : apres l'export 3MF d'un fichier multi-couleur, neoSlice calcule le poids de filament par slot de couleur, laisse l'utilisateur associer ses bobines, colore l'apercu 3D en direct, decompte le stock de l'Espace Pro et ecrit les couleurs dans le 3MF.

## Parcours utilisateur

1. Export 3MF d'un fichier multi-objets (assemblage couleur) ou d'un STL peint dans Bambu Studio.
2. Le dialogue de succes d'export integre le panneau couleur (UNE seule fenetre, choix d'Emmanuel : plus de fenetre separee qui s'ouvrait avant le dialogue slicer). Panneau non modal, ancre a droite.
3. Pour chaque slot detecte : poids estime en grammes, choix de la bobine (ou saisie manuelle), apercu colore en direct dans le viewer.
4. Avertissement affiche : « ne fermez pas cette fenetre tant que vous n'avez pas slice ».
5. Si aucune bobine ne correspond : bouton qui ouvre l'Espace Pro directement sur l'onglet Bobines (`_open_pro_hub(initial_tab="spools")`, selection d'onglet differee dans `showEvent` de pro_hub, sinon bug d'affichage).
6. Validation : decompte du stock multi-couleur + patch `filament_colour` dans le 3MF.

## Fichiers

| Fichier | Role |
|---|---|
| `core/export/color_breakdown.py` | Calcul du poids par slot (`ColorBreakdownWidget`) |
| `core/export/color_patch.py` | Patch `filament_colour` dans le 3MF exporte |
| `core/export/color_export_dialog.py` | UI du panneau couleur |
| `core/geometry/paint_scan.py` | Detection des STL peints dans Bambu Studio |
| `core/geometry/stl_loader.py` | Parsing 3MF multi-objets, geometrie par composant |
| `ui/main_window.py` | `_build_color_section()`, integration au dialogue de succes, `AnalysisWorker(is_color_assembly=...)` |
| `ui/components/viewer_3d.py` | `set_slot_colors(mapping)`, placement Z global |
| `core/i18n.py` | Cles `color_export.*` FR + EN |

## Detection des sources de couleur

- **3MF multi-objets** : chaque composant = un slot. `_part_geom_by_id` lit la geometrie DISTINCTE de chaque sous-objet (trimesh renvoyait un mesh fusionne pour les composants a chemin externe : cause des pieces dupliquees superposees). Drapeau `is_color_assembly` sur `ThreeMFData`, decalage Z global `_gzmin`.
- **STL peints dans Bambu Studio** : `paint_scan.scan_paint(threemf_path)` scanne TOUS les fichiers `*.model` du zip (la peinture est souvent dans un sous-modele `3D/Objects/*.model`), groupe par le DERNIER caractere du code `paint_color` (index couleur Bambu), seuil `_MIN_ZONE_FRACTION = 0.02`.
- **Approximation peinte (niveau 2b)** : acceptee par Emmanuel meme si approximative.

## Bugs viewer corriges pendant le chantier

1. **Grille du plateau a travers les objets** : cause = `vtkMapper.SetResolveCoincidentTopologyToPolygonOffset()` : SUPPRIME. Grille a `_gz = -0.5`, surface du plateau a z = -1.0. Ne pas remettre le polygon offset.
2. **Fichier badge « completement buge », pieces superposees** : `_part_geom_by_id` (ci-dessus).
3. **Relief fantome + couleurs en bas au lieu du haut** : retour arriere sur l'approche combined_mesh=base ; decalage Z global conserve + drapeau `is_color_assembly`.
4. **Faux surplombs a 23 pour cent sur piece plate** (aucun slicer n'en detecte) : clamp dans `AnalysisWorker` pour les assemblages couleur plats : remise a zero de `overhang_severity`, `ratio`, `ov.display_mask`, `critical_face_mask`.
5. **Progression d'analyse irrealiste (10 puis 100 pour cent)** : ticker de progression en thread avec petits sauts aleatoires et pauses (demande explicite d'Emmanuel : pas trop fluide).
6. **Spinbox : chiffre superpose aux fleches** : corrige (marges).
7. **Fenetre qui ne s'agrandit pas a l'ajout d'une couleur + pas centree** : corrige.
8. **Valeurs residuelles apres glisser-deposer d'un nouveau fichier** : colonne de droite reinitialisee.
9. **Bug d'affichage a l'ouverture de l'onglet Bobines depuis la fenetre 3MF** : selection d'onglet differee dans `showEvent`.

## Divers export

- Metadonnees Orca : correction du « created by BambuStudio » + migration `ensure_vertical_shell_thickness`.
- Bug connu NON corrige (pre-existant) : `_parse_threemf_multiobject` (stl_loader.py vers L248) leve `UnboundLocalError: root` si un 3MF n'a pas `Metadata/model_settings.config` (Fusion/trimesh) ; le repli charge quand meme, les vrais 3MF Bambu ne sont pas touches.
