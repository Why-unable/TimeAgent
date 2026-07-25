[CmdletBinding()]
param(
    [string]$OutputDirectory = "backups"
)

$ErrorActionPreference = "Stop"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$resolvedDirectory = Join-Path (Get-Location) $OutputDirectory
$archivePath = Join-Path $resolvedDirectory "time-agent-$timestamp.dump"

New-Item -ItemType Directory -Force -Path $resolvedDirectory | Out-Null

# PostgreSQL custom format preserves schema and data while remaining suitable
# for pg_restore. The password is read by Docker from .env and never printed.
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' |
    Set-Content -AsByteStream -Path $archivePath

if ((Get-Item $archivePath).Length -eq 0) {
    Remove-Item -LiteralPath $archivePath
    throw "Backup failed: generated archive is empty."
}

Write-Host "PostgreSQL backup created: $archivePath"
