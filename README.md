# neoSlice — AI-Powered 3D Print Optimizer

**neoSlice** est un assistant IA de slicing pour les imprimantes **Bambu Lab**. Il analyse vos fichiers 3D et génère automatiquement une configuration d'impression optimisée dans Bambu Studio.

> Version actuelle : **v0.1.5** — [Télécharger](https://neoslice-ai.com)

---

## Fonctionnalités

- **Import STL & 3MF** — chargez vos fichiers directement, y compris les 3MF multi-plateau Bambu Studio
- **Analyse géométrique** — détection des surplombs, fragilité, stabilité par groupe de pièces
- **Intent en langage naturel** — décrivez votre besoin ("solide", "rapide", "finition") et neoSlice règle tout
- **Génération 3MF** — exporte un fichier prêt à ouvrir dans Bambu Studio avec tous les paramètres optimisés
- **Barres de fragilité** — indicateur visuel flottant par lot de pièces dans le viewer 3D
- **Mise à jour automatique** — vérification et installation directement depuis l'application

## Plateformes supportées

| Plateforme | Format | Statut |
|---|---|---|
| Windows 10/11 | `.exe` (installateur) | ✅ Disponible |
| macOS 12+ (arm64 / x86_64) | `.dmg` | ✅ Disponible |

## Installation

### Windows
1. Téléchargez `neoSlice_Setup_v0.1.5-beta_Windows.exe` sur [neoslice-ai.com](https://neoslice-ai.com)
2. Lancez l'installateur — aucun droit administrateur requis
3. Un raccourci est créé sur le bureau

### macOS
1. Téléchargez `neoSlice-v0.1.5-macOS.dmg`
2. Ouvrez le DMG et glissez `neoSlice.app` dans Applications
3. Au premier lancement, faites clic droit → Ouvrir (validation Gatekeeper)

### Mise à jour depuis l'application
Paramètres (⚙) → section **Mise à jour** → **Vérifier maintenant**

---

## Changelog

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
- **Build** : PyInstaller 6.20

## Build local

```bash
# Windows
python -m PyInstaller --clean -y neoslice.spec

# macOS (depuis un Mac)
python -m PyInstaller --clean -y neoslice_mac.spec
```

---

## Soutenir le projet

neoSlice est **entièrement gratuit** et le restera.  
Si vous souhaitez soutenir son développement : [☕ Buy Me a Coffee](https://buymeacoffee.com/bambulabpourlesnuls)

---

© 2026 Emmanuel Percheron
