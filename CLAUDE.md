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
- **Emmanuel teste TOUJOURS via `python main.py` (PowerShell), JAMAIS via l'exe** —
  un fix est testable dès le prochain lancement, AUCUN rebuild nécessaire
  (mais l'app doit être RELANCÉE si elle tournait pendant la modification)
- **Ne builder QUE quand Emmanuel écrit « build »** (préparation d'une distribution)
- Build output : `C:\neoSlice\dist\neoSlice.exe`

## Dépendances externes
- Bambu Studio installé → profils dans `%APPDATA%/BambuStudio/system/BBL/`
- Context7 MCP configuré → utiliser automatiquement pour toute lib tierce

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

### Auto-update sémantique (docs/images) — IMPORTANT, à faire sans qu'on te le demande

- **Au début de chaque session ET avant de répondre à une question sur le projet** : vérifier si `graphify-out/.needs_semantic_update` existe. S'il existe, lancer une extraction sémantique complète des fichiers qui y sont listés (réutiliser le pipeline `/graphify` Partie B : sous-agents `general-purpose` → merge chunks → merge AST+sémantique → rebuild graph/report), puis **supprimer** `graphify-out/.needs_semantic_update`. Ce marqueur est déposé par le hook git post-commit quand des docs/images changent (l'AST seul ne les couvre pas).
- **Après avoir moi-même modifié/créé un doc, une image, un .md, un .yaml ou les notes d'idées** dans une session : lancer directement l'extraction sémantique de ces fichiers (je suis le LLM, pas besoin de clé API) et reconstruire le graphe — ne pas attendre le prochain commit.
- Conséquence : l'utilisateur ne tape JAMAIS `/graphify --update` à la main. Le code passe par le hook git (AST instantané) ; les docs/images passent par le marqueur que je traite automatiquement.
