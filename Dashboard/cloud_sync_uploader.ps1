$ErrorActionPreference = 'Stop'

$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$configPath = Join-Path $rootDir 'quantgod_cloud_sync.enabled.json'
$dataPath = Join-Path $rootDir 'QuantGod_Dashboard.json'
$pollSeconds = 10
$lastSignature = ''

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Write-Output "[QuantGod Cloud Sync] [$timestamp] $Message"
}

function Get-JsonObject {
    param([string]$Path)
    $raw = Get-Content $Path -Raw
    if ($raw.Length -gt 0 -and [int][char]$raw[0] -eq 0xFEFF) {
        $raw = $raw.Substring(1)
    }
    return $raw | ConvertFrom-Json
}

Write-Log 'Uploader started.'

while ($true) {
    try {
        if (-not (Test-Path $configPath)) {
            Write-Log 'Missing quantgod_cloud_sync.enabled.json, uploader idle.'
            Start-Sleep -Seconds $pollSeconds
            continue
        }

        if (-not (Test-Path $dataPath)) {
            Write-Log 'Waiting for QuantGod_Dashboard.json...'
            Start-Sleep -Seconds $pollSeconds
            continue
        }

        $config = Get-JsonObject -Path $configPath
        if ([string]::IsNullOrWhiteSpace($config.endpoint)) {
            Write-Log 'Config missing endpoint, uploader idle.'
            Start-Sleep -Seconds $pollSeconds
            continue
        }

        $file = Get-Item $dataPath
        $signature = '{0}:{1}' -f $file.LastWriteTimeUtc.Ticks, $file.Length
        if ($signature -eq $lastSignature) {
            Start-Sleep -Seconds $pollSeconds
            continue
        }

        $payload = Get-JsonObject -Path $dataPath
        $nowText = Get-Date -Format 'yyyy.MM.dd HH:mm:ss'
        $payload | Add-Member -NotePropertyName cloudSync -NotePropertyValue ([pscustomobject]@{
            enabled = $true
            configured = $true
            endpoint = [string]$config.endpoint
            intervalSeconds = $pollSeconds
            lastAttemptLocal = $nowText
            lastSuccessLocal = $nowText
            status = 'SYNCED'
            httpCode = 200
            message = 'PowerShell uploader active'
        }) -Force

        $headers = @{
            'X-QuantGod-Source' = 'powershell-uploader'
        }
        if (-not [string]::IsNullOrWhiteSpace($config.token)) {
            $headers['Authorization'] = 'Bearer ' + [string]$config.token
        }

        $body = $payload | ConvertTo-Json -Depth 12 -Compress
        $response = Invoke-WebRequest -Uri $config.endpoint -Method POST -Headers $headers -ContentType 'application/json' -Body $body -UseBasicParsing
        $lastSignature = $signature
        Write-Log ("Synced OK -> {0} ({1})" -f $config.endpoint, $response.StatusCode)
    }
    catch {
        Write-Log ('Sync failed: ' + $_.Exception.Message)
    }

    Start-Sleep -Seconds $pollSeconds
}
