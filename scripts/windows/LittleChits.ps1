# The small progress window behind the "Little Chits" and "Stop Little Chits" desktop shortcuts.
# `make shortcut` copies this to %LOCALAPPDATA%\LittleChits with a config.json beside it; the shortcuts run it
# through start.vbs / stop.vbs so no console window flashes up.
# It runs scripts/desktop.sh inside WSL and shows the "@step/@ok/@warn/@fail" lines it prints.
# Keep this file plain ASCII: Windows PowerShell 5.1 misreads UTF-8 without a BOM.
param([ValidateSet("start", "stop")][string]$Action = "start")

$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Cfg = Get-Content (Join-Path $Here "config.json") -Raw | ConvertFrom-Json
$Url = "http://localhost:$($Cfg.port)"
$Log = Join-Path $Here "last-$Action.log"

# WSL normally forwards localhost:PORT to the game. When that relay dies (it does now and then, until WSL restarts),
# the game is still reachable at WSL's own address, so open that instead of a page that never loads.
function Test-Game([string]$u) {
    try { return ((Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "$u/api/health").StatusCode -eq 200) } catch { return $false }
}
function Get-GameUrl {
    if (Test-Game $Url) { return $Url }
    try {
        $ip = (& wsl.exe -d $Cfg.distro -- hostname -I) -split '\s+' | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' } | Select-Object -First 1
        if ($ip) { $alt = "http://$($ip):$($Cfg.port)"; if (Test-Game $alt) { return $alt } }
    } catch {}
    return $Url
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

# One window per shortcut: a second double-click while the first is still working does nothing.
$created = $false
$mutex = New-Object System.Threading.Mutex($true, "Local\LittleChits-$Action", [ref]$created)
if (-not $created) { exit 0 }

$withModels = $false
if ($Action -eq "stop") {
    $answer = [System.Windows.Forms.MessageBox]::Show(
        "Stop Little Chits?`n`nAlso stop the AI model servers? That frees your GPUs, but anything else using those " +
        "models stops too, and the next start takes a few minutes longer.`n`n" +
        "Yes = stop the game AND the models`nNo = stop just the game`nCancel = don't stop anything",
        "Stop Little Chits", "YesNoCancel", "Question")
    if ($answer -eq "Cancel") { exit 0 }
    $withModels = ($answer -eq "Yes")
}

# ---------------------------------------------------------------- window
$form = New-Object System.Windows.Forms.Form
$form.Text = if ($Action -eq "start") { "Little Chits" } else { "Stop Little Chits" }
$form.Size = New-Object System.Drawing.Size(600, 380)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.BackColor = [System.Drawing.Color]::FromArgb(27, 35, 54)
$form.ForeColor = [System.Drawing.Color]::White
$form.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$icon = Join-Path $Here "icon.ico"
if (Test-Path $icon) { $form.Icon = New-Object System.Drawing.Icon($icon) }

$title = New-Object System.Windows.Forms.Label
$title.Text = if ($Action -eq "start") { "Getting your world ready..." } else { "Stopping..." }
$title.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 14)
$title.ForeColor = [System.Drawing.Color]::FromArgb(255, 184, 107)
$title.Location = New-Object System.Drawing.Point(18, 14)
$title.AutoSize = $true
$form.Controls.Add($title)

$list = New-Object System.Windows.Forms.RichTextBox
$list.Location = New-Object System.Drawing.Point(18, 54)
$list.Size = New-Object System.Drawing.Size(548, 216)
$list.ReadOnly = $true
$list.BorderStyle = "None"
$list.BackColor = $form.BackColor
$list.ForeColor = $form.ForeColor
$list.Font = New-Object System.Drawing.Font("Segoe UI", 10.5)
$list.TabStop = $false
$form.Controls.Add($list)

$bar = New-Object System.Windows.Forms.ProgressBar
$bar.Style = "Marquee"
$bar.MarqueeAnimationSpeed = 30
$bar.Location = New-Object System.Drawing.Point(18, 282)
$bar.Size = New-Object System.Drawing.Size(330, 14)
$form.Controls.Add($bar)

$openBtn = New-Object System.Windows.Forms.Button
$openBtn.Text = "Open the game"
$openBtn.Location = New-Object System.Drawing.Point(360, 274)
$openBtn.Size = New-Object System.Drawing.Size(110, 30)
$openBtn.FlatStyle = "Flat"
$openBtn.Visible = ($Action -eq "start")
$openBtn.Enabled = $false
$openBtn.Add_Click({ Start-Process (Get-GameUrl) })
$form.Controls.Add($openBtn)

$closeBtn = New-Object System.Windows.Forms.Button
$closeBtn.Text = "Close"
$closeBtn.Location = New-Object System.Drawing.Point(478, 274)
$closeBtn.Size = New-Object System.Drawing.Size(88, 30)
$closeBtn.FlatStyle = "Flat"
$closeBtn.Add_Click({ $form.Close() })
$form.Controls.Add($closeBtn)

$foot = New-Object System.Windows.Forms.Label
$foot.Location = New-Object System.Drawing.Point(18, 312)
$foot.Size = New-Object System.Drawing.Size(548, 22)
$foot.ForeColor = [System.Drawing.Color]::FromArgb(150, 160, 185)
$foot.Font = New-Object System.Drawing.Font("Segoe UI", 8.5)
$foot.Text = "Details: $Log"
$form.Controls.Add($foot)

# ---------------------------------------------------------------- progress lines
$rows = New-Object System.Collections.Specialized.OrderedDictionary
$Marks = @{ step = [string][char]0x2026; ok = [string][char]0x2714; warn = "!"; fail = [string][char]0x2716 }
$Colors = @{
    step = [System.Drawing.Color]::FromArgb(138, 208, 255); ok = [System.Drawing.Color]::FromArgb(120, 220, 140)
    warn = [System.Drawing.Color]::FromArgb(255, 200, 90); fail = [System.Drawing.Color]::FromArgb(255, 110, 110)
}
$state = @{ failed = $false; warned = $false; done = $false; opened = $false; pos = 0; closeAt = $null; exited = $false }

function Show-Rows {
    $list.Clear()
    foreach ($k in $rows.Keys) {
        $r = $rows[$k]
        $list.SelectionColor = $Colors[$r.kind]
        $list.AppendText("  " + $Marks[$r.kind] + "  ")
        $list.SelectionColor = $form.ForeColor
        $list.AppendText($r.text + "`n")
    }
}

function Set-Row([string]$key, [string]$kind, [string]$text) {
    $rows[$key] = @{ kind = $kind; text = $text }
    Show-Rows
}

function Handle-Line([string]$line) {
    if ($line -notmatch '^@(\w+)(?:\s+(\S+))?(?:\s+(.*))?$') { return }
    $tag = $Matches[1]; $key = $Matches[2]; $text = $Matches[3]
    switch ($tag) {
        "open" {
            Set-Row "open" "ok" "Opening the game in your browser..."
            $openBtn.Enabled = $true
            if (-not $state.opened) { $state.opened = $true; Start-Process (Get-GameUrl) }
        }
        "done" { $state.done = $true }
        default {
            if ($Colors.ContainsKey($tag)) {
                Set-Row $key $tag $text
                if ($tag -eq "fail") { $state.failed = $true }
                if ($tag -eq "warn") { $state.warned = $true }
            }
        }
    }
}

# ---------------------------------------------------------------- run desktop.sh in WSL
$wslArgs = @("-d", $Cfg.distro, "-e", "bash", $Cfg.shim, $Action, [string]$Cfg.port)
if ($withModels) { $wslArgs += "--models" }
Set-Row "wsl" "step" "Waking up Linux (WSL)..."
Set-Content -Path $Log -Value "" -Encoding UTF8
$proc = Start-Process -FilePath "wsl.exe" -ArgumentList $wslArgs -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $Log -RedirectStandardError "$Log.err"

function Read-NewLines {
    try {
        $fs = [System.IO.File]::Open($Log, "Open", "Read", "ReadWrite")
        try {
            if ($fs.Length -le $state.pos) { return }
            $fs.Position = $state.pos
            $buf = New-Object byte[] ($fs.Length - $state.pos)
            $n = $fs.Read($buf, 0, $buf.Length)
            $text = [System.Text.Encoding]::UTF8.GetString($buf, 0, $n)
            $cut = $text.LastIndexOf("`n")
            if ($cut -lt 0) { return }
            $state.pos += [System.Text.Encoding]::UTF8.GetByteCount($text.Substring(0, $cut + 1))
            if ($rows.Contains("wsl")) { $rows.Remove("wsl") }
            foreach ($l in $text.Substring(0, $cut).Split("`n")) { Handle-Line $l.TrimEnd("`r") }
        } finally { $fs.Close() }
    } catch { }
}

function Keep-WslAlive {
    # A hidden WSL process that lives as long as the game does, so Windows doesn't shut WSL (and the game) down.
    $running = Get-CimInstance Win32_Process -Filter "Name='wsl.exe'" |
        Where-Object { $_.CommandLine -match "desktop\.sh keepalive" }
    if (-not $running) {
        Start-Process -FilePath "wsl.exe" -WindowStyle Hidden `
            -ArgumentList @("-d", $Cfg.distro, "-e", "bash", $Cfg.shim, "keepalive", [string]$Cfg.port) | Out-Null
    }
}

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 300
$timer.Add_Tick({
    Read-NewLines
    if ($state.closeAt) {
        if ((Get-Date) -ge $state.closeAt) { $timer.Stop(); $form.Close() }
        return
    }
    if (-not $state.exited -and $proc.HasExited) {
        $state.exited = $true
        Read-NewLines
        $bar.Visible = $false
        # the work is finished: a new double-click may start again even if this window is still open
        try { $mutex.ReleaseMutex() } catch { }
        if (-not $state.done -and -not $state.failed) {
            $state.failed = $true
            Set-Row "crash" "fail" "Something went wrong before it finished. The details are in the log below."
        }
        if ($state.failed) {
            $title.Text = "That didn't work"
            $title.ForeColor = $Colors.fail
        } elseif ($Action -eq "start") {
            Keep-WslAlive
            $title.Text = if ($state.warned) { "Running, with a warning (see above)" } else { "All set. Have fun!" }
            if (-not $state.warned) { $state.closeAt = (Get-Date).AddSeconds(6) }
        } else {
            $title.Text = "Stopped."
            if (-not $state.warned) { $state.closeAt = (Get-Date).AddSeconds(4) }
        }
    }
})
$timer.Start()
$form.Add_FormClosed({ $timer.Stop(); try { $mutex.ReleaseMutex() } catch { } })
[void]$form.ShowDialog()
