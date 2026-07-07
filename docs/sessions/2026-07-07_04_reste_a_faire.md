# Reste a faire apres la session du 2026-07-07

## 1. Commit du travail de la session

Tout est NON COMMITE sur `main` (voir `git status` : une vingtaine de fichiers modifies + nouveaux dossiers `core/assistant/`, `data/kb/`, `tools/kb_*`, `ui/components/glass_panel.py`, `strands_widget.py`, etc.). A committer quand Emmanuel le decide.

## 2. Release des assets Oen (quand Emmanuel decide de publier)

Uploader dans la release GitHub `labstral/neoslice-assets`, tag `assistant-latest` :

| Asset | Source locale | Taille |
|---|---|---|
| `meta.json` | `C:\neoSlice\data\kb\index\meta.json` | petit |
| `chunks.jsonl` | `C:\neoSlice\data\kb\index\chunks.jsonl` | 715 Mo |
| `vectors.npy` | `C:\neoSlice\data\kb\index\vectors.npy` | 1517 Mo |
| `embed.gguf` | blob `C:\Users\manup\.neoslice\assistant\models\blobs\sha256-daec91ffb5dd0c27411bd71f29932917c49cf529a641d0168496c3a501e3062c` (bge-m3), a COPIER et RENOMMER en `embed.gguf` | 1158 Mo |
| `ollama-darwin.tgz` | telecharger depuis `https://github.com/ollama/ollama/releases/latest/download/ollama-darwin.tgz` et re-heberger tel quel | 129 Mo |

Deja en place dans la release (ne pas retoucher) : `ollama-windows-amd64.zip`, `model.gguf.00/.01/.02` (chat 7B en 3 parties).

Aucun utilisateur n'a installe Oen (jamais publie) : pas de procedure de migration a prevoir.

## 3. Rebuild de l'app

- UNIQUEMENT quand Emmanuel ecrit « build ». Commande : `python -m PyInstaller --clean -y neoslice.spec` (jamais pyinstaller.exe, jamais 2 builds en parallele).
- IMPORTANT : builder depuis `.venv312` UNIQUEMENT (la regression « viewer 3D absent » de la v0.1.6 venait d'un melange Python 3.12/3.14 ; un garde-fou est dans le spec). Le build v0.1.6.1 correctif est toujours en attente.
- `EMBED_MODEL = bge-m3` est fige dans le build : le rebuild est obligatoire avant publication d'Oen.

## 4. En attente / differe

- **Donnees de demo pour la video** : au prochain « go » d'Emmanuel, remplir tout l'Espace Pro (mix international, pas de backup) + generer les PDF dans Bureau/pdf.
- **Tuto « slicer de sortie »** : code, non commite, dans la file post-0.1.6.
- **Imprimantes a extraire d'OrcaSlicer** : Kobra X, Kobra 3 Max, Kobra Neo, Kobra S1 Max.
- **Adaptateurs KB restants** (crawler generique KO) : BTT, printed.boats ; a re-sonder : geeetech (MediaWiki), phrozen (Zendesk), ultimaker/raise3d, docs.vorondesign, lulzbot, ankermake.
- **Build macOS Codemagic** de la 0.1.6 (attente zip) puis release GitHub avec noms d'assets FIXES + Gist `latest.json` (notes sur UNE ligne).

## 5. Rappels de travail (contraintes permanentes)

- Pas d'emojis, pas de tirets cadratins dans l'app ni les reponses. Francais avec accents corrects.
- i18n TOUJOURS symetrique FR + EN (sauf mentions legales par pays).
- Emmanuel teste via `python main.py` (dev) ou `dist/neoSlice.exe` ; ne JAMAIS builder sans qu'il ecrive « build ».
- Context7 automatique pour toute lib tierce.
- Decision figee : chat = Qwen2.5 7B par defaut (ne pas reproposer 14B/3B), embed = bge-m3.
