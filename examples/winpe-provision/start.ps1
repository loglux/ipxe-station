# Fetched and run by startnet.cmd inside WinPE (X:).
# Detects the machine model, downloads the matching payload packages from the server,
# unpacks them to X:\provision and runs run.cmd from the payload if there is one.
param([Parameter(Mandatory)][string]$Server)

$base = "http://$Server/http/provision"
$work = 'X:\provision'
New-Item -ItemType Directory -Force -Path $work | Out-Null

function Get-Slug([string]$s) { ($s -replace '[^A-Za-z0-9]+', '-').Trim('-').ToLower() }

$cs     = Get-CimInstance Win32_ComputerSystem
$prod   = Get-CimInstance Win32_ComputerSystemProduct
$vendor = Get-Slug $cs.Manufacturer
# Lenovo keeps the friendly model name in Version; Name holds the machine-type code.
$model  = if ($vendor -like 'lenovo*') { $prod.Version } else { $cs.Model }
$slug   = "${vendor}_$(Get-Slug $model)"

Write-Host "Detected: $($cs.Manufacturer) / $model  ->  models/$slug"

# Optional packages: common.zip for every machine, models/<vendor>_<model>.zip for this model.
foreach ($pkg in @('common', "models/$slug")) {
    $zip = Join-Path $work (($pkg -replace '/', '_') + '.zip')
    try {
        (New-Object Net.WebClient).DownloadFile("$base/$pkg.zip", $zip)
    } catch {
        Write-Host "No package: $pkg"
        continue
    }
    Expand-Archive -Path $zip -DestinationPath $work -Force
    Write-Host "Unpacked: $pkg"
}

# Drivers shipped in a package under drivers\ (e.g. Intel RST/VMD for machines set to RAID mode).
$drivers = Join-Path $work 'drivers'
if (Test-Path $drivers) {
    Get-ChildItem $drivers -Recurse -Filter *.inf | ForEach-Object {
        Write-Host "drvload $($_.Name)"
        & drvload.exe $_.FullName | Out-Null
    }
    'rescan' | diskpart | Out-Null
}

$run = Join-Path $work 'run.cmd'
if (Test-Path $run) {
    & cmd.exe /c $run
} else {
    Write-Host "No run.cmd in the payload. Nothing to run - staying in WinPE."
}
