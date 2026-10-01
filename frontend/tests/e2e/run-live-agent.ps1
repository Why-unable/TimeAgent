$ErrorActionPreference = "Stop"

$credentialPath = Join-Path $env:LOCALAPPDATA "TimeAgent/live-agent-e2e.credential.xml"
if (-not (Test-Path -LiteralPath $credentialPath -PathType Leaf)) {
    throw "Live Agent credentials are not configured. Run configure-live-agent-credentials.ps1 once."
}

$credential = Import-Clixml -LiteralPath $credentialPath
if ($credential -isnot [System.Management.Automation.PSCredential]) {
    throw "The saved Live Agent credential file is invalid. Run configure-live-agent-credentials.ps1 again."
}

$email = $credential.UserName
$securePassword = $credential.Password
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
$testExitCode = 1
try {
    $env:TIME_AGENT_E2E_EMAIL = $email
    $env:TIME_AGENT_E2E_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    $env:TIME_AGENT_E2E_ENABLE_LIVE_AGENT = "1"
    $env:TIME_AGENT_E2E_BASE_URL = "https://steward.uresofa.me"

    $frontendRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
    Push-Location $frontendRoot
    try {
        npm exec -- playwright test --config=playwright.live-agent.config.ts
        $testExitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    $securePassword.Dispose()
    Remove-Item Env:TIME_AGENT_E2E_EMAIL -ErrorAction SilentlyContinue
    Remove-Item Env:TIME_AGENT_E2E_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:TIME_AGENT_E2E_ENABLE_LIVE_AGENT -ErrorAction SilentlyContinue
    Remove-Item Env:TIME_AGENT_E2E_BASE_URL -ErrorAction SilentlyContinue
}

if ($testExitCode -ne 0) {
    throw "Live Agent browser acceptance failed with exit code $testExitCode."
}

Write-Output "Live Agent browser acceptance passed. Credential environment variables were cleared."
