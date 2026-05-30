# ArthaOS deploy sync — Windows PowerShell
# Usage: .\deploy\sync.ps1 -ServerIP "<your-gcp-ip>" -KeyFile "C:\path\to\key.pem"
#
# Requires OpenSSH (built into Windows 10/11) and rsync via WSL or Git Bash.
# If you don't have rsync, use the scp fallback below.
#
# Syncs both ArthaOS backend/frontend AND the REA WhatsApp agent.

param(
    [Parameter(Mandatory=$true)]
    [string]$ServerIP,

    [Parameter(Mandatory=$true)]
    [string]$KeyFile,

    [string]$RemoteUser = "ubuntu",
    [string]$RemotePath = "~/arthaos"
)

$LOCAL     = "c:\Users\KshitijModi\Downloads\Remote Engineering Agents\workspace\ArthaOS"
$LOCAL_REA = "c:\Users\KshitijModi\Downloads\Remote Engineering Agents"
$SSH       = "ssh -i `"$KeyFile`" -o StrictHostKeyChecking=no ${RemoteUser}@${ServerIP}"

Write-Host "=== Syncing ArthaOS to $ServerIP ===" -ForegroundColor Cyan

# ── 1. Code (exclude secrets, venv, node_modules, __pycache__, DB) ──────────
Write-Host "[1/5] Syncing ArthaOS backend + frontend..."
$rsyncExcludes = @(
    "--exclude=.venv",
    "--exclude=node_modules",
    "--exclude=__pycache__",
    "--exclude=*.pyc",
    "--exclude=data/arthaos.db",
    "--exclude=.wwebjs_auth",
    "--exclude=.wwebjs_cache",
    "--exclude=backend/teller/certificate.pem",
    "--exclude=backend/teller/private_key.pem",
    "--exclude=gmail_token.json",
    "--exclude=gmail_credentials.json",
    "--exclude=.env",
    "--exclude=frontend/.env.local",
    "--exclude=deploy/sync.ps1"
)

# REA-specific excludes
$rsyncExcludesREA = @(
    "--exclude=node_modules",
    "--exclude=.wwebjs_auth",
    "--exclude=.wwebjs_cache",
    "--exclude=checkpoints",
    "--exclude=__pycache__",
    "--exclude=.env",
    "--exclude=workspace"
)

# Try rsync via WSL
$wslAvailable = (Get-Command wsl -ErrorAction SilentlyContinue) -ne $null
if ($wslAvailable) {
    $wslLocal    = (wsl wslpath -u $LOCAL.Replace("\", "/")).Trim()
    $wslLocalREA = (wsl wslpath -u $LOCAL_REA.Replace("\", "/")).Trim()
    $wslKey      = (wsl wslpath -u $KeyFile.Replace("\", "/")).Trim()
    $rsyncCmd    = "rsync -avz --delete $($rsyncExcludes -join ' ') -e 'ssh -i $wslKey -o StrictHostKeyChecking=no' '$wslLocal/' '${RemoteUser}@${ServerIP}:${RemotePath}/'"
    wsl bash -c $rsyncCmd
} else {
    Write-Warning "WSL not found. Using scp (slower, no delete). Install WSL + rsync for better syncs."
    Write-Warning "Run: scp -r -i '$KeyFile' '$LOCAL\backend' '${RemoteUser}@${ServerIP}:${RemotePath}/'"
    Write-Warning "     scp -r -i '$KeyFile' '$LOCAL\frontend' '${RemoteUser}@${ServerIP}:${RemotePath}/'"
}

# ── 2. REA (WhatsApp agent) ──────────────────────────────────────────────────
Write-Host "[2/5] Syncing REA WhatsApp agent to $RemotePath/REA ..."
ssh -i "$KeyFile" -o StrictHostKeyChecking=no "${RemoteUser}@${ServerIP}" "mkdir -p ${RemotePath}/REA"
if ($wslAvailable) {
    $rsyncCmdREA = "rsync -avz --delete $($rsyncExcludesREA -join ' ') -e 'ssh -i $wslKey -o StrictHostKeyChecking=no' '$wslLocalREA/' '${RemoteUser}@${ServerIP}:${RemotePath}/REA/'"
    wsl bash -c $rsyncCmdREA
} else {
    Write-Warning "Sync REA manually: scp -r -i '$KeyFile' '$LOCAL_REA\src' '${RemoteUser}@${ServerIP}:${RemotePath}/REA/'"
    Write-Warning "                   scp -r -i '$KeyFile' '$LOCAL_REA\index.js' '${RemoteUser}@${ServerIP}:${RemotePath}/REA/'"
}

# ── 3. Secrets (sent separately, never committed to git) ────────────────────
Write-Host "[3/5] Uploading ArthaOS secrets..."
scp -i "$KeyFile" "$LOCAL\.env"                                   "${RemoteUser}@${ServerIP}:${RemotePath}/.env"
scp -i "$KeyFile" "$LOCAL\frontend\.env.local"                    "${RemoteUser}@${ServerIP}:${RemotePath}/frontend/.env.local"
scp -i "$KeyFile" "$LOCAL\gmail_token.json"                       "${RemoteUser}@${ServerIP}:${RemotePath}/gmail_token.json"
scp -i "$KeyFile" "$LOCAL\gmail_credentials.json"                 "${RemoteUser}@${ServerIP}:${RemotePath}/gmail_credentials.json"
scp -i "$KeyFile" "$LOCAL\backend\teller\certificate.pem"         "${RemoteUser}@${ServerIP}:${RemotePath}/backend/teller/certificate.pem"
scp -i "$KeyFile" "$LOCAL\backend\teller\private_key.pem"         "${RemoteUser}@${ServerIP}:${RemotePath}/backend/teller/private_key.pem"

Write-Host "[3/5] Uploading REA secrets..."
if (Test-Path "$LOCAL_REA\.env") {
    scp -i "$KeyFile" "$LOCAL_REA\.env" "${RemoteUser}@${ServerIP}:${RemotePath}/REA/.env"
}

# ── 4. Database (only if you want to carry over existing data) ───────────────
Write-Host "[4/5] Uploading SQLite DB..."
$dbPath = "$LOCAL\data\arthaos.db"
if (Test-Path $dbPath) {
    scp -i "$KeyFile" "$dbPath" "${RemoteUser}@${ServerIP}:${RemotePath}/data/arthaos.db"
} else {
    Write-Host "  No local DB found — server will start fresh."
}

# ── 5. Update server environment and restart PM2 ────────────────────────────
Write-Host "[5/5] Restarting services on server..."
$remoteCmd = @"
set -e
source ~/arthaos/.venv/bin/activate
cd ~/arthaos
pip install -q -r requirements.txt
cd frontend && npm install --silent && npm run build
cd ../REA && npm install --silent
cd ..
pm2 restart all || pm2 start ~/arthaos/deploy/ecosystem.linux.config.js
pm2 save
echo 'Deploy complete'
"@
ssh -i "$KeyFile" -o StrictHostKeyChecking=no "${RemoteUser}@${ServerIP}" "$remoteCmd"

Write-Host "=== Done! Dashboard: http://$ServerIP ===" -ForegroundColor Green
Write-Host "    Backend API: http://$ServerIP/api/" -ForegroundColor Green
Write-Host "    REA alert port: 8001 (must be open in GCP firewall)" -ForegroundColor Yellow
