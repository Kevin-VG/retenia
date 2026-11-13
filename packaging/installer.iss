; Inno Setup 6: genera dist/RetenIA-<versión>-Setup.exe a partir de dist/RetenIA/
;
;     iscc /DAppVersion=1.0.0 packaging/installer.iss
;
; Instala por usuario (sin pedir administrador). El historial vive en %APPDATA%\RetenIA
; y NO se borra al desinstalar.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{0C785400-EB8E-4A93-83BC-AC8FF8EE6B2B}
AppName=RetenIA
AppVersion={#AppVersion}
AppVerName=RetenIA {#AppVersion}
AppPublisher=Kevin Ventura
AppPublisherURL=https://github.com/Kevin-VG/retenia
AppSupportURL=https://github.com/Kevin-VG/retenia/issues
DefaultDirName={autopf}\RetenIA
DefaultGroupName=RetenIA
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=RetenIA-{#AppVersion}-Setup
SetupIconFile=..\app\resources\icon.ico
UninstallDisplayIcon={app}\RetenIA.exe
LicenseFile=..\LICENSE
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\RetenIA\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\RetenIA"; Filename: "{app}\RetenIA.exe"
Name: "{autodesktop}\RetenIA"; Filename: "{app}\RetenIA.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\RetenIA.exe"; Description: "{cm:LaunchProgram,RetenIA}"; Flags: nowait postinstall skipifsilent
