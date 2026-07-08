# neoSlice — AI-Powered 3D Print Optimizer

**neoSlice** est un assistant IA de slicing multi-marques. Il analyse vos fichiers 3D, règle automatiquement une impression optimisée et exporte un fichier prêt à ouvrir dans **5 slicers** — Bambu Studio, OrcaSlicer, PrusaSlicer, CrealityPrint et ElegooSlicer — pour **plus de 80 marques et 600 imprimantes** (Bambu Lab, Creality, Prusa, Anycubic, Elegoo, Sovol…).

> Version actuelle : **v0.1.7** — [Télécharger](https://neoslice-ai.com)

---

## Fonctionnalités

- **5 slicers, 80+ marques, 600+ imprimantes** — le catalogue s'adapte au slicer de sortie choisi
- **Import STL & 3MF** — chargez vos fichiers directement, y compris les 3MF multi-plateau
- **Analyse géométrique** — détection des surplombs, fragilité, stabilité par groupe de pièces
- **Intent en langage naturel** — décrivez votre besoin ("solide", "rapide", "finition") et neoSlice règle tout
- **Génération 3MF** — export prêt à ouvrir dans votre slicer avec tous les paramètres optimisés
- **Oen — assistant IA local** *(Pro)* — un modèle Qwen3 tourne sur votre machine (hors ligne, privé), nourri d'une base de connaissances imprimantes ; **mode Réflexion** activable pour des réponses raisonnées
- **Export multicouleur** *(Pro)* — coloriez vos pièces après export 3MF, appliquez les filaments par slot, et le **stock est déduit automatiquement** après impression
- **Espace Pro — gestion d'atelier** *(Pro)* — bobines, devis, factures internationales, clients, commandes et catalogue d'articles, tous connectés
- **Mise à jour automatique** — vérification et installation directement depuis l'application

## Plateformes supportées

| Plateforme | Format | Statut |
|---|---|---|
| Windows 10/11 | `.exe` (installateur) | ✅ Disponible |
| macOS 12+ (arm64 / x86_64) | `.zip` | ✅ Disponible |

## Installation

### Windows
1. Téléchargez `neoSlice_Setup_Windows.exe` sur [neoslice-ai.com](https://neoslice-ai.com)
2. Lancez l'installateur — aucun droit administrateur requis
3. Un raccourci est créé sur le bureau

### macOS
1. Téléchargez `neoSlice_macOS.zip`
2. Décompressez et glissez `neoSlice.app` dans Applications
3. Au premier lancement, faites clic droit → Ouvrir (validation Gatekeeper)

### Mise à jour depuis l'application
Paramètres (⚙) → section **Mise à jour** → **Vérifier maintenant**

---

## Changelog

### v0.1.7
- **Oen — assistant IA local** *(Pro)* : un modèle **Qwen3 8B** tourne directement sur votre machine (hors ligne, privé), avec une base de connaissances imprimantes toutes marques et une recherche sémantique (RAG). **Mode Réflexion** activable dans la fenêtre d'Oen pour des réponses raisonnées. Base de connaissances mise à jour depuis GitHub sans réinstaller l'application.
- **Export multicouleur** *(Pro)* : coloriez vos pièces après export 3MF, appliquez un filament par slot, obtenez le grammage/bobine par couleur — et le **stock est déduit automatiquement** après impression.
- **5 slicers** : sortie compatible Bambu Studio, OrcaSlicer, PrusaSlicer, CrealityPrint et ElegooSlicer. Le catalogue d'imprimantes s'adapte au slicer choisi (80+ marques / 600+ imprimantes).
- **Nouvelles imprimantes** : Flashforge Creator 5 / 5 Pro, Phrozen Arco, et gamme Anycubic Kobra étendue.
- **Version Pro** : le Diagnostic IA et Oen deviennent des fonctionnalités Pro ; l'interface standard reste entièrement gratuite pour optimiser et exporter ses pièces.
- **Tutoriel enrichi** : présentation d'Oen et de l'export multicouleur, adapté selon Pro/standard.
- **Correctif** : barre de titre sombre native fiable sous Windows (plus de retour au thème clair).

### v0.1.6
- **Espace Pro — gestion d'atelier complète** : bobines (stock multi-couleur, coût/kg, alertes de réappro, liste de courses), devis, factures, clients, commandes (file de production) et catalogue d'articles, tous connectés
- **Tableau de bord** : CA facturé / encaissé / dû, factures en retard, graphe des 6 derniers mois (noms de mois réels + légende) et export comptable CSV
- **Facturation internationale** : 13 pays, documents dans la langue du client (FR, EN, DE, NL, IT, ES), mentions légales par pays et frais de recouvrement configurables
- **Décompte automatique du filament** après chaque impression
- **Correctifs d'affichage** : barre de titre sombre native fiable (plus de bande noire ni de barre perdue au retour de réduction), listes sans fantômes, menu de statut au clic

### v0.1.5.7
- **Estimation du poids plus juste** : nouveau modèle physique basé sur la surface réelle de la pièce (coque + remplissage), précis sur petites comme grandes pièces
- **Supports plus propres** : interface de contact ajustée (style « snug », motif rectiligne, espacement serré) → dessous lisse et retrait plus facile
- **Surplombs maîtrisés** : détection des parois en surplomb + ralentissement automatique des porte-à-faux raides (moins d'affaissement) et débit de pont calibré
- **Coutures plus discrètes** en mode précision (gap de couture resserré)

### v0.1.5.6
- **macOS** : correction de l'activation Pro et des mises à jour (« Pas de connexion Internet » alors que la connexion fonctionnait) — certificats SSL embarqués
- Hauteur de couche « rapide » ramenée à 0.24 (buse 0.4) + température PETG à 250°C
- Fiabilité de l'import STL/3MF sur Mac (networkx/lxml embarqués)

### v0.1.5.5
- Correction de l'activation neoSlice Pro : plus de blocage sur connexion lente / antivirus (activation en arrière-plan, sans consommer d'activation en cas d'échec réseau)

### v0.1.5.4
- Aperçu miniature des fichiers à l'import (STL / OBJ / 3MF)
- Rendu 3D mat, plus lisible
- Génération adaptée aux limites réelles de l'imprimante (vitesses, débit, températures)
- Estimation du poids selon le matériau
- Tutoriel bilingue et fignolages d'interface

### v0.1.5.3
- Correctifs de compatibilité : démarrage sur davantage de configurations Windows
- Améliorations de stabilité

### v0.1.5
- **NOUVEAU** Import natif des fichiers 3MF Bambu Studio (multi-plateau, modificateurs, profils)
- **NOUVEAU** Barres de fragilité flottantes par groupe de pièces
- Fix : mapping imprimante H2C/H2S corrigé
- Fix : style de support par défaut corrigé
- Fix : angle de support minimum 30°
- Fix : hauteurs de couche cohérentes avec les préréglages Bambu
- Fix : suppression des avertissements Bambu Studio à l'ouverture du fichier généré

### v0.1.4
- Viewer 3D multi-objets
- Support des fichiers STL volumineux
- Détection surplombs + fragilité

---

## Stack technique

- **UI** : Python 3.12 + PySide6 6.11
- **3D Viewer** : PyVista 0.48 + PyVistaQt 0.11
- **Géométrie** : Trimesh 4.12, NumPy 2.4, SciPy 1.17, Shapely
- **IA locale** : Ollama (Qwen3 8B + embeddings bge-m3), RAG
- **Build** : PyInstaller 6.20

## Build local

```bash
# Windows
python -m PyInstaller --clean -y neoslice.spec

# macOS (depuis un Mac)
python -m PyInstaller --clean -y neoslice_mac.spec
```

---

## Gratuit + Pro

neoSlice est **gratuit** pour optimiser et exporter vos pièces — c'est le cœur de l'application et ça le restera.
Pour aller plus loin, **neoSlice Pro** débloque l'assistant IA Oen, l'export multicouleur avec décompte de stock, le Diagnostic IA et la gestion d'atelier complète.

Envie de soutenir le projet ? [☕ Buy Me a Coffee](https://buymeacoffee.com/bambulabpourlesnuls)

---

© 2026 Emmanuel Percheron
