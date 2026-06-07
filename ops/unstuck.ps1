# GEYAM cheatcode — motivation reset by shipping the current frontend live.
#
# When you're stuck halfway and demotivated, run:
#     pwsh .\ops\unstuck.ps1
# (or `powershell .\ops\unstuck.ps1` if pwsh isn't installed)
#
# What it does (~2 min build + 5 min manual upload):
#   1. Pulse-checks api.geyam.com so you know the backend is alive
#   2. Builds Flutter Web with prod API URL baked in
#   3. Zips build/web → C:\tmp\geyam-web.zip
#   4. Opens Hostinger File Manager + geyam.com in your browser
#   5. Prints the 4 manual upload steps
#
# Why this works: the bottleneck of motivation is "I can't see progress." This
# script makes "I shipped something visible to the public internet" a 7-minute
# action. Use it as a reset button — not as your main workflow.

$ErrorActionPreference = "Stop"
$start = Get-Date

Write-Host ""
Write-Host "=== GEYAM unstuck cheatcode ===" -ForegroundColor Magenta
Write-Host ""

# 1. Pulse-check api.geyam.com — sometimes "it's all already fine" is the reset
Write-Host "[1/4] Pulsing api.geyam.com/healthz..." -ForegroundColor Cyan
try {
    $h = Invoke-RestMethod -Uri https://api.geyam.com/healthz -TimeoutSec 10
    $db = $h.checks.db.ok
    $redis = $h.checks.redis.ok
    $disk = $h.checks.disk.ok
    Write-Host "      OK — db=$db redis=$redis disk=$disk ($($h.checks.disk.free_pct)% free)" -ForegroundColor Green
} catch {
    Write-Host "      WARN: $_" -ForegroundColor Yellow
    Write-Host "      The frontend will still build, but POS calls will fail until the API recovers."
}

# 2. Build Flutter Web with prod API URL
$projectDir = "C:\Programming_Local\geyam\geyam\frontend\geyam_pos"
Write-Host "[2/4] Building Flutter Web (release, API_BASE_URL=https://api.geyam.com)..." -ForegroundColor Cyan
Push-Location $projectDir
try {
    flutter build web --release --dart-define=API_BASE_URL=https://api.geyam.com
    if ($LASTEXITCODE -ne 0) { throw "flutter build returned exit $LASTEXITCODE" }
} finally {
    Pop-Location
}
Write-Host "      OK — build at $projectDir\build\web\" -ForegroundColor Green

# 3. Zip for File Manager upload
if (-not (Test-Path C:\tmp)) { New-Item -ItemType Directory -Path C:\tmp | Out-Null }
$zip = "C:\tmp\geyam-web.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Write-Host "[3/4] Zipping build/web → $zip..." -ForegroundColor Cyan
Compress-Archive -Path "$projectDir\build\web\*" -DestinationPath $zip
$sizeMB = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host "      OK — $sizeMB MB ready" -ForegroundColor Green

# 4. Open Hostinger File Manager + geyam.com for the upload + admire steps
Write-Host "[4/4] Opening Hostinger File Manager + geyam.com in your browser..." -ForegroundColor Cyan
Start-Process "https://hpanel.hostinger.com/files/file-manager"
Start-Process "https://geyam.com"

$elapsed = [int]((Get-Date) - $start).TotalSeconds
Write-Host ""
Write-Host "Built in ${elapsed}s. Manual steps now:" -ForegroundColor Magenta
Write-Host "    a. In Hostinger File Manager, navigate into public_html/"
Write-Host "    b. Drag $zip into the panel to upload"
Write-Host "    c. Right-click the zip in the panel -> Extract -> destination: public_html/"
Write-Host "    d. Delete the zip after extraction (optional, keeps things tidy)"
Write-Host "    e. Hard-refresh https://geyam.com (Ctrl+Shift+R) — your work is live."
Write-Host ""
Write-Host "Go look at it. Take a breath. Then `git stash pop` (if you stashed) and continue." -ForegroundColor Magenta
Write-Host ""
