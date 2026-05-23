# setup_startup_task.ps1
# Registers ArthaOS as a Windows Task Scheduler task that runs at user logon.
# Run once: right-click -> "Run with PowerShell", or:
#   powershell -ExecutionPolicy Bypass -File setup_startup_task.ps1

# Self-elevate if not already running as admin
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $args = '-ExecutionPolicy Bypass -File "' + $MyInvocation.MyCommand.Definition + '"'
    Start-Process powershell -Verb RunAs -ArgumentList $args
    exit
}

$TaskName    = 'ArthaOS'
$ProjectDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$PythonExe   = (Get-Command python -ErrorAction SilentlyContinue).Source

if (-not $PythonExe) {
    Write-Error 'Python not found in PATH. Install Python 3.10+ and retry.'
    Read-Host 'Press Enter to exit'
    exit 1
}

$StartScript = Join-Path $ProjectDir 'start.py'
if (-not (Test-Path $StartScript)) {
    Write-Error "start.py not found at: $StartScript"
    Read-Host 'Press Enter to exit'
    exit 1
}

# Remove existing task if present
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed existing '$TaskName' task."
}

$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument ('"{0}"' -f $StartScript) `
    -WorkingDirectory $ProjectDir

$Trigger  = New-ScheduledTaskTrigger -AtLogon -User $env:USERNAME

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable

$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description 'ArthaOS personal finance AI backend - starts at user logon.' | Out-Null

Write-Host ''
Write-Host "Task '$TaskName' registered successfully."
Write-Host "  Python : $PythonExe"
Write-Host "  Script : $StartScript"
Write-Host "  Trigger: At logon for $env:USERNAME"
Write-Host ''
Write-Host 'To run now without rebooting:'
Write-Host "  Start-ScheduledTask -TaskName $TaskName"
Write-Host ''
Write-Host 'To remove the task:'
Write-Host "  Unregister-ScheduledTask -TaskName $TaskName -Confirm:'$'false"
Write-Host ''
Read-Host 'Press Enter to exit'
