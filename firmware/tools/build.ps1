<#
Build only. This script has no serial-port, flash, erase, security-provisioning,
or deployment command. It is the native Windows equivalent of build.sh.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Work,
    [Parameter(Mandatory)][string]$Idf,
    [Parameter(Mandatory)][string]$ToolPython,
    [ValidateSet('usb-assisted', 'ota')][string]$Mode = 'usb-assisted',
    [string]$IdfToolsPath = $env:IDF_TOOLS_PATH
)

$ErrorActionPreference = 'Stop'
$expectedIdf = 'fff9895c82d744c7237be8847347bdd1b07c6643'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Work = [IO.Path]::GetFullPath($Work)
$Idf = [IO.Path]::GetFullPath($Idf)
$ToolPython = [IO.Path]::GetFullPath($ToolPython)

if (-not $IdfToolsPath) { throw 'Set IDF_TOOLS_PATH or pass -IdfToolsPath.' }
if (-not (Test-Path -LiteralPath $ToolPython -PathType Leaf)) { throw 'AMPVE tooling Python is missing.' }
$revision = (& git -c "safe.directory=$Idf" -C $Idf rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $revision -ne $expectedIdf) { throw 'Unreviewed ESP-IDF commit.' }

$env:PYTHONUTF8 = '1'
$env:IDF_TOOLS_PATH = [IO.Path]::GetFullPath($IdfToolsPath)
$env:CMAKE_NINJA_FORCE_RESPONSE_FILE = '1'

& $ToolPython (Join-Path $root 'firmware\tools\prepare.py') --work $Work --mode $Mode
if ($LASTEXITCODE -ne 0) { throw 'Source preparation failed.' }
& $ToolPython (Join-Path $root 'firmware\tools\assets.py') --output (Join-Path $Work 'main\ampve\brand_assets.c')
if ($LASTEXITCODE -ne 0) { throw 'Brand asset generation failed.' }

. (Join-Path $Idf 'export.ps1')
Set-Location $Work
$env:SOURCE_DATE_EPOCH = '1789257600'
& python scripts/gen_lang.py --language en-US --output main/assets/lang_config.h
if ($LASTEXITCODE -ne 0) { throw 'Language generation failed.' }
$env:SDKCONFIG_DEFAULTS = 'sdkconfig.defaults;sdkconfig.defaults.esp32p4;sdkconfig.ampve'

function Replace-GeneratedText([string]$Path, [string]$Old, [string]$New) {
    $text = [IO.File]::ReadAllText($Path)
    if (-not $text.Contains($Old)) { return }
    [IO.File]::WriteAllText($Path, $text.Replace($Old, $New), [Text.UTF8Encoding]::new($false))
}

$sdkconfig = Join-Path $Work 'sdkconfig'
if ((Test-Path -LiteralPath $sdkconfig) -and
    -not (Select-String -Quiet -LiteralPath $sdkconfig -SimpleMatch 'CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions/ampve/7b-stock-v1.csv"')) {
    Copy-Item -LiteralPath $sdkconfig -Destination "$sdkconfig.pre-stock-profile" -Force
    Remove-Item -LiteralPath $sdkconfig
}
if (Test-Path -LiteralPath $sdkconfig) {
    if (Select-String -Quiet -LiteralPath $sdkconfig -SimpleMatch 'CONFIG_PM_SLEEP_CLK_ICG_ENABLE=y') {
        Copy-Item -LiteralPath $sdkconfig -Destination "$sdkconfig.pre-startup-retention-fix" -Force
        Replace-GeneratedText $sdkconfig 'CONFIG_PM_SLEEP_CLK_ICG_ENABLE=y' '# CONFIG_PM_SLEEP_CLK_ICG_ENABLE is not set'
    }
    if (Select-String -Quiet -LiteralPath $sdkconfig -SimpleMatch 'CONFIG_ESP_MAIN_TASK_STACK_SIZE=16384') {
        Copy-Item -LiteralPath $sdkconfig -Destination "$sdkconfig.pre-scheduler-stack-fix" -Force
        Replace-GeneratedText $sdkconfig 'CONFIG_ESP_MAIN_TASK_STACK_SIZE=16384' 'CONFIG_ESP_MAIN_TASK_STACK_SIZE=4096'
    }
    if ($Mode -eq 'ota') {
        Replace-GeneratedText $sdkconfig 'CONFIG_AMPVE_USB_COMMISSIONING=y' '# CONFIG_AMPVE_USB_COMMISSIONING is not set'
    } else {
        Replace-GeneratedText $sdkconfig '# CONFIG_AMPVE_USB_COMMISSIONING is not set' 'CONFIG_AMPVE_USB_COMMISSIONING=y'
    }
}

if (-not (Test-Path -LiteralPath (Join-Path $Work 'components\78__esp-wifi-connect'))) {
    & idf.py -DIDF_TARGET=esp32p4 -DCMAKE_NINJA_FORCE_RESPONSE_FILE=ON reconfigure
    if ($LASTEXITCODE -ne 0) { throw 'Initial IDF reconfigure failed.' }
    & $ToolPython (Join-Path $root 'firmware\tools\provisioning.py') --work $Work
    if ($LASTEXITCODE -ne 0) { throw 'Provisioning override failed.' }
}

& idf.py -DIDF_TARGET=esp32p4 -DCMAKE_NINJA_FORCE_RESPONSE_FILE=ON reconfigure
if ($LASTEXITCODE -ne 0) { throw 'Final IDF reconfigure failed.' }
& python (Join-Path $root 'firmware\tools\check_lock.py') (Join-Path $Work 'dependencies.lock')
if ($LASTEXITCODE -ne 0) { throw 'Dependency lock validation failed.' }
& ninja -C build -j4
if ($LASTEXITCODE -ne 0) { throw 'Firmware compilation failed.' }
