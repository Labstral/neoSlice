# Ré-entraînement automatique du modèle de défauts (Kaggle)

Configuration **une seule fois**. Ensuite, chaque semaine, le modèle se ré-entraîne
tout seul sur les nouvelles photos contribuées, et l'app récupère la nouvelle version
automatiquement. **Aucune intervention.**

## Vue d'ensemble

```
Kaggle Notebook planifié (hebdo, GPU gratuit)
  → télécharge les photos de Supabase
  → ré-entraîne
  → garde-fou : publie SEULEMENT si aussi bon ou meilleur
  → met à jour model_manifest.json sur GitHub Releases
        ↓
App neoSlice → détecte la nouvelle version → télécharge le modèle automatiquement
```

---

## Étapes (≈ 15 min, une fois)

### 1. Récupérer la clé Supabase service_role
- Dashboard Supabase → **Settings → API**
- Section **Project API keys** → copie la clé **`service_role`** (⚠️ secrète, ne jamais la mettre dans l'app — uniquement dans Kaggle)

### 2. Créer un token GitHub
- github.com → **Settings → Developer settings → Personal access tokens → Tokens (classic)**
- **Generate new token (classic)** → coche le scope **`repo`** → génère → copie le token (`ghp_...`)

### 3. Le dataset de base
Déjà uploadé automatiquement sur Kaggle sous **`emmanuelpercheron/neoslice-defect-base`**.
(Si besoin de le recréer : `kaggle datasets create -p <dossier> --dir-mode zip`)

### 4. Créer le notebook Kaggle
1. kaggle.com → **Create → New Notebook**
2. **Settings (panneau droit)** :
   - **Accelerator** : `GPU T4 x2` (ou P100)
   - **Add Input** → cherche et ajoute ton dataset **`neoslice-defect-base`**
3. **Add-ons → Secrets** → ajoute 3 secrets (bouton *Add a new secret*) :
   | Label | Valeur |
   |-------|--------|
   | `SUPABASE_URL` | `https://obmypmocuwnhuxbsaxhx.supabase.co` |
   | `SUPABASE_SERVICE_KEY` | la clé service_role (étape 1) |
   | `GITHUB_TOKEN` | le token GitHub (étape 2) |
4. Dans une cellule, colle :
   ```python
   !pip -q install timm onnx onnxruntime albumentations
   import urllib.request
   url = "https://raw.githubusercontent.com/Labstral/neoSlice/main/scripts/kaggle_retrain.py"
   exec(urllib.request.urlopen(url).read().decode())
   ```
   (récupère toujours la dernière version du script depuis GitHub)
5. **Run All** une fois pour vérifier que ça marche (tu verras le téléchargement,
   l'entraînement, puis `[PUBLIE] vN` ou `[REJET]`).

### 5. Planifier l'exécution hebdomadaire
- En haut du notebook → menu **⋮ → Schedule a notebook run** (ou *Schedule*)
- Choisis **Weekly**, un jour/heure (ex: dimanche 03:00)
- Active. C'est tout.

---

## Sécurité / garde-fou
- Le nouveau modèle n'est **publié que si `val_acc >= modèle actuel`**. Sinon il est
  rejeté et rien ne change pour les utilisateurs.
- La clé `service_role` et le token GitHub restent **uniquement dans les secrets Kaggle**,
  jamais dans l'app distribuée (l'app n'utilise que la clé `anon` en écriture seule).

## Réglages (variables d'env optionnelles dans le notebook)
- `NEOSLICE_EPOCHS` (défaut 15) — nombre d'epochs
- `NEOSLICE_MIN_NEW` (défaut 1) — minimum de photos pour déclencher

## Vérifier que ça tourne
- Onglet **Output** du notebook : logs de chaque run planifié
- GitHub → Releases → tag `models` : `model_manifest.json` doit afficher la
  dernière `version` / `val_acc`
