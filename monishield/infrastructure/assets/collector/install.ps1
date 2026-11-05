<#
MoniShield collector installer for Windows Server (PowerShell 5.1 or newer, run as Administrator).

It installs the OpenTelemetry Collector (otelcol-contrib) from the official MSI, enrolls it with the one-time token from the
MoniShield Collectors page, writes the configuration MoniShield made for this collector and starts the Windows service.
The script holds no secret. Download it to a file, read it, then run it:

  Invoke-WebRequest -UseBasicParsing -OutFile install.ps1 https://<your-MoniShield>/collector/install.ps1
  powershell -ExecutionPolicy Bypass -File .\install.ps1 -Name <collector name> -Token <enrollment token>

Parameters: -Name   the collector's name as on the page (checked against the server's answer)
            -Token  the enrollment token (works once, for 24 hours)
            -Url    MoniShield's address (default: the one this script was served from)
            -Upgrade no token: refresh an installed collector (its key stays; it gets the current configuration)
            -DryRun print the steps and change nothing

Where the key goes: into the service's own environment (the Environment value under
HKLM\SYSTEM\CurrentControlSet\Services\otelcol-contrib). Only administrators and the system can read that key. A machine-wide
environment variable would be readable by every user and process on the server, so it is not used.
#>
param(
  [string]$Name = '',
  [string]$Token = '',
  [string]$Url = '@@URL@@',
  [switch]$Upgrade,
  [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$Version = '@@VERSION@@'
$Release = "https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v$Version"
$Asset = "otelcol-contrib_${Version}_windows_x64.msi"
$ServiceName = 'otelcol-contrib'
$InstallDir = Join-Path $env:ProgramFiles 'OpenTelemetry Collector'
$QueueDir = Join-Path $env:ProgramData 'OpenTelemetry Collector\queue'

function Say([string]$Text) { Write-Host "==> $Text" }
function Stop-Install([string]$Text) { Write-Host "error: $Text" -ForegroundColor Red; exit 1 }

# Check what was typed before anything is installed.
if ($Upgrade) {
  if ($Name -or $Token) { Stop-Install '-Upgrade takes no -Name and no -Token: it uses the key that is installed' }
} else {
  if (-not $Name) { Stop-Install '-Name is required' }
  if (-not $Token) { Stop-Install '-Token is required' }
  if ($Name -notmatch '^[a-z0-9][a-z0-9-]{0,62}$') { Stop-Install '-Name may only hold lowercase letters, digits and hyphen' }
  if ($Token -notmatch '^mse_[0-9]+_[A-Za-z0-9_-]+$') { Stop-Install '-Token does not look like an enrollment token (mse_...)' }
}
$Url = $Url.TrimEnd('/')
if ($Url -notmatch '^https?://[A-Za-z0-9.:_~/-]+$') { Stop-Install '-Url must be an address such as https://logs.example.com' }

# -Upgrade: an installed collector keeps its key; it gets the current configuration
if ($Upgrade) {
  $reg = "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName"
  $key = ''
  $cur = (Get-ItemProperty -Path $reg -Name Environment -ErrorAction SilentlyContinue).Environment
  if ($cur) { $line = @($cur | Where-Object { $_ -like 'MONISHIELD_COLLECTOR_KEY=*' }) | Select-Object -First 1; if ($line) { $key = $line.Substring('MONISHIELD_COLLECTOR_KEY='.Length) } }
  if ($key -notmatch '^msk_[0-9]+_[A-Za-z0-9_-]+$') { Stop-Install "no collector key is installed in the Environment value of the $ServiceName service. Install the collector first: install.ps1 -Name <name> -Token <token>" }
  Say "Upgrading the collector in place: receiver $Url, key from the $ServiceName service"
  if ($DryRun) {
    Say "[dry-run] would GET $Url/api/collector/config with the installed key as a Bearer token"
    Say "[dry-run] would check it with otelcol-contrib validate, then write $InstallDir\config.yaml"
    Say "[dry-run] would restart the $ServiceName service and show its status"
    exit 0
  }
  $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
  if (-not $admin) { Stop-Install 'run this script in a PowerShell window opened as Administrator' }
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  $exe = Join-Path $InstallDir 'otelcol-contrib.exe'
  if (-not (Test-Path $exe)) { Stop-Install "$exe was not found: install the collector first" }
  Say 'Fetching the current configuration'
  try { $r = Invoke-WebRequest -UseBasicParsing -Headers @{ Authorization = "Bearer $key" } -Uri "$Url/api/collector/config" }
  catch {
    $code = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
    if ($code -gt 0) { Stop-Install "the server refused the key (HTTP $code): it may be revoked or replaced. Replace the key on the Collectors page." }
    Stop-Install "could not reach ${Url}: $($_.Exception.Message)"
  }
  $tmp = Join-Path ([IO.Path]::GetTempPath()) ('monishield-' + [Guid]::NewGuid().ToString('N') + '.yaml')
  try {
    [IO.File]::WriteAllText($tmp, [string]$r.Content, (New-Object Text.UTF8Encoding($false)))
    Say 'Checking the configuration'
    $env:MONISHIELD_COLLECTOR_KEY = $key
    try { & $exe validate "--config=$tmp"; if ($LASTEXITCODE -ne 0) { Stop-Install 'the new configuration did not pass otelcol-contrib validate; nothing was changed' } }
    finally { Remove-Item Env:\MONISHIELD_COLLECTOR_KEY -ErrorAction SilentlyContinue }
    Say "Writing $InstallDir\config.yaml"
    Copy-Item -Path $tmp -Destination (Join-Path $InstallDir 'config.yaml') -Force
  } finally { Remove-Item -Force -Path $tmp -ErrorAction SilentlyContinue }
  Say "Restarting the $ServiceName service"
  Restart-Service -Name $ServiceName
  Start-Sleep -Seconds 3
  Get-Service -Name $ServiceName | Format-List Name, Status, StartType
  if ((Get-Service -Name $ServiceName).Status -ne 'Running') { Stop-Install "the $ServiceName service is not running; see the Windows Event Log (Application)" }
  Say 'Done. The collector now runs the current configuration.'
  exit 0
}

Say "MoniShield collector '$Name': otelcol-contrib $Version (windows x64), receiver $Url"
if ($DryRun) {
  Say "[dry-run] would download $Release/$Asset"
  Say "[dry-run] would download $Release/$Asset.sha256 and stop if the SHA-256 differs"
  Say '[dry-run] would install the MSI silently'
  Say "[dry-run] would POST the token to $Url/api/collector/enroll with X-Requested-With: monishield-collector"
  Say "[dry-run] would write $InstallDir\config.yaml from the answer"
  Say "[dry-run] would store the key in the Environment value of the $ServiceName service (administrators and system only)"
  Say "[dry-run] would create $QueueDir, validate the configuration, restart the $ServiceName service and show its status"
  exit 0
}

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { Stop-Install 'run this script in a PowerShell window opened as Administrator' }
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Work = Join-Path ([IO.Path]::GetTempPath()) ('monishield-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Work | Out-Null
try {
  Say "Downloading $Asset"
  $msi = Join-Path $Work $Asset
  Invoke-WebRequest -UseBasicParsing -Uri "$Release/$Asset" -OutFile $msi
  $sum = (Invoke-WebRequest -UseBasicParsing -Uri "$Release/$Asset.sha256").Content
  if ($sum -is [byte[]]) { $sum = [Text.Encoding]::ASCII.GetString($sum) }
  $want = ($sum.Trim() -split '\s+')[0].ToLower()
  if ($want -notmatch '^[0-9a-f]{64}$') { Stop-Install 'the checksum file does not hold a SHA-256' }
  $have = (Get-FileHash -Algorithm SHA256 -Path $msi).Hash.ToLower()
  if ($have -ne $want) { Stop-Install "checksum mismatch for ${Asset}: expected $want, got $have; nothing was installed" }
  Say 'Checksum matches'

  Say 'Installing the MSI'
  $p = Start-Process -FilePath msiexec.exe -ArgumentList @('/i', "`"$msi`"", '/qn', '/norestart') -Wait -PassThru
  if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) { Stop-Install "msiexec failed with code $($p.ExitCode)" }
  $exe = Join-Path $InstallDir 'otelcol-contrib.exe'
  if (-not (Test-Path $exe)) { Stop-Install "$exe was not installed" }

  Say 'Enrolling this collector'
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Method Post -Uri "$Url/api/collector/enroll?format=install" `
      -Headers @{ 'X-Requested-With' = 'monishield-collector' } -ContentType 'application/json' `
      -Body (@{ token = $Token } | ConvertTo-Json -Compress)
  } catch {
    $code = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
    if ($code -gt 0) { Stop-Install "enrollment was refused (HTTP $code): the token is wrong, used or expired. Make a new one on the Collectors page." }
    Stop-Install "could not reach ${Url}: $($_.Exception.Message)"
  }
  $key = [string]($r.Headers['X-Collector-Key'] | Select-Object -First 1)
  $platform = [string]($r.Headers['X-Collector-Platform'] | Select-Object -First 1)
  $got = [string]($r.Headers['X-Collector-Name'] | Select-Object -First 1)
  if ($got -ne $Name) { Stop-Install "the token belongs to the collector '$got', not '$Name'. Its key was issued: replace the key on the Collectors page." }
  if ($platform -ne 'windows') { Stop-Install "this collector is registered for $platform, not for Windows. Replace its key on the Collectors page and follow the steps for $platform." }
  if ($key -notmatch '^msk_[0-9]+_[A-Za-z0-9_-]+$') { Stop-Install 'the server did not answer with a collector key' }

  Say 'Writing the configuration and the key'
  $config = Join-Path $InstallDir 'config.yaml'
  [IO.File]::WriteAllText($config, [string]$r.Content, (New-Object Text.UTF8Encoding($false)))
  New-Item -ItemType Directory -Force -Path $QueueDir | Out-Null
  & icacls.exe $QueueDir /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
  $reg = "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName"
  $env_ = @()
  $old = (Get-ItemProperty -Path $reg -Name Environment -ErrorAction SilentlyContinue).Environment
  if ($old) { $env_ = @($old | Where-Object { $_ -notlike 'MONISHIELD_COLLECTOR_KEY=*' }) }
  $env_ += "MONISHIELD_COLLECTOR_KEY=$key"
  New-ItemProperty -Path $reg -Name Environment -PropertyType MultiString -Value ([string[]]$env_) -Force | Out-Null

  Say 'Checking the configuration'
  $env:MONISHIELD_COLLECTOR_KEY = $key
  try { & $exe validate "--config=$config"; if ($LASTEXITCODE -ne 0) { Stop-Install 'the configuration did not pass otelcol-contrib validate' } }
  finally { Remove-Item Env:\MONISHIELD_COLLECTOR_KEY -ErrorAction SilentlyContinue }

  Say "Starting the $ServiceName service"
  Set-Service -Name $ServiceName -StartupType Automatic
  Restart-Service -Name $ServiceName
  Start-Sleep -Seconds 3
  Get-Service -Name $ServiceName | Format-List Name, Status, StartType
  if ((Get-Service -Name $ServiceName).Status -ne 'Running') { Stop-Install "the $ServiceName service is not running; see the Windows Event Log (Application)" }
  Say 'Done. The collector sends its first lines within a minute; check the Collectors page.'
} finally {
  Remove-Item -Recurse -Force -Path $Work -ErrorAction SilentlyContinue
}
