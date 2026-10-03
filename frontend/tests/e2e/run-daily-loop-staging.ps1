$ErrorActionPreference = "Stop"

$credentialPath = Join-Path $env:LOCALAPPDATA 'TimeAgent\agent-ux-v3-staging\staging-e2e.credential.xml'
if (-not (Test-Path -LiteralPath $credentialPath -PathType Leaf)) {
    throw 'Local V4 staging E2E credentials are not configured.'
}

$healthCode = & curl.exe --silent --show-error --output NUL --write-out '%{http_code}' 'http://127.0.0.1:7081/health/live'
if ($LASTEXITCODE -ne 0 -or $healthCode -ne '200') {
    throw 'Local staging health check did not return HTTP 200.'
}

$credential = Import-Clixml -LiteralPath $credentialPath
if ($credential -isnot [System.Management.Automation.PSCredential]) {
    throw 'The saved local staging credential file is invalid.'
}

$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($credential.Password)
try {
    $env:TIME_AGENT_E2E_EMAIL = $credential.UserName
    $env:TIME_AGENT_E2E_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    $env:TIME_AGENT_E2E_BASE_URL = 'http://127.0.0.1:7081'
    Push-Location (Join-Path $PSScriptRoot '..\..')
    try {
        npm exec -- playwright test --config=playwright.daily-loop-staging.config.ts
        if ($LASTEXITCODE -ne 0) {
            throw "Local V4 Daily Loop staging acceptance failed with exit code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    $credential.Password.Dispose()
    Remove-Item Env:TIME_AGENT_E2E_EMAIL -ErrorAction SilentlyContinue
    Remove-Item Env:TIME_AGENT_E2E_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:TIME_AGENT_E2E_BASE_URL -ErrorAction SilentlyContinue
}

Write-Output 'Local V4 Daily Loop staging acceptance passed. Credential environment variables were cleared.'
