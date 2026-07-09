$ErrorActionPreference = "Stop"

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Minervini Scanner v3.0.lnk"
$repoCandidates = @(
    "$env:USERPROFILE\minervini-ai-screener",
    "$env:USERPROFILE\Desktop\minervini-ai-screener"
)

# Prefer the BAT file next to this script if the repo is opened from Windows/WSL share.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$batPath = Join-Path $scriptDir "Minervini_Scan.bat"
if (!(Test-Path $batPath)) {
    foreach ($candidate in $repoCandidates) {
        $candidateBat = Join-Path $candidate "Minervini_Scan.bat"
        if (Test-Path $candidateBat) {
            $batPath = $candidateBat
            break
        }
    }
}

if (!(Test-Path $batPath)) {
    throw "Cannot find Minervini_Scan.bat. Run this script from the minervini-ai-screener repo folder."
}

$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $batPath
$shortcut.WorkingDirectory = Split-Path -Parent $batPath
$shortcut.Description = "Run Minervini Scanner v3.0 in WSL and open the HTML report"
$shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,167"
$shortcut.Save()

Write-Host "Created desktop shortcut: $shortcutPath"
Write-Host "Target: $batPath"
