# Prevent this laptop from sleeping or turning off its display while the
# backend + cloudflared are serving production traffic. Run in a PowerShell
# that stays open alongside start.sh and cloudflared.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File deploy/keep_awake.ps1
#
# Ctrl+C to release the assertion.

$signature = @'
[DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
public static extern uint SetThreadExecutionState(uint esFlags);
'@
$ES = Add-Type -MemberDefinition $signature -Name 'Kernel32Power' `
    -Namespace 'GeyamKeepAwake' -PassThru

# ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
$null = $ES::SetThreadExecutionState(0x80000000 -bor 0x00000001 -bor 0x00000002)
Write-Host "GEYAM keep-awake active. Ctrl+C to exit."

try {
    while ($true) { Start-Sleep -Seconds 60 }
}
finally {
    # ES_CONTINUOUS alone re-allows sleep
    $null = $ES::SetThreadExecutionState(0x80000000)
    Write-Host "Released. System can sleep again."
}
