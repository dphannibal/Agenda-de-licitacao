; Instalador do programa dos USUÁRIOS da Agenda de Licitações (Inno Setup 6).
; Instala só o AgendaUsuario.exe, que acha o servidor na rede e abre o sistema no navegador.
; Não pede nada nem exige administrador do Windows. O instalador do servidor deixa uma cópia
; deste na pasta compartilhada; instalado de lá, ele guarda essa pasta como reserva para
; achar o servidor.
;   pyinstaller --distpath dist instalador\usuario.spec
;   "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" /DVersao=1.1.0 instalador\AgendaUsuario.iss

#ifndef Versao
  #define Versao "1.1.0"
#endif
#define Nome "Agenda de Licitações"
#define Exe "AgendaUsuario.exe"

[Setup]
AppId={{9B2F4C61-0D3E-4A7B-8E15-3C6A2D9F7B48}
AppName={#Nome} (usuário)
AppVersion={#Versao}
AppVerName={#Nome} {#Versao} (usuário)
AppPublisher={#Nome}
DefaultDirName={localappdata}\Programs\AgendaLicitacoes
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=AgendaLicitacoes-Usuario-{#Versao}
SetupIconFile=icone.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#Exe}
UninstallDisplayName={#Nome} (usuário)

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "..\dist\{#Exe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\{#Nome}"; Filename: "{app}\{#Exe}"
Name: "{userdesktop}\{#Nome}"; Filename: "{app}\{#Exe}"

[Run]
Filename: "{app}\{#Exe}"; Parameters: "{code:ParametroPasta}"; Check: InstaladoDoServidor; Flags: runhidden waituntilterminated
Filename: "{app}\{#Exe}"; Description: "Abrir a {#Nome}"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\AgendaLicitacoes"

[Code]
{ Pasta de onde o instalador foi aberto: a compartilhada do servidor, se tiver o atalho. }
function PastaDeOrigem: String;
begin
  Result := ExtractFileDir(ExpandConstant('{srcexe}'));
end;

function InstaladoDoServidor: Boolean;
begin
  Result := FileExists(PastaDeOrigem + '\Abrir Agenda de Licitações.url');
end;

function ParametroPasta(Param: String): String;
begin
  Result := '--pasta-servidor "' + PastaDeOrigem + '"';
end;
