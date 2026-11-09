[CmdletBinding()]
param([string]$Serial = 'emulator-5554', [switch]$VerifyLlm)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskAdb = Join-Path $env:LOCALAPPDATA 'Programs\Android\Sdk\platform-tools\adb.exe'
$taskPrivateRoot = [IO.Path]::GetFullPath((Join-Path $taskRoot 'evidence\private\history'))
$taskFixture = [IO.Path]::GetFullPath((Join-Path $taskRoot ((Get-Content (Join-Path $taskRoot 'evidence\history\latest-fixture.json') -Raw | ConvertFrom-Json).fixture)))
if (-not $taskFixture.StartsWith($taskPrivateRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid private fixture path.' }
$taskOutput = Join-Path $taskRoot 'evidence\history'
$taskScreens = Join-Path $taskFixture 'screenshots'
$null = New-Item -ItemType Directory -Path $taskScreens -Force
$taskBackend = $null
$taskDeviceConfig = '/sdcard/Android/data/com.haddol7.photoviewer.assessment02/files/history-test-config.json'
function Invoke-Adb([string[]]$Arguments) {
    $text = (& $taskAdb -s $Serial @Arguments 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "ADB operation failed: $text" }
    return $text
}
try {
    if ((Invoke-Adb @('get-state')).Trim() -ne 'device') { throw 'Android device is unavailable.' }
    $build = Get-Content (Join-Path $taskRoot 'evidence\content\android\verification.json') -Raw | ConvertFrom-Json
    if ($build.status -ne 'passed') { throw 'Build and lint must pass first.' }
    foreach ($apk in $build.build.apks) {
        $file = Join-Path $taskRoot $apk.path
        if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $apk.sha256) { throw 'APK source verification differs.' }
        $installed = Invoke-Adb @('install','-r','-t',$file)
        if ($installed -notmatch '(?m)^Success\s*$') { throw 'APK installation failed.' }
    }
    $linuxRoot = (& wsl.exe -d Ubuntu --exec wslpath -a $taskRoot).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'WSL path resolution failed.' }
    $info = [Diagnostics.ProcessStartInfo]::new('wsl.exe')
    foreach ($value in @('-d','Ubuntu','--cd',$linuxRoot,'--','/home/daeha/.venvs/mobile_web_service_02/bin/python','-u','tools/serve_history_fixture.py')) { $info.ArgumentList.Add($value) }
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardInput = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $taskBackend = [Diagnostics.Process]::new()
    $taskBackend.StartInfo = $info
    if (-not $taskBackend.Start()) { throw 'WSL fixture server did not start.' }
    $readyLine = $taskBackend.StandardOutput.ReadLineAsync()
    if (-not $readyLine.Wait(20000) -or -not $readyLine.Result) { throw 'WSL fixture did not become ready.' }
    $ready = $readyLine.Result | ConvertFrom-Json
    if (-not $ready.ready) { throw 'Unexpected fixture readiness result.' }
    $credentials = Get-Content (Join-Path $taskFixture 'test-auth.json') -Raw | ConvertFrom-Json
    $proof = Get-Content (Join-Path $taskOutput 'verification.json') -Raw | ConvertFrom-Json
    $config = @{server=('http://10.0.2.2:'+$ready.port+'/');username=$credentials.username;password=$credentials.password;expected_passages=$proof.passages_stored;verify_llm=[bool]$VerifyLlm}
    $configPath = Join-Path $taskFixture 'device-config.json'
    [IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    $null = Invoke-Adb @('shell','mkdir','-p','/sdcard/Android/data/com.haddol7.photoviewer.assessment02/files')
    $null = Invoke-Adb @('push',$configPath,$taskDeviceConfig)
    $result = Invoke-Adb @('shell','am','instrument','-w','-e','class','com.haddol7.photoviewer.ui.HistorySyncTest','com.haddol7.photoviewer.assessment02.test/android.test.InstrumentationTestRunner')
    [IO.File]::WriteAllText((Join-Path $taskOutput 'android-test.txt'), $result, [Text.UTF8Encoding]::new($false))
    if ($result -notmatch 'OK \(2 tests\)' -or $result -match 'FAILURES|INSTRUMENTATION_FAILED') { throw 'History device tests failed; inspect evidence/history/android-test.txt.' }
    $screenshots = @()
    foreach ($name in @('history-native-list.png','history-native-question.png','history-mobile-web-list.png','history-mobile-web-detail.png','history-mobile-web-question.png')) {
        $file = Join-Path $taskScreens $name
        $null = Invoke-Adb @('pull',('/sdcard/Android/data/com.haddol7.photoviewer.assessment02/files/evidence/'+$name),$file)
        $screenshots += @{path=[IO.Path]::GetRelativePath($taskRoot,$file).Replace('\','/');sha256=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()}
    }
    $record = @{verified_utc=(Get-Date).ToUniversalTime().ToString('o');environment='Windows Android API35 emulator with WSL Django';device=$Serial;tests=2;pass=$true;actual_native_and_webview=$true;first_viewport_multiple_cards=$true;horizontal_overflow=$false;detail_controls_fit=$true;grounded_question_evidence_verified=$true;actual_llm_generation_verified=[bool]$VerifyLlm;production_verified=$false;screenshots=$screenshots}
    [IO.File]::WriteAllText((Join-Path $taskOutput 'mobile-verification.json'), ($record | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    Write-Output 'PASS: Android native and actual WebView history tests, including five screenshots.'
} finally {
    if (Test-Path -LiteralPath $taskAdb) { $null = & $taskAdb -s $Serial shell rm -f $taskDeviceConfig 2>$null }
    if ($null -ne $taskBackend -and -not $taskBackend.HasExited) {
        $taskBackend.StandardInput.WriteLine('stop')
        $taskBackend.StandardInput.Close()
        if (-not $taskBackend.WaitForExit(5000)) { $taskBackend.Kill($true) }
    }
    if ($null -ne $taskBackend) { $taskBackend.Dispose() }
}
