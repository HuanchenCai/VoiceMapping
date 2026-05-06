; Inno Setup script for VoiceMap installer.
; Compile with: ISCC.exe installer.iss
; Output: dist/VoiceMap_v1.0.0_setup.exe

#define MyAppName        "VoiceMap"
#define MyAppDisplayName "嗓音声学品质多维分析图谱 (VoiceMap)"
#define MyAppVersion     "1.0.0"
#define MyAppPublisher   "蔡寰宸 (Huanchen Cai)"
#define MyAppURL         "https://github.com/HuanchenCai/VoiceMapping"
#define MyAppExeName     "VoiceMap.exe"

[Setup]
AppId={{F4B0E9C8-7A3F-4D2A-9E8C-1B6F3E5D7A2B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=LICENSE
OutputDir=dist
OutputBaseFilename=VoiceMap_v{#MyAppVersion}_setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "chs"; MessagesFile: "compiler:Default.isl,compiler:Languages\ChineseSimplified.isl"
Name: "en";  MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Pull the entire dist/VoiceMap/ folder PyInstaller produces.
Source: "dist\VoiceMap\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
