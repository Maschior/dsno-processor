; Script gerado para o Inno Setup
; Configurado para instalação local (Current User) - NÃO requer privilégios de Administrador.

#define MyAppVersion "2.0"

[Setup]
; Informações Básicas
AppId={{6ee8a011-ae1d-49fd-a75c-a8495770db88}}
AppName=DSNO Processor
AppVerName=DSNO Processor
AppVersion={#MyAppVersion}
AppPublisher=Matheus Borges
DefaultDirName={sd}\Users\{username}\Softwares\DSNO Processor
DefaultGroupName=DSNO Processor
AllowNoIcons=yes
; Define que NÃO precisa de Admin
PrivilegesRequired=lowest
OutputBaseFilename=DSNO Processor Installer
SetupIconFile=assets\icons\favicon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern dynamic windows11 includetitlebar
;WizardSmallImageFile=assets\logo-light.png
;WizardSmallImageFileDynamicDark=assets\logo-dark.png
;WizardImageAlphaFormat=defined
UninstallDisplayIcon={app}\favicon.ico

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Copia tudo da pasta dist gerada pelo PyInstaller
Source: "dist\DSNO Processor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; NOTA: O arquivo config.toml não deve ser sobrescrito se já existir (opcional)
Source: "config.toml.example"; DestDir: "{app}"; DestName: "config.toml"; Flags: ignoreversion onlyifdoesntexist
; icon
Source: "assets\icons\favicon.ico"; DestDir: "{app}"; Flags: ignoreversion
; Driver JDBC do Oracle (módulo de Pendências) — fica em {app}\java\ojdbc17.jar
Source: "java\ojdbc17.jar"; DestDir: "{app}\java"; Flags: ignoreversion
; Java 21 embarcado — copiado como zip e extraído pelo [Run] abaixo; o zip é
; removido ao final da instalação (deleteafterinstall).
Source: "java\jdk-21.0.10_windows-x64_bin.zip"; DestDir: "{app}\java"; Flags: ignoreversion deleteafterinstall

[Icons]
Name: "{group}\DSNO Processor"; Filename: "{app}\DSNO Processor.exe"
Name: "{userdesktop}\DSNO Processor"; Filename: "{app}\DSNO Processor.exe"; Tasks: desktopicon

[Run]
; Extrai o Java 21 embarcado para {app}\java\jdk-21.0.10 (usado pelo módulo de
; Pendências). Roda antes do lançamento do app.
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Expand-Archive -Path '{app}\java\jdk-21.0.10_windows-x64_bin.zip' -DestinationPath '{app}\java' -Force"""; StatusMsg: "Extraindo Java 21..."; Flags: runhidden waituntilterminated
Description: "{cm:LaunchProgram,DSNO Processor}"; FileName: "{app}\DSNO Processor.exe"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove o Java extraído na desinstalação (não foi rastreado pelo instalador).
Type: filesandordirs; Name: "{app}\java"
