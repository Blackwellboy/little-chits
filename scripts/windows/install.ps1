# Puts the "Little Chits" and "Stop Little Chits" shortcuts on the Windows desktop. Run by `make shortcut`.
# Prints the desktop folder it used (it may be under OneDrive).
param([Parameter(Mandatory = $true)][string]$Dir)

$desk = [Environment]::GetFolderPath("Desktop")
$shell = New-Object -ComObject WScript.Shell

function New-Shortcut([string]$name, [string]$vbs, [string]$icon, [string]$desc) {
    $lnk = $shell.CreateShortcut((Join-Path $desk "$name.lnk"))
    $lnk.TargetPath = Join-Path $env:WINDIR "System32\wscript.exe"
    $lnk.Arguments = '"' + (Join-Path $Dir $vbs) + '"'
    $lnk.WorkingDirectory = $Dir
    $lnk.IconLocation = (Join-Path $Dir $icon) + ",0"
    $lnk.Description = $desc
    $lnk.Save()
}

New-Shortcut "Little Chits" "start.vbs" "icon.ico" "Start the AI models and Little Chits, then open it in your browser"
New-Shortcut "Stop Little Chits" "stop.vbs" "icon-stop.ico" "Stop Little Chits (and, if you like, the AI models)"

# The old "Little Chits.bat" launcher is replaced by the shortcut.
$old = Join-Path $desk "Little Chits.bat"
if (Test-Path $old) { Remove-Item $old }
Write-Output $desk
