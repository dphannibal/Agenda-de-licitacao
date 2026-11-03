; Instalador da Agenda de Licitações (Inno Setup 6).
; Gerado pelo GitHub Actions (.github/workflows/instalador.yml) a partir do executável que o
; PyInstaller deixa em dist\AgendaLicitacoes. Para gerar à mão, num Windows:
;   pyinstaller --distpath dist instalador\agenda.spec
;   "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" /DVersao=1.1.0 instalador\AgendaLicitacoes.iss

#ifndef Versao
  #define Versao "1.1.0"
#endif
#define Nome "Agenda de Licitações"
#define Exe "AgendaLicitacoes.exe"
#define Porta "8080"
#define Tarefa "Agenda de Licitacoes"

[Setup]
AppId={{6E0C5B7A-3F1D-4B8E-9C2A-7D4E1F0A8B35}
AppName={#Nome}
AppVersion={#Versao}
AppVerName={#Nome} {#Versao}
AppPublisher={#Nome}
DefaultDirName=C:\AgendaLicitacoes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=AgendaLicitacoes-Instalador-{#Versao}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#Exe}
UninstallDisplayName={#Nome}
CloseApplications=no
SetupLogging=yes

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "iniciar"; Description: "Iniciar o sistema automaticamente com o Windows (recomendado)"
Name: "compartilhar"; Description: "Compartilhar a pasta do programa na rede como ""Licitacoes"", somente leitura (recomendado)"
Name: "firewall"; Description: "Liberar a porta {#Porta} no Firewall do Windows para redes privadas e de domínio (recomendado)"
Name: "nuvem"; Description: "Guardar cópias do banco de dados numa pasta do Google Drive (recomendado)"

[Files]
Source: "..\dist\AgendaLicitacoes\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "configurar.ps1"; DestDir: "{app}\instalador"; Flags: ignoreversion

[INI]
; Atalho na área de trabalho do computador hospedeiro.
Filename: "{commondesktop}\{#Nome}.url"; Section: "InternetShortcut"; Key: "URL"; String: "http://localhost:{#Porta}/"

[Run]
Filename: "{app}\{#Exe}"; Parameters: "{code:ParametrosPreparar}"; StatusMsg: "Preparando o banco de dados..."; Flags: runhidden waituntilterminated
Filename: "powershell.exe"; Parameters: "{code:ParametrosConfigurar|instalar}"; StatusMsg: "Configurando o Windows..."; Flags: runhidden waituntilterminated
Filename: "{commondesktop}\{#Nome}.url"; Description: "Abrir a Agenda de Licitações"; Tasks: iniciar; Flags: postinstall shellexec nowait skipifsilent
Filename: "{app}\{#Exe}"; Description: "Iniciar a Agenda de Licitações agora (janela do servidor)"; Tasks: not iniciar; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "{code:ParametrosConfigurar|desinstalar}"; Flags: runhidden waituntilterminated; RunOnceId: "Desconfigurar"

[UninstallDelete]
Type: files; Name: "{app}\Abrir Agenda de Licitações.url"
Type: files; Name: "{commondesktop}\{#Nome}.url"

[Code]
var
  PaginaNuvem: TInputDirWizardPage;

function GetVolumeInformation(Raiz: String; Nome: String; TamanhoNome: Cardinal;
  var Serie: Cardinal; var Componente: Cardinal; var Opcoes: Cardinal;
  Sistema: String; TamanhoSistema: Cardinal): Boolean;
  external 'GetVolumeInformationW@kernel32.dll stdcall';

{ Pasta do Google Drive para computador, quando ele já está instalado. }
function PastaGoogleDrive: String;
var
  Candidatas: TArrayOfString;
  I: Integer;
begin
  SetArrayLength(Candidatas, 4);
  Candidatas[0] := ExpandConstant('{%USERPROFILE}\Meu Drive');
  Candidatas[1] := ExpandConstant('{%USERPROFILE}\My Drive');
  Candidatas[2] := 'G:\Meu Drive';
  Candidatas[3] := 'G:\My Drive';
  Result := '';
  for I := 0 to GetArrayLength(Candidatas) - 1 do
    if DirExists(Candidatas[I]) then
    begin
      Result := Candidatas[I] + '\AgendaLicitacoes';
      Exit;
    end;
end;

{ A unidade virtual do Google Drive (modo "transmitir arquivos") só existe na sessão do
  usuário: o sistema, que roda como serviço, não a enxerga. }
function NaUnidadeVirtualDoDrive(Pasta: String): Boolean;
var
  Nome, Sistema: String;
  Serie, Componente, Opcoes: Cardinal;
begin
  Nome := StringOfChar(' ', 261);
  Sistema := StringOfChar(' ', 261);
  Result := GetVolumeInformation(AddBackslash(ExtractFileDrive(Pasta)), Nome, 261, Serie,
    Componente, Opcoes, Sistema, 261) and (Pos('GOOGLE DRIVE', Uppercase(Nome)) > 0);
end;

procedure InitializeWizard;
begin
  PaginaNuvem := CreateInputDirPage(wpSelectTasks, 'Cópia de segurança no Google Drive',
    'Em qual pasta do Google Drive guardar as cópias do banco de dados?',
    'O banco continua neste computador. A cada 5 minutos com alterações, uma cópia completa ' +
    'vai para a pasta abaixo, junto com uma cópia por dia dos últimos 30 dias. Use uma pasta ' +
    'dentro do "Meu Drive" com o Google Drive no modo "Espelhar arquivos".' + #13#10#13#10 +
    'Se este computador quebrar, instale o programa em outro indicando a mesma pasta: ele ' +
    'restaura a última cópia e assume. Dois computadores nunca servem a agenda ao mesmo tempo.',
    False, 'AgendaLicitacoes');
  PaginaNuvem.Add('Pasta das cópias:');
  { Instalação silenciosa: /NUVEM="pasta". Atualização: a pasta escolhida da outra vez. }
  PaginaNuvem.Values[0] := ExpandConstant('{param:NUVEM}');
  if PaginaNuvem.Values[0] = '' then
    PaginaNuvem.Values[0] := GetPreviousData('Nuvem', PastaGoogleDrive);
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  SetPreviousData(PreviousDataKey, 'Nuvem', PaginaNuvem.Values[0]);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = PaginaNuvem.ID) and not WizardIsTaskSelected('nuvem');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Pasta: String;
begin
  Result := True;
  if CurPageID = PaginaNuvem.ID then
  begin
    Pasta := Trim(PaginaNuvem.Values[0]);
    if Pasta = '' then
    begin
      MsgBox('Informe a pasta do Google Drive ou volte e desmarque a opção de cópias.',
        mbError, MB_OK);
      Result := False;
    end
    else if NaUnidadeVirtualDoDrive(Pasta) then
      Result := MsgBox('Esta pasta está na unidade virtual do Google Drive, que o sistema ' +
        '(iniciado com o Windows, sem usuário) não consegue acessar.' + #13#10#13#10 +
        'Nas preferências do Google Drive, mude "Meu Drive" para "Espelhar arquivos" e escolha ' +
        'uma pasta dentro de C:\Users\...\Meu Drive.' + #13#10#13#10 + 'Continuar mesmo assim?',
        mbConfirmation, MB_YESNO) = IDYES;
  end;
end;

function PastaNuvem: String;
begin
  Result := '';
  if WizardIsTaskSelected('nuvem') then
    Result := RemoveBackslashUnlessRoot(Trim(PaginaNuvem.Values[0]));
end;

function ParametrosPreparar(Param: String): String;
begin
  Result := '--preparar';
  if PastaNuvem <> '' then Result := Result + ' --nuvem "' + PastaNuvem + '"';
end;

{ Parâmetros do configurar.ps1 conforme as opções marcadas no assistente. }
function ParametrosConfigurar(Acao: String): String;
begin
  Result := '-NoProfile -ExecutionPolicy Bypass -File "' +
    ExpandConstant('{app}\instalador\configurar.ps1') + '" -Acao ' + Acao +
    ' -Pasta "' + ExpandConstant('{app}') + '" -Porta {#Porta}';
  if Acao = 'instalar' then
  begin
    if WizardIsTaskSelected('iniciar') then Result := Result + ' -Iniciar';
    if WizardIsTaskSelected('compartilhar') then Result := Result + ' -Compartilhar';
    if WizardIsTaskSelected('firewall') then Result := Result + ' -Firewall';
    if PastaNuvem <> '' then Result := Result + ' -Nuvem "' + PastaNuvem + '"';
  end;
end;

{ Atualização: para o sistema em execução antes de substituir os arquivos. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Codigo: Integer;
begin
  Exec(ExpandConstant('{sys}\schtasks.exe'), '/End /TN "{#Tarefa}"', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#Exe}', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  Result := '';
end;

procedure CurPageChanged(CurPageID: Integer);
var
  Texto: String;
begin
  if CurPageID = wpFinished then
  begin
    Texto := 'A Agenda de Licitações foi instalada.' + #13#10#13#10 +
      'Neste computador: atalho "{#Nome}" na área de trabalho (http://localhost:{#Porta}/).';
    if WizardIsTaskSelected('compartilhar') then
      Texto := Texto + #13#10#13#10 + 'Nos demais computadores: abra \\' + GetComputerNameString +
        '\Licitacoes e dê dois cliques em "Abrir Agenda de Licitações".';
    Texto := Texto + #13#10#13#10 + 'Primeira instalação: abra o atalho neste computador e crie a ' +
      'conta do administrador (só é possível neste computador).';
    Texto := Texto + #13#10#13#10 + 'Os dados ficam em ' + ExpandConstant('{commonappdata}') +
      '\AgendaLicitacoes';
    if PastaNuvem <> '' then
      Texto := Texto + ', com cópias em ' + PastaNuvem + '.'
    else
      Texto := Texto + ' (faça backup dessa pasta).';
    WizardForm.FinishedLabel.Caption := Texto;
  end;
end;
