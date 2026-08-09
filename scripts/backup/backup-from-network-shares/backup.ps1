# ========================================
# backup.ps1 — копирование zip архивов в каталог backup с прогрессом
# ========================================

# --- Настройки ---
$backupMap = [ordered]@{
    "\\srv002\C$\diskS\BACKUP\BACKUP1\Backup\current\" = "1cv7\optovik"
    "\\srv005\D$\backup\current\BaseBuh\" = "1cv8\BaseBuh"
    "\\srv005\D$\backup\current\BaseBuhSovel\" = "1cv8\BaseBuhSovel"
    "\\srv005\D$\backup\current\BaseDoc\" = "1cv8\BaseDoc"
    "\\srv005\D$\backup\current\BaseUP\" = "1cv8\BaseUP"
    "\\srv005\D$\backup\current\BaseZUP\" = "1cv8\BaseZUP"
    "\\srv005\D$\backup\current\BaseZUP_2022_NeNalog\" = "1cv8\BaseZUP_2022_NeNalog"
    "\\srv005\D$\backup\current\BaseZUP_NeNalog\" = "1cv8\BaseZUP_NeNalog"
}

# --- Вспомогательная функция для форматирования размера ---
function Format-Size($bytes) {
    if ($bytes -ge 1GB) { return "{0:N2}ГБ" -f ($bytes / 1GB) }
    elseif ($bytes -ge 1MB) { return "{0:N2}МБ" -f ($bytes / 1MB) }
    else { return "{0:N0}КБ" -f ($bytes / 1KB) }
}

# --- Определение корня backup каталога ---
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$destRoot = Join-Path $scriptDir "backup"
$dateFolder = (Get-Date -Format "yyyy-MM-dd")
$destRoot = Join-Path $destRoot $dateFolder
if (!(Test-Path $destRoot)) { New-Item -ItemType Directory -Force -Path $destRoot | Out-Null }

Write-Host "`n=== Проверка ZIP архивов ===`n"
Write-Host "[INFO] Бэкап будет сохранён в: $destRoot`n"

# --- Поиск архивов ---
$foundZips = @()
foreach ($srcPath in $backupMap.Keys) {
    $targetSubdir = $backupMap[$srcPath]
    if (Test-Path $srcPath) {
        $zips = Get-ChildItem -Path $srcPath -Filter "*.zip" -File -ErrorAction SilentlyContinue
        foreach ($zip in $zips) {
            $foundZips += [PSCustomObject]@{
                FilePath   = $zip.FullName
                FileName   = $zip.Name
                Size       = $zip.Length
                DestSubdir = $targetSubdir
            }
        }
    } else {
        Write-Host "[WARN] Путь не найден: $srcPath" -ForegroundColor Yellow
    }
}

if ($foundZips.Count -eq 0) {
    Write-Host "[ERROR] ZIP архивы не найдены!" -ForegroundColor Red
    exit
}

# --- Отображение списка ---
$leftWidth = 70
$barWidth  = 20

Write-Host "`n=== Список архивов для копирования ===`n"
Write-Host "[INFO] Бэкап будет сохранён в: $destRoot`n"

$lineInfo = @()
foreach ($f in $foundZips) {
    $leftTextRaw = "$($f.DestSubdir)\$($f.FileName) ($(Format-Size($f.Size)))"
    if ($leftTextRaw.Length -gt $leftWidth) {
        $leftText = $leftTextRaw.Substring(0, $leftWidth - 3) + "..."
    } else {
        $leftText = $leftTextRaw.PadRight($leftWidth)
    }

    $emptyBar = "░" * $barWidth
    Write-Host ("[ ] " + $leftText + "┃$emptyBar┃ 00%  0.00 МБ/с")
    $lineInfo += [PSCustomObject]@{
        Index = [console]::CursorTop - 1
        File  = $f
    }
}

Write-Host "`n[INFO] Общий прогресс:`n"
$emptyTotal = "░" * $barWidth
Write-Host ("   ┃$emptyTotal┃ 00%")
$totalLine = [console]::CursorTop - 1

# --- Подтверждение перед копированием ---
Write-Host "`n[INFO] Нажмите Enter для начала копирования..."
[void][System.Console]::ReadLine()

# --- Копирование с прогрессом ---
$totalSize = ($foundZips | Measure-Object Size -Sum).Sum
$totalCopied = 0

foreach ($f in $foundZips) {
    $srcFile  = $f.FilePath
    $destFile = Join-Path (Join-Path $destRoot $f.DestSubdir) $f.FileName
    $lineNum  = ($lineInfo | Where-Object { $_.File -eq $f }).Index
    $fileSize = $f.Size
    $copied = 0
    $buffer = New-Object byte[](4MB)
    $in = [IO.File]::OpenRead($srcFile)
    $outDir = Split-Path $destFile -Parent
    if (!(Test-Path $outDir)) { New-Item -ItemType Directory -Force -Path $outDir | Out-Null }
    $out = [IO.File]::Create($destFile)
    $sw = [Diagnostics.Stopwatch]::StartNew()

    while (($read = $in.Read($buffer, 0, $buffer.Length)) -gt 0) {
        $out.Write($buffer, 0, $read)
        $copied += $read
        $totalCopied += $read

        $pct = [math]::Floor(($copied / $fileSize) * 100)
        $pctText = ("{0:00}" -f $pct) + "%"
        $barCount = [math]::Floor(($pct / 100) * $barWidth)
        $bar = ("█" * $barCount).PadRight($barWidth, "░")
        $speed = if ($sw.Elapsed.TotalSeconds -gt 0) { "{0,6:N2}" -f (($copied / 1MB) / $sw.Elapsed.TotalSeconds) } else { " 0.00" }

        # Обновляем строку файла
        $leftTextRaw = "$($f.DestSubdir)\$($f.FileName) ($(Format-Size($f.Size)))"
        if ($leftTextRaw.Length -gt $leftWidth) {
            $leftText = $leftTextRaw.Substring(0, $leftWidth - 3) + "..."
        } else {
            $leftText = $leftTextRaw.PadRight($leftWidth)
        }

        [console]::SetCursorPosition(0, $lineNum)
        Write-Host ("[V] " + $leftText + "┃$bar┃ $pctText $speed МБ/с    ") -NoNewline

        # Обновляем общий прогресс
        $totalPct = [math]::Floor(($totalCopied / $totalSize) * 100)
        $totalBar = ("█" * [math]::Floor(($totalPct / 100) * $barWidth)).PadRight($barWidth, "░")
        [console]::SetCursorPosition(3, $totalLine)
        Write-Host ("┃$totalBar┃ {0:00}%" -f $totalPct) -NoNewline
    }

    $in.Close()
    $out.Close()
}

Write-Host "`n`n[INFO] Копирование завершено. Нажмите Enter для выхода..."
[void][System.Console]::ReadLine()
