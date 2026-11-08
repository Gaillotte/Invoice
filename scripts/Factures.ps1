# Factures.ps1 - sign in to Gmail and import new invoices.
# Started by Factures.cmd (double-click), or from PowerShell: .\scripts\Factures.ps1

# Folder where Invoice is installed. Change it if you move the project.
$ProjectDir = "C:\DEV\Factures"

$Host.UI.RawUI.WindowTitle = "Factures - import Gmail"

function Stop-WithMessage($Message) {
    Write-Host ""
    Write-Host $Message -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

# 1. Go to the project folder
if (-not (Test-Path $ProjectDir)) {
    Stop-WithMessage "Folder not found: $ProjectDir (edit `$ProjectDir at the top of this script)."
}
Set-Location $ProjectDir

# 2. Activate the Python environment
$Activate = Join-Path $ProjectDir ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $Activate)) {
    Stop-WithMessage "No .venv in $ProjectDir. Create it first (Install Guide, step 3.2)."
}
. $Activate

# 3. Sign in to Gmail (opens the browser only when a new sign-in is needed)
Write-Host "== invoices auth ==" -ForegroundColor Cyan
invoices auth
if ($LASTEXITCODE -ne 0) { Stop-WithMessage "Sign-in failed: see the message above." }

# 4. Import new invoices
Write-Host ""
Write-Host "== invoices fetch ==" -ForegroundColor Cyan
invoices fetch
if ($LASTEXITCODE -ne 0) {
    Write-Host "Some emails could not be imported: see the lines marked ! above." -ForegroundColor Yellow
}

# 5. Show what is left to pay
Write-Host ""
Write-Host "== Unpaid invoices ==" -ForegroundColor Cyan
invoices list --status unpaid

Write-Host ""
Read-Host "Done. Press Enter to close"
