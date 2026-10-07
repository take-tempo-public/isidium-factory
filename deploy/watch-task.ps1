<#
The PR watcher's timer (card 30): one Windows scheduled task per tenant, run on the host, that starts one
`isidium-factory watch --once` pass every 15 minutes and logs it. Not a container and not a service supervisor: the
store's restart policy is no and the VPN breaks WSL DNS, so each pass is a process that does its work and exits.

  watch-task.ps1 -Tenant T -Checkout C -Deploy D     register the task, or replace it if it is there
  watch-task.ps1 -Tenant T -Remove                   unregister it; the log stays

`-Pass` and `-Exe` are the task's own action: the registered task runs this script again with them, and nobody else
passes them. No parameter has a default.
#>
[CmdletBinding(DefaultParameterSetName = 'Register')]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$')]
    [string]$Tenant,
    [Parameter(Mandatory = $true, ParameterSetName = 'Register')]
    [Parameter(Mandatory = $true, ParameterSetName = 'Pass')]
    [string]$Checkout,
    [Parameter(Mandatory = $true, ParameterSetName = 'Register')]
    [Parameter(Mandatory = $true, ParameterSetName = 'Pass')]
    [string]$Deploy,
    [Parameter(Mandatory = $true, ParameterSetName = 'Remove')]
    [switch]$Remove,
    [Parameter(Mandatory = $true, ParameterSetName = 'Pass')]
    [switch]$Pass,
    [Parameter(Mandatory = $true, ParameterSetName = 'Pass')]
    [string]$Exe
)

$TaskName = "isidium-watch-$Tenant"

# The cadence is the owner's ruling of 2026-10-04 ('Every 15 minutes'), not this script's to move.
$CadenceMinutes = 15

# The execution limit: a pass that hangs is ended by the scheduler rather than left to hold the next one off.
# It must be longer than a close's lease (CLOSE_LEASE_S in cli.py, one hour) plus a fixup's bound (_fixup_bound: the
# signed [executor].wall_clock_s per attempt times container.ATTEMPTS, 3600 x 2 at tenant #0), which is three hours
# together; four hours clears that. A pass that outlived its leases would act without them. If the signed
# wall_clock_s is raised, raise this: the test recomputes the bound from the tenant's config and goes red.
$LimitHours = 4

if ($Pass) {
    $env:ISIDIUM_DEPLOY = $Deploy
    $env:PYTHONIOENCODING = 'utf-8'
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $ErrorActionPreference = 'Continue'
    $log = Join-Path $Deploy "$Tenant\factory\watch-task.log"
    $stamp = (Get-Date).ToUniversalTime().ToString('o')
    Add-Content -Path $log -Value "START $stamp" -Encoding utf8
    & $Exe watch --once --tenant $Tenant --checkout $Checkout 2>&1 | ForEach-Object { "$_" } | Add-Content -Path $log -Encoding utf8
    $code = $LASTEXITCODE
    if ($null -eq $code) { $code = 1 }
    $stamp = (Get-Date).ToUniversalTime().ToString('o')
    Add-Content -Path $log -Value "EXIT $code $stamp" -Encoding utf8
    exit $code
}

if ($Remove) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $existing) {
        Write-Output "no task $TaskName"
        exit 0
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "removed $TaskName"
    exit 0
}

$found = Get-Command isidium-factory -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $found) {
    throw 'isidium-factory is not on PATH: install the factory first'
}
$exePath = $found.Source
$scriptPath = $MyInvocation.MyCommand.Path

$argLine = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -Pass -Tenant "{1}" -Checkout "{2}" -Deploy "{3}" -Exe "{4}"' -f $scriptPath, $Tenant, $Checkout, $Deploy, $exePath
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argLine
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes $CadenceMinutes)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours $LimitHours) -StartWhenAvailable
$me = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Output "registered $TaskName: every $CadenceMinutes minutes, one pass at a time, limit $LimitHours hours"
