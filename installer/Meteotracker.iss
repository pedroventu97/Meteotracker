[Setup]
AppId={{B6E1D2A8-4AFB-4A66-8BAA-77F4F5B65A11}
AppName=Meteotracker
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\Meteotracker
DefaultGroupName=Meteotracker
OutputDir=..\dist
OutputBaseFilename=Meteotracker-{#AppVersion}-setup
PrivilegesRequired=lowest
Uninstallable=yes

[Files]
Source: "..\dist\Meteotracker\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Meteotracker"; Filename: "{app}\Meteotracker.exe"
Name: "{autodesktop}\Meteotracker"; Filename: "{app}\Meteotracker.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Crea collegamento sul desktop"; Flags: unchecked

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
