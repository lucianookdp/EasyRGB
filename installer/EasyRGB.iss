; EasyRGB - instalador (Inno Setup 6). Gerado por tools/build_exe.py; o GitHub Actions gera em cada versão.
; Instala só para o usuário atual (não precisa de administrador para os arquivos, e o app consegue se atualizar
; sozinho). O administrador é pedido uma vez, no fim, para instalar o driver PawnIO que o OpenRGB usa.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\EasyRGB"
#endif

[Setup]
AppId={{6B1F2E7A-3C4D-4E8F-9A1B-EA5B0C7D2E19}
AppName=EasyRGB
AppVersion={#AppVersion}
AppVerName=EasyRGB {#AppVersion}
AppPublisher=EasyRGB (open source)
AppPublisherURL=https://github.com/lucianookdp/EasyRGB
AppSupportURL=https://github.com/lucianookdp/EasyRGB/issues
AppUpdatesURL=https://github.com/lucianookdp/EasyRGB/releases
DefaultDirName={localappdata}\Programs\EasyRGB
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputBaseFilename=EasyRGB-Setup
SetupIconFile=..\app\icon.ico
UninstallDisplayIcon={app}\EasyRGB.exe
UninstallDisplayName=EasyRGB
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
VersionInfoVersion={#AppVersion}
VersionInfoDescription=EasyRGB Setup

[Languages]
; o instalador aparece no idioma do Windows (os 30 idiomas que o Inno Setup traz)
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"
Name: "armenian"; MessagesFile: "compiler:Languages\Armenian.isl"
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "bulgarian"; MessagesFile: "compiler:Languages\Bulgarian.isl"
Name: "catalan"; MessagesFile: "compiler:Languages\Catalan.isl"
Name: "corsican"; MessagesFile: "compiler:Languages\Corsican.isl"
Name: "czech"; MessagesFile: "compiler:Languages\Czech.isl"
Name: "danish"; MessagesFile: "compiler:Languages\Danish.isl"
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"
Name: "finnish"; MessagesFile: "compiler:Languages\Finnish.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "hebrew"; MessagesFile: "compiler:Languages\Hebrew.isl"
Name: "hungarian"; MessagesFile: "compiler:Languages\Hungarian.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "norwegian"; MessagesFile: "compiler:Languages\Norwegian.isl"
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "slovak"; MessagesFile: "compiler:Languages\Slovak.isl"
Name: "slovenian"; MessagesFile: "compiler:Languages\Slovenian.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "swedish"; MessagesFile: "compiler:Languages\Swedish.isl"
Name: "tamil"; MessagesFile: "compiler:Languages\Tamil.isl"
Name: "thai"; MessagesFile: "compiler:Languages\Thai.isl"
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "ukrainian"; MessagesFile: "compiler:Languages\Ukrainian.isl"

[CustomMessages]
; sem prefixo = inglês para todos os idiomas; "pt." = português
DesktopIcon=Create a desktop shortcut
pt.DesktopIcon=Criar atalho na Área de Trabalho
Driver=Installing OpenRGB support and the PawnIO driver (Windows asks for administrator permission once)...
pt.Driver=Instalando o suporte ao OpenRGB e o driver PawnIO (o Windows pede permissão de administrador uma vez)...
Open=Open EasyRGB
pt.Open=Abrir o EasyRGB

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; dados de cada PC ficam em {app}\app e não são apagados numa atualização

[Dirs]
Name: "{app}\app"

[Icons]
Name: "{autoprograms}\EasyRGB"; Filename: "{app}\EasyRGB.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\EasyRGB"; Filename: "{app}\EasyRGB.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; OpenRGB já vem no pacote; isto instala o driver e desliga o ASRock Polychrome (reversível). Pede admin uma vez.
; Instalação silenciosa (winget, /VERYSILENT): pula; o EasyRGB.exe faz isso ao abrir pela primeira vez.
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\1-Configurar (admin).ps1"""; \
  WorkingDir: "{app}"; StatusMsg: "{cm:Driver}"; Flags: runhidden waituntilterminated; Check: NotConfigured and not WizardSilent
Filename: "{app}\EasyRGB.exe"; Description: "{cm:Open}"; WorkingDir: "{app}"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/im EasyRGB.exe /f"; Flags: runhidden; RunOnceId: "KillApp"
; tira o "Restaurar ao ligar o PC" (a tarefa foi criada como admin: o Windows pede permissão)
Filename: "{app}\EasyRGB.exe"; Parameters: "iniciar-com-windows nao"; Flags: runhidden waituntilterminated; RunOnceId: "DelTask"

[UninstallDelete]
; os dados do PC (pasta app: perfil, visual, presets) ficam, caso a pessoa instale de novo
Type: files; Name: "{app}\configurado.ok"
Type: files; Name: "{app}\app\easyrgb.log"

[Code]
function NotConfigured(): Boolean;
begin
  Result := not FileExists(ExpandConstant('{app}\configurado.ok'));
end;
