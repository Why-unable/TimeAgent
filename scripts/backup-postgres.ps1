[CmdletBinding()]
param(
    [string]$OutputDirectory = "backups"
)

$ErrorActionPreference = "Stop"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$resolvedDirectory = Join-Path (Get-Location) $OutputDirectory
$archivePath = Join-Path $resolvedDirectory "time-agent-$timestamp.dump"
$temporaryArchive = "/tmp/time-agent-backup-$timestamp.dump"

New-Item -ItemType Directory -Force -Path $resolvedDirectory | Out-Null

# PostgreSQL custom format preserves schema and data while remaining suitable
# for pg_restore. Keep binary data inside Docker and copy it with `docker cp`:
# Windows PowerShell 5 does not support Set-Content -AsByteStream.
$containerOutput = & docker compose ps -q postgres
if ($LASTEXITCODE -ne 0) {
    throw "Could not query the PostgreSQL Compose container (exit code $LASTEXITCODE)."
}
$containerId = ([string]$containerOutput).Trim()
if ([string]::IsNullOrWhiteSpace($containerId)) {
    throw "PostgreSQL container is not running. Start the Compose stack before creating a backup."
}

try {
    & docker compose exec -T postgres sh -c "pg_dump -U `"`$POSTGRES_USER`" -d `"`$POSTGRES_DB`" -Fc > $temporaryArchive"
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL dump command failed with exit code $LASTEXITCODE."
    }

    & docker cp "${containerId}:$temporaryArchive" $archivePath
    if ($LASTEXITCODE -ne 0) {
        throw "Could not copy the PostgreSQL archive from the container."
    }
}
finally {
    & docker compose exec -T postgres sh -c "rm -f $temporaryArchive" 2>$null
}

if ((Get-Item $archivePath).Length -eq 0) {
    Remove-Item -LiteralPath $archivePath
    throw "Backup failed: generated archive is empty."
}

Write-Host "PostgreSQL backup created: $archivePath"
