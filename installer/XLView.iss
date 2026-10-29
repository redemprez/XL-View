#define AppVersion "0.7.0"
#ifndef PayloadDir
  #define PayloadDir "..\release\payload\XL View"
#endif

[Setup]
AppId={{65A650D9-AB05-4D38-8E26-1080E1416CF1}
AppName=XL View
AppVersion={#AppVersion}
AppVerName=XL View {#AppVersion}
DefaultDirName={localappdata}\Programs\XL View
DefaultGroupName=XL View
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19041
OutputDir=..\release
OutputBaseFilename=XL-View-Setup-{#AppVersion}-x64
SetupIconFile=..\lcxl\assets\xl-view.ico
UninstallDisplayIcon={app}\XL View.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
VersionInfoVersion={#AppVersion}
InfoAfterFile=INSTALL.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "installed-mode.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "INSTALL.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\XL View"; Filename: "{app}\XL View.exe"; WorkingDir: "{app}"
Name: "{group}\Preset library folder"; Filename: "{localappdata}\XL View\presets"
Name: "{autodesktop}\XL View"; Filename: "{app}\XL View.exe"; Tasks: desktopicon

[Dirs]
Name: "{localappdata}\XL View\presets"; Flags: uninsneveruninstall

[Run]
Filename: "{app}\XL View.exe"; Description: "{cm:LaunchProgram,XL View}"; Flags: nowait postinstall skipifsilent unchecked

; No UninstallDelete: presets, backups and QSettings are user data.
