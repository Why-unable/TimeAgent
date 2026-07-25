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

# Restore is deliberately opt-in and runs only against the Compose PostgreSQL
# container. --clean replaces objects included in the selected archive.
Get-Content -LiteralPath $resolvedArchive -AsByteStream -Raw |
    docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner'

Write-Host "PostgreSQL restore completed from: $resolvedArchive"
