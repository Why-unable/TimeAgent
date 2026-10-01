$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    throw "LOCALAPPDATA is unavailable; run this script from your Windows user session."
}

$email = Read-Host "Dedicated E2E test account email"
if ([string]::IsNullOrWhiteSpace($email)) {
    throw "An E2E test account email is required."
}

$securePassword = Read-Host "Dedicated E2E test account password (hidden input)" -AsSecureString
if ($securePassword.Length -eq 0) {
    throw "An E2E test account password is required."
}

$credentialDirectory = Join-Path $env:LOCALAPPDATA "TimeAgent"
$credentialPath = Join-Path $credentialDirectory "live-agent-e2e.credential.xml"
New-Item -ItemType Directory -Path $credentialDirectory -Force | Out-Null

$credential = [System.Management.Automation.PSCredential]::new($email.Trim(), $securePassword)
$credential | Export-Clixml -LiteralPath $credentialPath -Force

Write-Output "Live Agent E2E credentials saved with Windows DPAPI for this Windows user."
Write-Output "The encrypted credential file is outside the repository."
