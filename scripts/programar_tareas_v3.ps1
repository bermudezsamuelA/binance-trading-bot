# Registra en el Programador de tareas de Windows la corrida semanal del canal sombra de la v3 y de la prueba de
# equivalencia de Coinalyze (domingo a las 10:00, hora local). Ejecutar UNA vez en PowerShell desde la raiz del repo:
#   powershell -ExecutionPolicy Bypass -File scripts\programar_tareas_v3.ps1
# Para quitarla: Unregister-ScheduledTask -TaskName "BinanceBot-V3-Sombra" -Confirm:$false
# OJO: las descargas de Binance fallan con la VPN activa; la salida queda en binance-research\v3_research\output\tarea_semanal.log
$repo = Split-Path -Parent $PSScriptRoot
$research = Join-Path $repo "binance-research"
$python = Join-Path $research ".venv\Scripts\python.exe"
$log = Join-Path $research "v3_research\output\tarea_semanal.log"
$cmd = "cd /d `"$research`" && `"$python`" v3_research\shadow\run_daily.py --download >> `"$log`" 2>&1 && `"$python`" v3_research\shadow\equivalence_coinalyze.py >> `"$log`" 2>&1"
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c $cmd"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 10:00
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName "BinanceBot-V3-Sombra" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "Tarea 'BinanceBot-V3-Sombra' registrada: domingos 10:00. Log: $log"
