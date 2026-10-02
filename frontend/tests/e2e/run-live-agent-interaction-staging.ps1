$ErrorActionPreference = "Stop"

$credentialPath = Join-Path $env:LOCALAPPDATA 'TimeAgent\agent-ux-v3-staging\staging-e2e.credential.xml'
if (-not (Test-Path -LiteralPath $credentialPath -PathType Leaf)) {
    throw 'Local V3 staging E2E credentials are not configured.'
}

$credential = Import-Clixml -LiteralPath $credentialPath
if ($credential -isnot [System.Management.Automation.PSCredential]) {
    throw 'The saved local V3 staging credential file is invalid.'
}

$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($credential.Password)
try {
    $env:TIME_AGENT_E2E_EMAIL = $credential.UserName
    $env:TIME_AGENT_E2E_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    $env:TIME_AGENT_E2E_ENABLE_INTERACTIONS = '1'
    $env:TIME_AGENT_E2E_BASE_URL = 'http://127.0.0.1:7081'
    Push-Location (Join-Path $PSScriptRoot '..\..')
    try {
        npm exec -- playwright test --config=playwright.live-agent-staging.config.ts
        if ($LASTEXITCODE -ne 0) {
            throw "Local V3 Agent interaction acceptance failed with exit code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    $credential.Password.Dispose()
    Remove-Item Env:TIME_AGENT_E2E_EMAIL -ErrorAction SilentlyContinue
    Remove-Item Env:TIME_AGENT_E2E_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:TIME_AGENT_E2E_ENABLE_INTERACTIONS -ErrorAction SilentlyContinue
    Remove-Item Env:TIME_AGENT_E2E_BASE_URL -ErrorAction SilentlyContinue
}

Write-Output 'Local V3 Agent interaction acceptance passed. Credential environment variables were cleared.'
