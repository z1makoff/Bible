# Выключить ПК после ночной работы над главами.
#   powershell -File tools/shutdown_pc.ps1              # выключить через 2 минуты
#   powershell -File tools/shutdown_pc.ps1 -Seconds 600 # через 10 минут
#   powershell -File tools/shutdown_pc.ps1 -Cancel      # отменить запланированное выключение
param([int]$Seconds = 120, [switch]$Cancel)

if ($Cancel) {
    shutdown /a
    Write-Output "Выключение отменено."
    exit
}

# Повторный вызов переносит срок: старый таймер снимается, ставится новый.
shutdown /a 2>$null
shutdown /s /t $Seconds /c "Читалка: работа над главами закончена, ПК выключится."
Write-Output "ПК выключится через $Seconds с. Отмена: powershell -File tools/shutdown_pc.ps1 -Cancel"
