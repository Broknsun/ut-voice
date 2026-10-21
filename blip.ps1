# blip.ps1 — UT Voice 的 PowerShell 外壳
#
# 用法：在当前会话里 dot-source 一次
#     . D:\zaxiang\ut-voice\blip.ps1
#
# 然后：
#     blip "我在这呢"                  # 用抹香的声音念一句
#     blip "done" -Voice papyrus       # 换嗓
#     blip-done                        # 任务完成音（预生成，毫秒级）
#     blip-error                       # 出错音
#     blip-alert                       # 提醒音
#     Invoke-Bliped { npm run build }  # 跑命令，按结果收尾发声
#     blip-loop "等你回来"             # 循环念到 Ctrl+C
#
# 想让它开机就可用，把下面这行加进 $PROFILE：
#     . D:\zaxiang\ut-voice\blip.ps1

$script:UTVoiceRoot = if ($PSScriptRoot) { $PSScriptRoot } else { "D:\zaxiang\ut-voice" }
$script:UTPlayer = $null

function Get-UTPlayer {
    if ($script:UTPlayer) { return $script:UTPlayer }
    Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
    $script:UTPlayer = New-Object System.Media.SoundPlayer
    $script:UTPlayer
}

function Play-UTFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Warning "找不到音频: $Path"
        return
    }
    $p = Get-UTPlayer
    $p.SoundLocation = (Resolve-Path -LiteralPath $Path).Path
    $p.Load()
    $p.PlaySync()
}

function Play-Cue([string]$Name) {
    Play-UTFile (Join-Path $script:UTVoiceRoot "demos\cue_$Name.wav")
}

function blip {
    <#
    .SYNOPSIS
        用 UT 音色念一句话。
    #>
    param(
        [Parameter(Position = 0, ValueFromPipeline = $true)]
        [string]$Text = "heh. ok.",
        [ValidateSet("sans", "papyrus", "toriel", "flowey", "undyne", "alphys", "blook", "maxiang")]
        [string]$Voice = "maxiang",
        [switch]$NoPlay
    )
    $py = (Get-Command python -ErrorAction SilentlyContinue)
    if (-not $py) { Write-Warning "没找到 python"; return }
    $cliArgs = @((Join-Path $script:UTVoiceRoot "ut_say.py"), "-v", $Voice, $Text)
    if ($NoPlay) { $cliArgs += "--no-play" }
    & $py.Source @cliArgs | Out-Null
}

function blip-done  { Play-Cue "done"  }
function blip-error { Play-Cue "error" }
function blip-alert { Play-Cue "alert" }

function Invoke-Bliped {
    <#
    .SYNOPSIS
        跑一段命令，成功响"完成"，失败响"出错"。
    .EXAMPLE
        Invoke-Bliped { npm run build }
    #>
    param([Parameter(Mandatory)][scriptblock]$Script)

    $code = 0
    try {
        & $Script
        $code = if ($null -ne $LASTEXITCODE) { $LASTEXITCODE } else { 0 }
    } catch {
        Write-Error $_
        $code = 1
    }
    if ($code -eq 0) { blip-done } else { blip-error }
    $code
}

function blip-loop {
    <#
    .SYNOPSIS
        每隔几秒念一次，直到 Ctrl+C。适合"跑完提醒我"。
    #>
    param(
        [string]$Text = "好了呢。",
        [ValidateSet("sans", "papyrus", "toriel", "flowey", "undyne", "alphys", "blook", "maxiang")]
        [string]$Voice = "maxiang",
        [int]$IntervalSeconds = 10,
        [int]$Times = 0   # 0 = 无限
    )
    $i = 0
    while ($Times -eq 0 -or $i -lt $Times) {
        blip $Text -Voice $Voice
        $i++
        if ($Times -eq 0 -or $i -lt $Times) { Start-Sleep -Seconds $IntervalSeconds }
    }
}

Write-Host "UT Voice ready  ·  blip-done / blip-error / blip-alert / blip <text> -Voice <name>" -ForegroundColor DarkGray
