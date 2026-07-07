# Oen, l'assistant IA local de neoSlice : etat complet (2026-07-07)

## Identite et acces

- Nom : **Oen** (« neo » a l'envers). Titre du panneau : « Oen · Assistant neoSlice ». Accueil : « Bonjour, je suis Oen, l'assistant de neoSlice. »
- Fonction Pro uniquement (`est_pro()`), installation optionnelle depuis les reglages (section « OEN · ASSISTANT IA », boutons Installer / Desinstaller, barre de progression, worker `_InstallWorker`).
- Fenetre « Licences et mentions » accessible par un lien en bas des reglages : Ollama (MIT), Qwen2.5 et bge-m3 (Apache 2.0), attributions des wikis constructeurs.

## Architecture technique

| Composant | Valeur |
|---|---|
| Runtime | Ollama embarque dans `~/.neoslice/assistant/ollama/`, serveur HTTP 127.0.0.1:11434 |
| Modele chat | **Qwen2.5 7B** (alias `neoslice-assistant`, cree depuis model.gguf en 3 parties) |
| Modele embedding | **bge-m3** (multilingue, 1024 dim, AUCUN prefixe de tache) |
| Index RAG | 740 773 passages, vectors.npy float16 1517 Mo, chunks.jsonl 715 Mo |
| Fichiers cle | `core/assistant/engine.py`, `rag.py`, `context.py`, `installer.py`, `ui/components/glass_panel.py`, `strands_widget.py`, `tools/kb_index.py` |

- `engine.stream(history)` assemble : `_SYSTEM_PROMPT` + guide UI + `context.build_context_block()` (instantane reel : Espace Pro, parametres de generation, analyse viewer) + `rag.context_block(derniere question)` + historique + `_GUARD` en DERNIER. Temperature 0.25, num_ctx 8192.
- `kb_index_dir()` : renvoie l'index installe `~/.neoslice/assistant/kb/index` s'il est complet, sinon repli sur `data/kb/index` (mode dev).
- Installateur cross-plateforme : `OLLAMA_RUNTIME = {win32: ollama-windows-amd64.zip, darwin: ollama-darwin.tgz}`, extraction tar.gz avec `filter='data'` (preserve +x et symlinks), `_finalize_ollama_binary()`. Tous les assets tires d'UNE release GitHub `labstral/neoslice-assets` tag `assistant-latest`.

## DECISION MODELE (2026-07-07, ne pas rouvrir)

**On reste sur Qwen2.5 7B par defaut.** Le 14B (meilleur raisonnement) et le 3B (plus leger) ont ete proposes et REFUSES par Emmanuel : « ce n'est pas que pour moi, tout le monde n'a pas une carte graphique, il faut un truc qui s'adapte a tout type d'ordinateur ». Le 7B est le compromis retenu (tourne aussi en CPU). Tout gain futur passe par le prompt, le guard et le RAG, pas par la taille du modele.

## Migration RAG nomic vers bge-m3 (TERMINEE)

- Probleme d'origine : `nomic-embed-text` exige les prefixes `search_document:` / `search_query:`, l'index avait ete construit SANS : recherche fortement degradee, Oen repondait a cote (retour Emmanuel : « il repond n'importe quoi, il ne se base pas sur les wikis »).
- Solution : bge-m3 (multilingue FR/EN, 1024 dim, aucun prefixe). `_load_existing(model)` remet l'index a zero si le modele change (evite le melange de dimensions). `meta.json` porte `model`, `dim`, `dtype: float16`, `nomic_prefixed: false`.
- Stockage **float16** obligatoire : en float32, 1024 dim x 740k = environ 3 Go, au dessus de la limite de 2 Go par asset GitHub. `rag.py` fait le produit scalaire PAR BLOCS de 100 000 lignes avec recast float32.
- Perf du re-index (RTX 3060) : BATCH=128 (256 provoquait des HTTP 400 intermittents), `_embed_chunk` resilient (decoupe recursive + troncature a 1800 caracteres au lieu du repli sequentiel 20x plus lent), PIPELINE producteur/consommateur dans `kb_index.py` (un thread lit et decoupe les .md pendant que le GPU embarque) : GPU passe de 61 a 98 pour cent, debit de 26 a plus de 40 passages/s.
- Qualite VALIDEE : « calibrer plateau X1C » remonte les vraies pages « Nivellement manuel du plateau » Bambu (0.67-0.74) ; « PETG stringing » remonte la page stringing de la KB Prusa.

## Entrainement (3 rounds) : lecons et corrections

**Lecon transverse : sur le 7B, une regle critique ne « prend » que dans `_GUARD` (dernier message = le plus obei). Le long `_SYSTEM_PROMPT` et la section REPERES ne suffisent pas pour les faits sensibles.**

Corrections appliquees (toutes re-testees OK) :
1. Enceinte : PLA/PETG = porte et capot OUVERTS ; ABS/ASA/PC/nylon = fermes. A1/A1 mini/Ender 3/Prusa MINI et MK = open-frame, PAS de porte a ouvrir.
2. Anti-melange de marques : X1C/X1/P1/A1 = Bambu Lab, jamais Prusa.
3. Anti-hallucination : ne jamais inventer de menu, case a cocher, source, guide, URL ou caracteristique machine ; ne citer une source que si elle est dans les CONNAISSANCES fournies.
4. **neoSlice N'IMPRIME PAS, NE CALIBRE PAS, NE NIVELLE PAS, NE PILOTE PAS la machine** : ne jamais proposer « utiliser neoSlice » pour ces actions.
5. **Surplombs : jusqu'a environ 45 degres = SANS support** sur la quasi-totalite des machines ; si une source cite 75 degres tolere, cela CONFIRME que 45 passe (le 7B inversait la logique en s'ancrant sur les pages Prusa).
6. **Reduire le temps d'impression** = AUGMENTER hauteur de couche et vitesse, reduire remplissage et parois, buse plus large. Le 7B conseillait l'inverse (baisser la vitesse).
7. Anti-recitation : en-tete du `_GUARD` = « ces regles GUIDENT ta reponse, tu ne les RECITES jamais, ne mentionne un point que s'il repond a la question » (le 7B recitait la regle enceinte sur une question de remplissage). Attenue, il reste parfois un bloc « Rappels » verbeux mais juste.
8. Filler (« n'hesitez pas », « je peux vous aider ») : interdiction non fiable au niveau prompt, donc suppression GARANTIE en post-traitement `glass_panel._strip_filler` (comme le markdown via `_plain_text`).
9. Options cliquables : le modele emet `[[OPTIONS: a | b | c]]`, `_split_options` extrait et affiche des puces cliquables ; le marqueur est masque pendant le streaming.
10. Largeur de bulle corrigee via `QFontMetrics.boundingRect` + `setFixedWidth`.

Limites 7B connues et acceptees : rate parfois un fait enfoui (sechage nylon-CF, buse acier trempe), exemples chiffres parfois embrouilles, petit derapage occasionnel. C'est le plafond du modele, pas un bug.

## Script d'entrainement reutilisable

`scratchpad/train.py` (dossier scratchpad de session, a recreer au besoin) : appelle `AssistantEngine.instance().stream()` avec le pipeline REEL (prompt + UI + contexte + RAG + guard) puis applique le post-traitement de l'app (`_split_options`, `_plain_text`, `_strip_filler`). Usage : `python train.py '["question 1", "question 2"]' sortie.txt`.
