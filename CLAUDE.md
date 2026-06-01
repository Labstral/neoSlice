# neoSlice — Assistant IA de slicing pour Bambu Studio

## Stack technique
- **UI** : Python 3.12 + PySide6 6.11 (Qt6)
- **3D Viewer** : PyVista 0.48 + PyVistaQt 0.11
- **Géométrie** : Trimesh 4.12, NumPy 2.4, SciPy 1.17, Shapely
- **Data models** : Pydantic 2.13
- **Build** : PyInstaller 6.20

## Commandes essentielles
```bash
# Build (TOUJOURS python -m PyInstaller, jamais pyinstaller.exe)
python -m PyInstaller --clean -y neoslice.spec

# Test rapide avant build
python -c "from ui.main_window import MainWindow; print('OK')"

# Lancer en dev
python main.py
```

## Architecture — fichiers clés
| Fichier | Rôle |
|---------|------|
| `main.py` | Point d'entrée, splash, init thème |
| `ui/main_window.py` | Fenêtre principale + worker threads |
| `ui/components/viewer_3d.py` | Viewer PyVista 3D |
| `ui/styles/theme.py` | Gestionnaire thèmes dark/light |
| `core/export/tmf_builder.py` | Constructeur 3MF |
| `core/export/bambu_config_resolver.py` | Résout profils Bambu Studio |
| `core/geometry/` | Analyse STL (surplombs, fragilité, stabilité) |
| `core/parameters/parameter_engine.py` | Intent → paramètres impression |
| `core/intent/intent_parser.py` | NLP — texte libre → IntentProfile |
| `data/filaments.py` | Catalogue filaments |
| `data/printers.py` | Catalogue imprimantes |
| `version.py` | Version actuelle |

## Règles critiques 3MF (ne jamais ignorer)
1. **print_settings_id** doit être INCONNU de Bambu Studio → ex: `"neoSlice 0.20mm @BBL X1C"`
   (sinon BS recharge le preset et écrase enable_support)
2. **Ne jamais supprimer toutes les clés filament** → utiliser slot Generic PLA neutre
3. **curr_bed_type seul ne suffit pas** → mettre à jour aussi la clé température plateau (eng_plate_temp, etc.)

## Workflow recommandé — EPCT
Pour toute modification non triviale :
1. **E**xplore — lire les fichiers concernés, comprendre le contexte
2. **P**lan — proposer un plan détaillé, attendre validation
3. **C**ode — implémenter le plan validé
4. **T**est — tester via PowerShell, puis build PyInstaller si tout est bon

## Context management
- Utiliser `/compact` dès que le contexte dépasse ~50% pour garder des réponses précises
- Utiliser des subagents pour les recherches larges (évite de polluer le contexte principal)

## Build & test
- **Emmanuel teste toujours via** `dist/neoSlice.exe` (raccourci bureau), jamais `python main.py`
- **Toujours rebuilder** après modification de code avant de déclarer terminé
- Build output : `C:\neoSlice\dist\neoSlice.exe`

## Dépendances externes
- Bambu Studio installé → profils dans `%APPDATA%/BambuStudio/system/BBL/`
- Context7 MCP configuré → utiliser automatiquement pour toute lib tierce
