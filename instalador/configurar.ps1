# Configuração do Windows feita pelo instalador da Agenda de Licitações.
#   -Acao instalar     protege as pastas e, conforme as opções, compartilha a pasta do
#                      programa, libera o firewall e inicia o sistema com o Windows
#                      (com -Nuvem, o sistema envia cópias do banco para essa pasta)
#   -Acao desinstalar  desfaz o que foi configurado (os dados são mantidos)
# Nomes de grupos variam com o idioma do Windows, por isso as contas vão por SID.
param(
    [Parameter(Mandatory = $true)][ValidateSet('instalar', 'desinstalar')][string]$Acao,
    [string]$Pasta = (Split-Path -Parent $PSScriptRoot),
    [int]$Porta = 8080,
    [switch]$Compartilhar,
    [switch]$Firewall,
    [switch]$Iniciar,
    [string]$Nuvem = ''
)

$ErrorActionPreference = 'Stop'
$Tarefa = 'Agenda de Licitacoes'
$Regra = 'Agenda de Licitacoes'
$Compartilhamento = 'Licitacoes'
$Dados = Join-Path $env:ProgramData 'AgendaLicitacoes'
$Exe = Join-Path $Pasta 'AgendaLicitacoes.exe'

New-Item -ItemType Directory -Force -Path $Dados | Out-Null
Start-Transcript -Path (Join-Path $Dados 'instalacao.log') -Append | Out-Null
$script:Falhas = 0

function Conta([string]$Sid) {
    ([Security.Principal.SecurityIdentifier]$Sid).Translate([Security.Principal.NTAccount]).Value
}

function Etapa([string]$Texto, [scriptblock]$Bloco) {
    try {
        & $Bloco
        Write-Output "OK: $Texto"
    } catch {
        Write-Output "FALHOU: $Texto - $($_.Exception.Message)"
        $script:Falhas++
    }
}

function Executar([string]$Programa, [string[]]$Argumentos) {
    & $Programa @Argumentos | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "$Programa terminou com código $LASTEXITCODE" }
}

function Remove-Configuracao {
    Etapa 'parar o sistema' {
        if (Get-ScheduledTask -TaskName $Tarefa -ErrorAction SilentlyContinue) {
            Stop-ScheduledTask -TaskName $Tarefa
        }
        Get-Process -Name 'AgendaLicitacoes' -ErrorAction SilentlyContinue | Stop-Process -Force
    }
    Etapa 'remover o início automático' {
        if (Get-ScheduledTask -TaskName $Tarefa -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $Tarefa -Confirm:$false
        }
    }
    Etapa 'remover a regra do firewall' {
        Get-NetFirewallRule -DisplayName $Regra -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    }
    Etapa 'remover o compartilhamento' {
        if (Get-SmbShare -Name $Compartilhamento -ErrorAction SilentlyContinue) {
            Remove-SmbShare -Name $Compartilhamento -Force
        }
    }
}

if ($Acao -eq 'desinstalar') {
    Remove-Configuracao
} else {
    Remove-Configuracao   # reinstalação/atualização: recomeça do zero

    # Dados (banco, chave das sessões, brasão): só administradores e o sistema.
    Etapa 'proteger a pasta de dados' {
        Executar 'icacls.exe' @($Dados, '/inheritance:r', '/grant:r',
            '*S-1-5-32-544:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F')
    }
    # Programa: usuários autenticados só leem (inclusive pela rede).
    Etapa 'permissões da pasta do programa' {
        Executar 'icacls.exe' @($Pasta, '/inheritance:r', '/grant:r',
            '*S-1-5-32-544:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F', '*S-1-5-11:(OI)(CI)RX')
    }
    if ($Firewall) {
        Etapa "liberar a porta $Porta no firewall" {
            New-NetFirewallRule -DisplayName $Regra -Direction Inbound -Action Allow -Protocol TCP `
                -LocalPort $Porta -Profile Domain, Private | Out-Null
        }
    }
    if ($Compartilhar) {
        Etapa "compartilhar a pasta como \\$env:COMPUTERNAME\$Compartilhamento (somente leitura)" {
            New-SmbShare -Name $Compartilhamento -Path $Pasta -ReadAccess (Conta 'S-1-1-0') `
                -Description 'Agenda de Licitações' | Out-Null
        }
    }
    if ($Iniciar) {
        # Tarefa agendada como SYSTEM: o sistema sobe com o Windows, mesmo sem ninguém logado,
        # sem limite de tempo de execução e reiniciando sozinho se cair.
        Etapa 'iniciar com o Windows' {
            $argumentos = "--porta $Porta"
            if ($Nuvem) { $argumentos += " --nuvem `"$($Nuvem.TrimEnd('\'))`"" }
            $executar = New-ScheduledTaskAction -Execute $Exe -WorkingDirectory $Pasta -Argument $argumentos
            $gatilho = New-ScheduledTaskTrigger -AtStartup
            $opcoes = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
                -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
                -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
            $conta = New-ScheduledTaskPrincipal -UserId (Conta 'S-1-5-18') -LogonType ServiceAccount -RunLevel Highest
            Register-ScheduledTask -TaskName $Tarefa -Action $executar -Trigger $gatilho -Settings $opcoes `
                -Principal $conta -Description 'Agenda de Licitações' -Force | Out-Null
            Start-ScheduledTask -TaskName $Tarefa
        }
    }
}

Write-Output "Concluído com $script:Falhas falha(s)."
Stop-Transcript | Out-Null
exit $script:Falhas
