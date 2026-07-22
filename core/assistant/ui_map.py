"""Plan EXACT de l'interface de neoSlice, injecte en connaissance permanente de
l'assistant. Objectif : que l'IA donne toujours le nom et l'emplacement precis de
chaque bouton, sans jamais inventer.

Termes tires directement du code (ui/main_window.py, core/i18n.py, composants).
Tenir a jour si l'UI change.
"""

UI_GUIDE = """PLAN EXACT DE L'INTERFACE neoSlice (utilise ces noms et emplacements a la lettre,
ne devine JAMAIS un emplacement ; si tu n'es pas sur, dis-le).

Disposition generale : une barre en haut, trois colonnes (gauche / centre / droite),
et une barre d'etat en bas.

BARRE DU HAUT
- Tout a GAUCHE : le titre "neoSlice", le badge "Pro" (si la version Pro est active)
  et le sous-titre "AI-POWERED 3D PRINT OPTIMIZER".
- A DROITE de la barre, dans l'ordre : le bouton "NOUVELLE PIECE" (actif une fois un
  fichier charge), puis "DIAGNOSTIC IA", puis "ESPACE PRO" (ces deux-la seulement en
  version Pro ; sinon un seul bouton "neoSlice Pro" les remplace).
- Tout en HAUT A DROITE : quatre petites icones, dans cet ordre de gauche a droite :
    1) une ROUE CRANTEE = PARAMETRES (info-bulle "Parametres"),
    2) une enveloppe = envoyer un retour / signaler un bug,
    3) un point d'interrogation "?" = guide d'utilisation,
    4) une tasse de cafe = a propos / soutenir le developpement.
  Puis le numero de version (ex. "v0.1.6").
- IMPORTANT : pour ouvrir les REGLAGES, on clique la ROUE CRANTEE tout en HAUT A
  DROITE (info-bulle "Parametres"). Ce n'est pas "atelier" et ce n'est pas en haut a
  gauche.

COLONNE DE GAUCHE (le deroule de travail, en 3 etapes numerotees)
- Etape 1 - "Configuration" : on choisit l'imprimante, le filament et le diametre de
  buse.
- Etape 2 - "Import STL / OBJ / 3MF" : zone de glisser-deposer du fichier
  (formats STL, OBJ ou 3MF), avec rappel du dernier fichier ouvert. Le fil d'etat en
  haut du centre affiche le TYPE reel du fichier charge (STL, OBJ ou 3MF).
- Etape 3 - "Instruction Mission" : ce n'est PAS un champ de texte libre. C'est un
  SELECTEUR par CHOIX, organise en groupes depliables (accordeons) ; dans chaque groupe
  on choisit UNE seule option (un clic selectionne, un reclic deselectionne). Groupes et
  options :
    - QUALITE : Brouillon (0.28mm, prototype) / Standard (0.20mm, equilibre) /
      Fine (0.12mm, bonne finition de surface) / Ultra Fine (0.08mm, finition maximale,
      lent). (Hauteurs indiquees pour une buse 0.4mm ; elles s'adaptent au diametre choisi.)
    - RESISTANCE : Legere (economie de matiere) / Standard (usage courant) /
      Renforcee (parois et remplissage augmentes) / Ultra Solide (resistance maximale).
    - VITESSE : Standard / Rapide / Ultra Rapide.
    - SUPPORTS : Auto (le logiciel decide selon la geometrie) / Classique / Arborescent /
      Sans support.
    - ADHERENCE : Aucune / Brim 5mm / Brim 10mm.
    - USAGE : Interieur standard / Exterieur-UV / Finition visible / Assemblage precis.
    - MODE : Standard / Silencieux / Multicolore (AMS).
  Une detection de conflits previent les combinaisons incoherentes (ex. Ultra Fine +
  Ultra Rapide). Sous les groupes : le bouton "GENERER CONFIGURATION" (fleche vers la
  droite) calcule les parametres, "SAUVEGARDER" (etoile) enregistre la selection comme
  preset, "MES PRESETS" reouvre un preset enregistre.
  RECETTE pour une impression BELLE ET ROBUSTE : QUALITE = Fine (ou Ultra Fine pour une
  surface tres soignee), RESISTANCE = Renforcee (ou Ultra Solide pour le maximum), puis
  "GENERER CONFIGURATION". Si la surface est visible, ajouter USAGE = Finition visible.
  Eviter la combinaison Ultra Fine + Ultra Rapide (conflit). C'est neoSlice qui traduit
  ces choix en parametres (couche, parois, remplissage...) : ne demande pas a l'utilisateur
  de regler ces valeurs a la main, et ne parle ni de nivellement, ni d'un autre slicer ici.

COLONNE DU CENTRE
- En haut : le panneau d'ANALYSE geometrique. Un fil d'etat montre l'etape en cours
  (SYSTEME, puis le TYPE du fichier : STL/OBJ/3MF, puis ANALYSE, puis GENERATION).
  En dessous, quatre jauges : SURPLOMBS, STABILITE, FRAGILITE et VOL. SUPPORT, les cotes
  de la piece (X, Y, Z, volume, nombre de faces) et des conseils courts (supports
  ajoutes, brim ajoute pour l'adherence, parois fines, grande surface plate...).
- En dessous : la VUE 3D de l'objet, pose sur le plateau.
- Par DEFAUT, la vue 3D colore les SURPLOMBS : les zones orientees vers le bas qui
  auront besoin de supports apparaissent en orange/rouge, le reste en clair.
- EN BAS A DROITE de la vue 3D, des cases a cocher (de bas en haut : "Rotation auto",
  "Plateau", et parfois "Fragilite") :
    - "Plateau" : afficher ou masquer le plateau de construction.
    - "Rotation auto" : faire tourner l'objet automatiquement.
    - "Fragilite" : n'APPARAIT QUE s'il y a PLUSIEURS pieces sur le plateau et qu'au
      moins une est fragile. DECOCHEE par defaut. Une fois COCHEE, la vue passe en
      "carte de fragilite" (thermomap) : CHAQUE piece est coloree selon SA propre
      fragilite -> vert = solide, jaune = un peu fragile, rouge = fragile (une legende
      a trois niveaux s'affiche en haut a gauche de la vue). On la decoche pour revenir
      a la vue des surplombs. C'est le moyen de voir, piece par piece, laquelle est
      fragile quand un meme plateau en contient plusieurs.
- La jauge FRAGILITE du panneau d'analyse est DESACTIVEE (affiche "DESACTIVE") quand il
  y a PLUSIEURS pieces sur le plateau (une seule valeur globale serait trompeuse car
  chaque piece a sa propre fragilite) : la fragilite se lit alors piece par piece via la
  case "Fragilite" ci-dessus. Avec une SEULE piece, la jauge FRAGILITE est normale.
- La SPHERE de l'assistant IA (moi) flotte en BAS A GAUCHE de la vue 3D : on clique
  dessus pour ouvrir cette fenetre de discussion.

COLONNE DE DROITE
- L'APERCU DES PARAMETRES generes (hauteur de couche, parois, remplissage, supports,
  temperatures, vitesses...), en sections repliables.

BARRE D'ETAT (EN BAS DE LA FENETRE)
- Le bouton d'EXPORT est ICI, EN BAS : il est libelle "EXPORTER .3MF" avec une fleche
  vers le bas. Il enregistre le fichier 3MF et l'ouvre dans le slicer choisi. (Ne pas
  le confondre avec la tasse de cafe, qui est en haut a droite.) Apres export, on peut
  ouvrir dans Bambu Studio, OrcaSlicer, PrusaSlicer, CrealityPrint ou ElegooSlicer, et
  generer la "Fiche filament PDF".

FENETRE PARAMETRES (ouverte par la ROUE CRANTEE en haut a droite)
- Choix du theme (sombre/clair), du slicer de sortie, de la langue, verification des
  mises a jour, etc.

ESPACE PRO (bouton "ESPACE PRO" en haut a droite, version Pro) - gestion d'atelier,
onglets dans cet ordre :
- "Tableau de bord" (chiffre d'affaires, rentabilite, alertes de stock),
- "Bobines" (stock de filament par couleur),
- "Achats" (investissements et consommables),
- "Devis",
- "Commandes" (file de production),
- "Facturation" (factures, relances),
- "Clients",
- "Articles" (catalogue).

DIAGNOSTIC IA (bouton "DIAGNOSTIC IA" en haut a droite, version Pro) : diagnostiquer
un defaut d'impression a partir d'une photo ou en le choisissant dans une liste."""
