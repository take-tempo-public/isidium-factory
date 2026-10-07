<#
The PR watcher's timer (card 30): one Windows scheduled task per tenant, run on the host, that starts one
`isidium-factory watch --once` pass every 15 minutes and logs it. Not a container and not a service supervisor: the
store's restart policy is no and the VPN breaks WSL DNS, so each pass is a process that does its work and exits.

  watch-task.ps1 -Tenant T -Checkout C -Deploy D     register the task, or replace it if it is there
  watch-task.ps1 -Tenant T -Remove                   unregister it; the log stays

`-Checkout` and `-Deploy` may be given relative, but each must exist: they are resolved to absolute paths, and so is the
executable, before anything is registered; a missing one is refused and registers nothing. The task starts in the
checkout. `-Tenant` is matched case-sensitively, as the factory's own tenant grammar is. The task starts on battery and is
not stopped when the host goes to battery. Registering or removing stops on the first error and prints no success line
after one.

`-Pass` and `-Exe` are the task's own action: the registered task runs this script again with them, and nobody else
passes them. No parameter has a default.
#>
[CmdletBinding(DefaultParameterSetName = 'Register')]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$', Options = 'None')]
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
# It is one value for every tenant registered on this host, so it must exceed each tenant's own bound: a close's lease
# (CLOSE_LEASE_S in cli.py, one hour) plus that tenant's fixup bound (_fixup_bound: its signed [executor].wall_clock_s
# per attempt times container.ATTEMPTS). Tenant #0 is the worked example: 3600 x 2 plus the lease is three hours, and
# four hours clears that. A pass that outlived its leases would act without them. A tenant whose wall_clock_s pushes
# its sum past this needs the limit raised: the test recomputes the bound from tenant #0's config and goes red.
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

# Past the pass, an error ends the script: -ErrorAction Stop on a cmdlet covers its non-terminating errors, and this
# covers the statement-terminating ones (CIM, parameter binding), so no success line below follows a failed call.
$ErrorActionPreference = 'Stop'

if ($Remove) {
    # Listed and filtered rather than looked up by name: a name lookup that finds nothing and a scheduler that fails both
    # raise, and telling them apart would mean reading the exception's text.
    $existing = @(Get-ScheduledTask -ErrorAction Stop | Where-Object { $_.TaskName -eq $TaskName })
    if ($existing.Count -eq 0) {
        Write-Output "no task $TaskName"
        exit 0
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    Write-Output "removed $TaskName"
    exit 0
}

$found = Get-Command isidium-factory -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $found) {
    throw 'isidium-factory is not on PATH: install the factory first'
}
if (-not (Test-Path -LiteralPath $Checkout -PathType Container)) {
    throw "-Checkout is not a directory: $Checkout"
}
if (-not (Test-Path -LiteralPath $Deploy -PathType Container)) {
    throw "-Deploy is not a directory: $Deploy"
}
if (-not (Test-Path -LiteralPath $found.Source -PathType Leaf)) {
    throw "the executable is not a file: $($found.Source)"
}
$checkoutPath = (Resolve-Path -LiteralPath $Checkout).ProviderPath
$deployPath = (Resolve-Path -LiteralPath $Deploy).ProviderPath
$exePath = (Resolve-Path -LiteralPath $found.Source).ProviderPath
$scriptPath = $MyInvocation.MyCommand.Path

$argLine = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -Pass -Tenant "{1}" -Checkout "{2}" -Deploy "{3}" -Exe "{4}"' -f $scriptPath, $Tenant, $checkoutPath, $deployPath, $exePath
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argLine -WorkingDirectory $checkoutPath -ErrorAction Stop
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes $CadenceMinutes) -ErrorAction Stop
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours $LimitHours) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ErrorAction Stop
$me = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive -ErrorAction Stop

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force -ErrorAction Stop | Out-Null
Write-Output "registered ${TaskName}: every $CadenceMinutes minutes, one pass at a time, limit $LimitHours hours"
