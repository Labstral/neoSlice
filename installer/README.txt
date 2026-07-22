==============================================================================
  neoSlice - AI-Powered 3D Print Optimizer
  Guide d'installation et de démarrage - v0.1.8
==============================================================================
  © 2026 Emmanuel Percheron - Tous droits réservés


------------------------------------------------------------------------------
SOMMAIRE
------------------------------------------------------------------------------
  1. Configuration requise
  2. Contenu du package
  3. Installation pas à pas
  4. Problèmes fréquents à l'installation
  5. Premier démarrage
  6. Désinstallation
  7. Questions fréquentes (FAQ)
  8. Nouveautés v0.1.8
  9. Contact et support


------------------------------------------------------------------------------
1. CONFIGURATION REQUISE
------------------------------------------------------------------------------

  Système d'exploitation  : Windows 10 (64 bits) ou Windows 11
  Processeur              : Intel Core i5 / AMD Ryzen 5 ou supérieur
  Mémoire RAM             : 8 Go minimum (16 Go recommandés)
  Espace disque           : 1 Go minimum disponible
  Carte graphique         : Compatible OpenGL 3.3 (intégrée ou dédiée)
  Résolution écran        : 1280x720 minimum (1920x1080 recommandée)
  Connexion internet      : Non requise (logiciel 100% local)

  ATTENTION : neoSlice n'est pas compatible avec Windows 32 bits.
  ATTENTION : Les machines virtuelles peuvent présenter des problèmes
              d'affichage 3D.


------------------------------------------------------------------------------
2. CONTENU DU PACKAGE
------------------------------------------------------------------------------

  neoSlice_Setup_v0.1.8_Windows.exe  ->  Installateur Windows
  README.txt                       ->  Ce guide
  LICENSE.txt                      ->  Accord de licence utilisateur final


------------------------------------------------------------------------------
3. INSTALLATION PAS À PAS
------------------------------------------------------------------------------

  ÉTAPE 1 - Préparer l'installation
  -----------------------------------
  Avant de lancer l'installateur, il est fortement recommandé de :

    * Fermer tous les programmes ouverts.
    * Désactiver temporairement votre antivirus si nécessaire (voir section 4).

  ÉTAPE 2 - Lancer l'installateur
  ---------------------------------
  Double-cliquez sur : neoSlice_Setup_v0.1.8_Windows.exe

  Si Windows affiche "Windows a protégé votre PC" :
    -> Cliquez sur "Informations complémentaires"
    -> Cliquez sur "Exécuter quand même"
  (Ce message apparaît car le logiciel n'a pas encore de signature
   numérique commerciale. Voir section 4 pour plus de détails.)

  ÉTAPE 3 - Suivre l'assistant d'installation
  ---------------------------------------------
    a) Écran d'accueil        -> Cliquez sur "Suivant"
    b) Accord de licence      -> Lisez et acceptez, puis "Suivant"
    c) Dossier d'installation -> Le dossier par défaut est recommandé :
                                 C:\Users\[vous]\AppData\Local\neoSlice\
    d) Raccourcis             -> Laissez "Créer un raccourci sur le Bureau"
                                 coché si vous souhaitez un accès rapide.
    e) Prêt à installer       -> Cliquez sur "Installer"
    f) Installation           -> Patientez (peut prendre 1 à 2 minutes).
    g) Fin d'installation     -> Laissez "Lancer neoSlice" coché pour
                                 démarrer le logiciel immédiatement.
                                 Cliquez sur "Terminer".

  ÉTAPE 4 - Réactiver votre antivirus
  -------------------------------------
  Une fois l'installation terminée, réactivez votre antivirus si vous
  l'aviez désactivé.


------------------------------------------------------------------------------
4. PROBLÈMES FRÉQUENTS À L'INSTALLATION
------------------------------------------------------------------------------

  MON ANTIVIRUS BLOQUE L'INSTALLATION OU SUPPRIME LE FICHIER
  ------------------------------------------------------------
  Pourquoi cela se produit-il ?
  neoSlice est distribué sans signature numérique commerciale (EV Code
  Signing), dont le coût est prohibitif pour un développeur indépendant.
  Les antivirus modernes signalent parfois les logiciels "inconnus" même
  s'ils sont parfaitement sûrs. C'est ce qu'on appelle un "faux positif".

  neoSlice ne contient aucun virus, malware, spyware ou code malveillant.
  Il fonctionne entièrement en local et n'établit aucune connexion réseau.

  Comment résoudre le problème ?

  -> Windows Defender (intégré à Windows) :
     1. Ouvrez Sécurité Windows (icône bouclier dans la barre des tâches)
     2. Allez dans "Protection contre les virus et menaces"
     3. Cliquez sur "Gérer les paramètres"
     4. Désactivez temporairement "Protection en temps réel"
     5. Installez neoSlice
     6. Réactivez la protection immédiatement après

  -> Autres antivirus (Avast, AVG, Bitdefender, Norton, Kaspersky...) :
     1. Faites un clic droit sur l'icône de votre antivirus dans la barre
        des tâches
     2. Cherchez une option "Désactiver", "Pause" ou "Mode jeu"
     3. Sélectionnez une désactivation temporaire (10 ou 15 minutes)
     4. Installez neoSlice
     5. Réactivez votre antivirus

  -> Si l'antivirus a déjà supprimé le fichier :
     Cherchez dans la "Quarantaine" ou "Menaces détectées" de votre
     antivirus et restaurez le fichier, puis ajoutez-le aux exceptions.


  WINDOWS AFFICHE "WINDOWS A PROTÉGÉ VOTRE PC"
  ----------------------------------------------
  Ce message de Windows SmartScreen apparaît pour tout exécutable
  téléchargé non signé numériquement.

     1. Cliquez sur "Informations complémentaires" (lien bleu)
     2. Cliquez sur "Exécuter quand même"


  L'INSTALLATION S'ARRÊTE OU GÈLE
  ---------------------------------
  -> Vérifiez que vous avez au moins 1 Go d'espace disque disponible
  -> Désactivez votre antivirus et relancez l'installation
  -> Redémarrez Windows et réessayez


------------------------------------------------------------------------------
5. PREMIER DÉMARRAGE
------------------------------------------------------------------------------

  Au premier lancement, neoSlice effectue quelques initialisations.
  Le démarrage peut prendre 10 à 20 secondes - c'est normal.

  FENÊTRE DE BIENVENUE
  ---------------------
  À la première ouverture, une fenêtre de bienvenue s'affiche.
    * Lisez les informations présentées.
    * Cochez "Ne plus afficher ce message" si vous ne souhaitez plus
      la revoir au prochain démarrage.
    * Cliquez sur "Commencer" pour accéder au logiciel.

  TUTORIEL INTERACTIF
  --------------------
  Un tutoriel pas à pas se lance automatiquement à la première utilisation.
  Il vous guide à travers les 4 étapes du workflow neoSlice :

    1. Configuration  - Choix du slicer de sortie, de l'imprimante et du filament
    2. Import STL     - Glisser-déposer votre fichier 3D
    3. Mission        - Réglage des critères d'impression
    4. Export         - Génération du fichier .3MF pour votre slicer

  Vous pouvez relancer ce tutoriel à tout moment via le bouton "?"
  situé en haut à droite de la fenêtre principale.

  PROBLÈMES D'AFFICHAGE 3D AU PREMIER DÉMARRAGE
  -----------------------------------------------
  Si le visualiseur 3D affiche une erreur ou reste vide :
    -> Mettez à jour les pilotes de votre carte graphique
    -> Vérifiez que OpenGL 3.3 est supporté par votre machine
    -> Relancez le logiciel (un second démarrage résout souvent le problème)


------------------------------------------------------------------------------
6. DÉSINSTALLATION
------------------------------------------------------------------------------

  Méthode 1 - Via Windows (recommandée) :
    1. Ouvrez Paramètres Windows (touche Windows + I)
    2. Allez dans "Applications" -> "Applications installées"
    3. Recherchez "neoSlice" dans la liste
    4. Cliquez sur les trois points "..." -> "Désinstaller"
    5. Suivez les instructions du désinstalleur

  Méthode 2 - Via le menu Démarrer :
    1. Ouvrez le menu Démarrer
    2. Cherchez le dossier "neoSlice"
    3. Cliquez sur "Désinstaller neoSlice"

  Note : La désinstallation supprime le logiciel mais conserve vos
  préférences locales (dossier C:\Users\[vous]\.neoslice\).
  Supprimez ce dossier manuellement si vous souhaitez une désinstallation
  complète.


------------------------------------------------------------------------------
7. QUESTIONS FRÉQUENTES (FAQ)
------------------------------------------------------------------------------

  Q : neoSlice est-il compatible avec macOS ou Linux ?
  R : Windows 10/11 (64 bits) et macOS sont supportés. Linux n'est
      pas encore supporté officiellement.

  Q : neoSlice est-il gratuit ?
  R : neoSlice est gratuit pour optimiser et exporter vos pièces - c'est le
      cœur de l'application et cela le restera. Une version Pro (optionnelle)
      débloque l'assistant IA Oen, l'export multicouleur avec décompte de stock,
      le Diagnostic IA et la gestion d'atelier complète.

  Q : Le logiciel envoie-t-il mes données quelque part ?
  R : Non. neoSlice fonctionne 100% en local. Aucune donnée n'est
      transmise. Vos fichiers STL et configurations restent sur votre
      machine.

  Q : Quelles imprimantes et quels slicers neoSlice supporte-t-il ?
  R : neoSlice couvre plus de 80 marques et 600 imprimantes (Bambu Lab,
      Creality, Prusa, Anycubic, Elegoo, Sovol...). La sortie est compatible
      avec 5 slicers : Bambu Studio, OrcaSlicer, PrusaSlicer, CrealityPrint et
      ElegooSlicer. Le catalogue d'imprimantes s'adapte au slicer choisi.

  Q : Puis-je utiliser neoSlice sans connexion internet ?
  R : Oui. neoSlice ne nécessite aucune connexion internet pour fonctionner.
      Une connexion est uniquement utilisée pour vérifier les mises à jour.

  Q : Le logiciel plante ou se ferme inopinément - que faire ?
  R : Consultez le fichier journal dans :
      C:\Users\[votre nom]\.neoslice\
      et transmettez-le au support avec une description du problème.

  Q : La mise à jour vers une nouvelle version nécessite-t-elle de
      désinstaller l'ancienne ?
  R : Non. Lancez simplement le nouvel installateur - il remplacera
      automatiquement la version précédente.

  Q : J'ai une imprimante Bambu Lab A2L, dois-je une version spéciale ?
  R : Non. neoSlice supporte nativement l'A2L depuis la v0.1.3.
      Sélectionnez simplement "A2L" dans la liste des imprimantes.
      Bambu Studio 2.7.1 ou supérieur est requis pour l'A2L.


------------------------------------------------------------------------------
8. NOUVEAUTÉS v0.1.8
------------------------------------------------------------------------------

  NEOGEN - GÉNÉRATEUR D'OBJETS 3D (Pro)
  --------------------------------------
  * Bibliothèque d'objets prêts à imprimer, tous personnalisables au
    millimètre : porte-clés, cadres photo, QR codes 3D en deux couleurs,
    cartes de visite, clips de câble au diamètre exact, joints, équerres,
    vis et écrous, objets pour la restauration, le mariage et la boutique.
  * Texte en relief ou gravé, choix de la police et des couleurs.
  * Chaque pièce est générée étanche et pensée pour sortir sans support.

  CARTE DE FRAGILITÉ PAR PIÈCE
  -----------------------------
  * Sur un plateau multi-pièces, cochez "Fragilité" dans la vue 3D :
    chaque pièce se colore selon sa solidité (vert = solide, jaune = un peu
    fragile, rouge = fragile).

  FLASHPRINT - 9e SLICER COMPATIBLE
  ----------------------------------
  * Sortie vers FlashPrint (FlashForge) avec dépôt automatique du profil
    d'impression.
  * Les plateaux proposés s'adaptent désormais à chaque imprimante.

  MODE PERFORMANCE AUTOMATIQUE
  -----------------------------
  * neoSlice choisit seul, pièce par pièce, le meilleur compromis entre
    vitesse d'analyse et précision selon votre machine.
  * Les fichiers 3MF complexes qui pouvaient bloquer le chargement
    s'ouvrent maintenant en quelques secondes.


------------------------------------------------------------------------------
RAPPEL - NOUVEAUTÉS v0.1.7
------------------------------------------------------------------------------

  OEN - ASSISTANT IA LOCAL (Pro)
  ----------------------------------
  * Un modèle Qwen3 tourne directement sur votre machine (hors ligne, privé),
    nourri d'une base de connaissances imprimantes toutes marques.
  * Activez le mode "Réflexion" pour des réponses raisonnées.
  * La base de connaissances se met à jour depuis GitHub sans réinstaller
    l'application.

  EXPORT MULTICOULEUR (Pro)
  -----------------------------
  * Coloriez vos pièces après l'export 3MF et appliquez un filament par slot.
  * Obtenez le grammage par couleur/bobine et le stock est déduit
    automatiquement après impression.

  5 SLICERS, 80+ MARQUES, 600+ IMPRIMANTES
  ---------------------------------------------
  * Sortie compatible Bambu Studio, OrcaSlicer, PrusaSlicer, CrealityPrint et
    ElegooSlicer - le catalogue d'imprimantes s'adapte au slicer choisi.
  * Nouvelles machines : Flashforge Creator 5 / 5 Pro, Phrozen Arco et gamme
    Anycubic Kobra étendue.

  VERSION PRO
  ---------------
  * Le Diagnostic IA et Oen deviennent des fonctionnalités Pro ; l'interface
    standard reste entièrement gratuite pour optimiser et exporter ses pièces.

  CORRECTIFS
  --------------
  * Barre de titre sombre native fiable sous Windows (plus de retour au
    thème clair).
  * Tutoriel enrichi (Oen + export multicouleur), adapté selon Pro/standard.


------------------------------------------------------------------------------
9. CONTACT ET SUPPORT
------------------------------------------------------------------------------

  Développeur  : Emmanuel Percheron
  Site web     : https://neoslice-ai.com
  Retours/bugs : https://neoslice-ai.com/retour

  Merci d'inclure dans votre message :
    * La version de Windows utilisée
    * La description précise du problème rencontré
    * Une capture d'écran si possible
    * Le fichier de log situé dans C:\Users\[vous]\.neoslice\

  --------------------------------------------------------------------------
  Merci d'utiliser neoSlice. Vos retours sont précieux pour améliorer
  le logiciel.
  --------------------------------------------------------------------------

  neoSlice - AI-Powered 3D Print Optimizer
  © 2026 Emmanuel Percheron - Tous droits réservés
