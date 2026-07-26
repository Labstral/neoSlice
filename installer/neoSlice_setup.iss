; Script Inno Setup — neoSlice Installer
; Généré automatiquement — ne pas modifier manuellement
; Pour compiler : ISCC.exe neoSlice_setup.iss

#define AppName      "neoSlice"
#define AppVersion   "0.1.8.4"
#define AppPublisher "Emmanuel Percheron"
#define AppURL       "https://github.com/neoslice"
#define AppExeName   "neoSlice.exe"
#define SourceDir    "C:\neoSlice\dist\neoSlice"
#define OutputDir    "C:\neoSlice\dist\installer"

[Setup]
AppId={{A3F2C8D1-7B4E-4F9A-B2C6-E8D3A1F5C7B9}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}

; Répertoire d'installation dans AppData (pas besoin d'admin, pas de conflit DLL)
DefaultDirName={localappdata}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

; Fichiers de sortie
OutputDir={#OutputDir}
OutputBaseFilename=neoSlice_Setup_v{#AppVersion}_Windows
SetupIconFile=..\assets\neoSlice.ico

; Compression
Compression=lzma2/ultra64
SolidCompression=yes
LZMANumFastBytes=273

; Interface
WizardStyle=modern

; Droits requis — AppData ne nécessite pas d'admin
PrivilegesRequired=lowest

; License
LicenseFile=LICENSE.txt

; Version info dans le setup.exe
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}

; Mise à jour — ferme automatiquement TOUT programme qui verrouille un fichier à
; remplacer, pas seulement neoSlice.exe. Un processus ENFANT survivant
; (QtWebEngineProcess.exe, worker…) gardait « _internal\msvcp140.dll » ouvert
; -> « DeleteFile a échoué ; code 5. Accès refusé ». En restreignant le filtre à
; neoSlice.exe, ces enfants étaient IGNORÉS. On revient donc au filtre par défaut
; (*.exe) : le gestionnaire de redémarrage Windows ferme tous les verrouilleurs.
; force = terminaison forcée si la fermeture gracieuse échoue (helper sans fenêtre,
; process figé/zombie). Débloque aussi les utilisateurs déjà coincés.
CloseApplications=force
RestartApplications=no

; Désinstalleur
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName} {#AppVersion}


[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"


[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le &Bureau"; GroupDescription: "Raccourcis :"


[Files]
; Dossier onedir complet (EXE + DLL + données PyInstaller)
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Documentation
Source: "README.txt";  DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion


[Icons]
; Menu Démarrer
Name: "{group}\{#AppName}";           Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"
Name: "{group}\Désinstaller {#AppName}"; Filename: "{uninstallexe}"; IconFilename: "{app}\{#AppExeName}"

; Bureau (optionnel — coché par défaut)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"; Tasks: desktopicon


[Run]
; Proposer de lancer neoSlice à la fin de l'installation
Filename: "{app}\{#AppExeName}"; \
  Description: "Lancer {#AppName}"; \
  Flags: nowait postinstall skipifsilent


[UninstallDelete]
; Nettoyer les fichiers temporaires laissés par PyInstaller au lancement
Type: filesandordirs; Name: "{app}"


[Code]
// Vérification minimale : Windows 10 ou supérieur
function InitializeSetup(): Boolean;
var
  Version: TWindowsVersion;
begin
  GetWindowsVersionEx(Version);
  if Version.Major < 10 then begin
    MsgBox('neoSlice nécessite Windows 10 ou supérieur.', mbError, MB_OK);
    Result := False;
  end else
    Result := True;
end;
