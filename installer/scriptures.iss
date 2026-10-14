; Inno Setup script for the Windows installer. Built by tool/build_installer.py, which passes
; /DSourceDir=<flutter release folder>, /DAppVersion=<x.y.z>, /DOutputDir=<folder> and /DIconFile=<path>.
; The installer is per-user (no administrator rights) and does not bundle scripture data: data is installed
; from a folder or downloaded from inside the app.

#define AppName "Scriptura"
#define AppExe "Scriptura.exe"

[Setup]
AppId={{B7C1E4B0-5D3A-4B52-9B65-3C8F7A1E2D41}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Scriptura Labs
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
LicenseFile={#SourceRoot}\installer\terms.txt
OutputDir={#OutputDir}
OutputBaseFilename=Scriptura-Setup-{#AppVersion}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; the user's notes, bookmarks and installed data live in the per-user app data folder and are never removed here
Type: filesandordirs; Name: "{app}"
