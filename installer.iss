; AutoApply Windows Installer
; Built with Inno Setup 6 — https://jrsoftware.org/isinfo.php
;
; Requirements before running this script:
;   1. pyinstaller AutoApply.spec  →  dist\AutoApply\AutoApply.exe
;   2. ISCC installer.iss          →  dist\installer\AutoApply-Setup.exe

#define MyAppName      "AutoApply"
#define MyAppVersion   "1.0.0"
#define MyAppPublisher "AutoApply"
#define MyAppExeName   "AutoApply.exe"
#define MyAppSourceDir "dist\AutoApply"

[Setup]
AppId={{D94EF8D5-3A42-4CD2-8C17-84F568ED1A9E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com
AppSupportURL=https://github.com
AppUpdatesURL=https://github.com
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist\installer
OutputBaseFilename=AutoApply-Setup
SetupIconFile=assets\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
CreateUninstallRegKey=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";     Description: "Create a &desktop shortcut";          GroupDescription: "Shortcuts:"
Name: "startupicon";     Description: "Start AutoApply with &Windows";        GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "installchromium"; Description: "Install &Chromium browser engine (~150 MB)"; GroupDescription: "Components:"

[Files]
Source: "{#MyAppSourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "config.yaml";    DestDir: "{app}"; Flags: onlyifdoesntexist ignoreversion
Source: "questions.yaml"; DestDir: "{app}"; Flags: onlyifdoesntexist ignoreversion
Source: ".env.example";   DestDir: "{app}"; Flags: onlyifdoesntexist ignoreversion; DestName: ".env.example"

[Icons]
Name: "{group}\{#MyAppName}";           Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Parameters: "--show"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";     Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Parameters: "--show"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}";     Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--install-browsers"; StatusMsg: "Installing Chromium browser engine (~150 MB)..."; Flags: runhidden waituntilterminated; Tasks: installchromium
Filename: "{app}\{#MyAppExeName}"; Parameters: "--show"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "cmd.exe"; Parameters: "/c rmdir /s /q ""{localappdata}\ms-playwright"""; Flags: runhidden; RunOnceId: "RemovePlaywrightCache"

[Registry]
Root: HKCU; Subkey: "Software\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  EnvPath, Msg: string;
begin
  if CurStep = ssDone then
  begin
    EnvPath := ExpandConstant('{app}\.env');
    if not FileExists(EnvPath) then
    begin
      Msg := 'Setup complete!' + #13#10 + #13#10 +
             'Before first use, copy .env.example to .env and set:' + #13#10 +
             '  ANTHROPIC_API_KEY=sk-ant-...' + #13#10 +
             '  PROFILE_EMAIL=you@email.com' + #13#10 +
             '  PROFILE_PHONE=555-555-5555' + #13#10 + #13#10 +
             'Also fill in your profile in config.yaml.' + #13#10 + #13#10 +
             'Installed to: ' + ExpandConstant('{app}');
      MsgBox(Msg, mbInformation, MB_OK);
    end;
  end;
end;
