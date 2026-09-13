<#
Registra una tarea programada de Windows para que el agente edge
(run_edge_agent.bat -> edge_agent.py) arranque solo al iniciar sesion en
esta laptop, y se reinicie solo si el proceso se cae.

No necesita ejecutarse como Administrador (AtLogOn del usuario actual
alcanza), pero si PowerShell te bloquea el script por la politica de
ejecucion, corre esto primero en esa misma ventana:
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

Uso, parado en la carpeta tesis-backend:
    powershell -ExecutionPolicy Bypass -File scripts\instalar_tarea_edge.ps1
#>

$ErrorActionPreference = "Stop"

$repoDir   = (Resolve-Path "$PSScriptRoot\..").Path
$pythonExe = Join-Path $repoDir ".venv\Scripts\python.exe"
$launcher  = Join-Path $repoDir "run_edge_agent.bat"

if (-not (Test-Path $pythonExe)) {
    Write-Error "No se encontro $pythonExe. Crea el venv (python -m venv .venv) e instala requirements.txt antes de instalar la tarea."
}
if (-not (Test-Path (Join-Path $repoDir "edge_config.json"))) {
    Write-Warning "No existe edge_config.json todavia. Copia edge_config.example.json, completalo, y luego corre este script de nuevo (o simplemente edita edge_config.json antes de que la tarea arranque)."
}

$taskName = "CrowdSense-EdgeAgent"

$action   = New-ScheduledTaskAction -Execute $launcher -WorkingDirectory $repoDir
$trigger  = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 0)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

Write-Host ""
Write-Host "Tarea '$taskName' registrada. Arrancara sola la proxima vez que inicies sesion en Windows."
Write-Host ""
Write-Host "Para probarla ahora mismo sin reiniciar la sesion:"
Write-Host "    Start-ScheduledTask -TaskName '$taskName'"
Write-Host "Para ver si esta corriendo:"
Write-Host "    Get-ScheduledTask -TaskName '$taskName' | Get-ScheduledTaskInfo"
Write-Host "Para ver el log en vivo:"
Write-Host "    Get-Content edge_agent.log -Wait -Tail 20"
Write-Host "Para quitarla:"
Write-Host "    Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
