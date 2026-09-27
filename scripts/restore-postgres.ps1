[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$ArchivePath,
    [switch]$ConfirmRestore
)

$ErrorActionPreference = "Stop"

if (-not $ConfirmRestore) {
    throw "Restore is destructive. Re-run with -ConfirmRestore after verifying the archive and target database."
}

$resolvedArchive = (Resolve-Path -LiteralPath $ArchivePath).Path
$temporaryArchive = "/tmp/time-agent-restore-$([guid]::NewGuid().ToString('N')).dump"

$containerOutput = & docker compose ps -q postgres
if ($LASTEXITCODE -ne 0) {
    throw "Could not query the PostgreSQL Compose container (exit code $LASTEXITCODE)."
}
$containerId = ([string]$containerOutput).Trim()
if ([string]::IsNullOrWhiteSpace($containerId)) {
    throw "PostgreSQL container is not running. Start the Compose stack before restoring a backup."
}

# Restore is deliberately opt-in and runs only against the Compose PostgreSQL
# container. Copy the binary archive with Docker rather than piping it through
# PowerShell, which keeps this script compatible with Windows PowerShell 5.
try {
    & docker cp $resolvedArchive "${containerId}:$temporaryArchive"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not copy the PostgreSQL archive into the container."
    }

    & docker compose exec -T postgres sh -c "pg_restore -U `"`$POSTGRES_USER`" -d `"`$POSTGRES_DB`" --clean --if-exists --no-owner $temporaryArchive"
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL restore command failed with exit code $LASTEXITCODE."
    }
}
finally {
    & docker compose exec -T postgres sh -c "rm -f $temporaryArchive" 2>$null
}

Write-Host "PostgreSQL restore completed from: $resolvedArchive"
