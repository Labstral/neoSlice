==============================================================================
  neoSlice - AI-Powered 3D Print Optimizer
  Guide d'installation et de démarrage - v0.1.2 Bêta
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
  8. Contact et support


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

  neoSlice_Setup_v0.1.2-beta_Windows.exe  ->  Installateur Windows
  README.txt                       ->  Ce guide
  LICENSE.txt                      ->  Accord de licence utilisateur final


------------------------------------------------------------------------------
3. INSTALLATION PAS À PAS
------------------------------------------------------------------------------

  ÉTAPE 1 - Préparer l'installation
  -----------------------------------
  Avant de lancer l'installateur, il est fortement recommandé de :

    * Fermer tous les programmes ouverts.
    * Désactiver temporairement votre antivirus (voir section 4).
    * Vous assurer d'être connecté en tant qu'administrateur Windows.

  ÉTAPE 2 - Lancer l'installateur
  ---------------------------------
  Double-cliquez sur : neoSlice_Setup_v0.1.2-beta_Windows.exe

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
                                 C:\Program Files\neoSlice\
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


  "ACCÈS REFUSÉ" OU "DROITS INSUFFISANTS"
  -----------------------------------------
  -> Faites un clic droit sur l'installateur
  -> Choisissez "Exécuter en tant qu'administrateur"


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

    1. Configuration  - Sélection de l'imprimante et du filament
    2. Import STL     - Glisser-déposer votre fichier 3D
    3. Mission        - Réglage des critères d'impression
    4. Export         - Génération du fichier .3MF pour Bambu Studio

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
  R : Oui, neoSlice est entièrement gratuit dans sa version actuelle.
      Si le logiciel vous est utile, vous pouvez soutenir son développement
      via un don volontaire sur Buy Me a Coffee. Cela n'est pas obligatoire.

  Q : Le logiciel envoie-t-il mes données quelque part ?
  R : Non. neoSlice fonctionne 100% en local. Aucune donnée n'est
      transmise. Vos fichiers STL et configurations restent sur votre
      machine.

  Q : neoSlice fonctionne-t-il avec toutes les imprimantes Bambu Lab ?
  R : neoSlice est optimisé pour les imprimantes Bambu Lab (X1, P1, A1
      et variantes). Les fichiers .3MF sont compatibles avec Bambu Studio.

  Q : Puis-je utiliser neoSlice sans connexion internet ?
  R : Oui. neoSlice ne nécessite aucune connexion internet.

  Q : Le logiciel plante ou se ferme inopinément - que faire ?
  R : Consultez le fichier journal dans :
      C:\Users\[votre nom]\.neoslice\
      et transmettez-le au support avec une description du problème.

  Q : La mise à jour vers une nouvelle version nécessite-t-elle de
      désinstaller l'ancienne ?
  R : Non. Lancez simplement le nouvel installateur - il remplacera
      automatiquement la version précédente.


------------------------------------------------------------------------------
8. CONTACT ET SUPPORT
------------------------------------------------------------------------------

  Développeur  : Emmanuel Percheron
  Email        : manu.percheron@gmail.com

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
