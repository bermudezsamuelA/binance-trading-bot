# Registra en el Programador de tareas de Windows dos tareas de la v3 (solo medicion y senales; NO envian ordenes):
#   BinanceBot-V3-Sombra    : todos los dias 10:00. Descarga datos nuevos, corre el canal sombra (resumen en
#                             binance-research\v3_research\output\prospectivo) y la prueba de equivalencia de Coinalyze.
#   BinanceBot-V3-Senales   : cada 15 minutos. Anota en output\vivo\senales_vivo.csv las senales P1/S1/S1H de la ultima vela
#                             cerrada (usa la historia que baja la tarea diaria, la API spot de Binance y Coinalyze).
# Ejecutar UNA vez en PowerShell desde la raiz del repo:
#   powershell -ExecutionPolicy Bypass -File scripts\programar_tareas_v3.ps1
# Para quitarlas: Unregister-ScheduledTask -TaskName "BinanceBot-V3-Sombra","BinanceBot-V3-Senales" -Confirm:$false
# OJO: las descargas de Binance fallan con la VPN activa; los logs quedan en binance-research\v3_research\output\
$repo = Split-Path -Parent $PSScriptRoot
$research = Join-Path $repo "binance-research"
$python = Join-Path $research ".venv\Scripts\python.exe"
$out = Join-Path $research "v3_research\output"

$daily = "cd /d `"$research`" && `"$python`" v3_research\shadow\run_daily.py --download >> `"$out\tarea_diaria.log`" 2>&1 && `"$python`" v3_research\shadow\equivalence_coinalyze.py >> `"$out\tarea_diaria.log`" 2>&1"
Register-ScheduledTask -TaskName "BinanceBot-V3-Sombra" -Force `
    -Action (New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c $daily") `
    -Trigger (New-ScheduledTaskTrigger -Daily -At 10:00) `
    -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)) | Out-Null

$live = "cd /d `"$research`" && `"$python`" v3_research\shadow\v3_live.py --no-download >> `"$out\tarea_senales.log`" 2>&1"
$every15 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName "BinanceBot-V3-Senales" -Force `
    -Action (New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c $live") `
    -Trigger $every15 `
    -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)) | Out-Null

Write-Host "Tareas registradas: BinanceBot-V3-Sombra (diaria 10:00) y BinanceBot-V3-Senales (cada 15 min). Logs en $out"
