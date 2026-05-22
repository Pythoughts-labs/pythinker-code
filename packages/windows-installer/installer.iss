; Pythinker Code — Windows native installer
; Inno Setup 6 syntax. Per-user install, no UAC by default.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{4F4F2EAE-9D55-4E8E-92BC-7C1FA38B6F02}
AppName=Pythinker Code
AppVersion={#AppVersion}
AppPublisher=Pythinker
AppPublisherURL=https://pythinker.com
AppSupportURL=https://github.com/mohamed-elkholy95/Pythinker-Code/issues
AppUpdatesURL=https://github.com/mohamed-elkholy95/Pythinker-Code/releases
DefaultDirName={localappdata}\Programs\Pythinker
DefaultGroupName=Pythinker
DisableProgramGroupPage=yes
DisableDirPage=no
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
OutputDir=..\..\dist
OutputBaseFilename=PythinkerSetup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\pythinker.ico
UninstallDisplayIcon={app}\pythinker.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=assets\LICENSE.rtf
ChangesEnvironment=yes
CloseApplications=force
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "modifypath"; Description: "Add Pythinker to your PATH"; \
  GroupDescription: "Shell integration:"; Check: not IsAdminInstallMode

Name: "modifypathmachine"; Description: "Add Pythinker to the system PATH"; \
  GroupDescription: "Shell integration:"; Check: IsAdminInstallMode

[Files]
Source: "..\..\dist\pythinker\*"; DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs
; Drop the native-build sentinel directly next to pythinker.exe (NOT inside
; _internal/). PyInstaller >=6.1 hides bundled data files under _internal/,
; which would make is_native_build() always return False.
Source: ".pythinker-native"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Pythinker"; Filename: "{app}\pythinker.exe"
Name: "{group}\Uninstall Pythinker"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\pythinker.exe"; Description: "Launch Pythinker"; \
  Flags: nowait postinstall skipifsilent unchecked

[Code]
function NeedsAddPath(Param, RootHive: string): Boolean;
var
  OrigPath: string;
  Root: Integer;
  Subkey, ValueName: string;
begin
  if RootHive = 'HKCU' then begin
    Root := HKEY_CURRENT_USER;
    Subkey := 'Environment';
  end else begin
    Root := HKEY_LOCAL_MACHINE;
    Subkey := 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';
  end;
  ValueName := 'Path';
  if not RegQueryStringValue(Root, Subkey, ValueName, OrigPath) then begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + UpperCase(Param) + ';',
                ';' + UpperCase(OrigPath) + ';') = 0;
end;

procedure AddToPath(Param, RootHive: string);
var
  OrigPath, NewPath: string;
  Root: Integer;
  Subkey: string;
begin
  if RootHive = 'HKCU' then begin
    Root := HKEY_CURRENT_USER;
    Subkey := 'Environment';
  end else begin
    Root := HKEY_LOCAL_MACHINE;
    Subkey := 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';
  end;
  if not RegQueryStringValue(Root, Subkey, 'Path', OrigPath) then
    OrigPath := '';
  if OrigPath = '' then
    NewPath := Param
  else
    NewPath := OrigPath + ';' + Param;
  RegWriteExpandStringValue(Root, Subkey, 'Path', NewPath);
end;

procedure RemoveFromPath(Param, RootHive: string);
var
  OrigPath: string;
  Root: Integer;
  Subkey: string;
begin
  if RootHive = 'HKCU' then begin
    Root := HKEY_CURRENT_USER;
    Subkey := 'Environment';
  end else begin
    Root := HKEY_LOCAL_MACHINE;
    Subkey := 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';
  end;
  if not RegQueryStringValue(Root, Subkey, 'Path', OrigPath) then exit;
  StringChangeEx(OrigPath, ';' + Param, '', True);
  StringChangeEx(OrigPath, Param + ';', '', True);
  StringChangeEx(OrigPath, Param, '', True);
  RegWriteExpandStringValue(Root, Subkey, 'Path', OrigPath);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  AppDir: string;
begin
  if CurStep = ssPostInstall then begin
    AppDir := ExpandConstant('{app}');
    if WizardIsTaskSelected('modifypath')
       and NeedsAddPath(AppDir, 'HKCU') then
      AddToPath(AppDir, 'HKCU');
    if WizardIsTaskSelected('modifypathmachine')
       and NeedsAddPath(AppDir, 'HKLM') then
      AddToPath(AppDir, 'HKLM');
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDir: string;
begin
  if CurUninstallStep = usUninstall then begin
    AppDir := ExpandConstant('{app}');
    RemoveFromPath(AppDir, 'HKCU');
    if IsAdminInstallMode then
      RemoveFromPath(AppDir, 'HKLM');
  end;
end;

function InitializeSetup(): Boolean;
var
  OtherScopeKey: string;
  Found: Boolean;
begin
  OtherScopeKey :=
    'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
    '{4F4F2EAE-9D55-4E8E-92BC-7C1FA38B6F02}_is1';

  if IsAdminInstallMode then
    Found := RegKeyExists(HKEY_CURRENT_USER, OtherScopeKey)
  else
    Found := RegKeyExists(HKEY_LOCAL_MACHINE, OtherScopeKey);

  if Found then begin
    MsgBox('An existing Pythinker install was found at a different scope. '
           + 'Please uninstall it from Apps & Features before continuing.',
           mbError, MB_OK);
    Result := False;
  end else
    Result := True;
end;
