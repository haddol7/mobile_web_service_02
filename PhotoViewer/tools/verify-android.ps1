[CmdletBinding()]
param(
    [switch]$RunDevice,
    [string]$Serial = 'emulator-5554',
    [string]$Server = 'http://10.0.2.2:8000/',
    [string]$Diagnostic = 'http://10.0.2.2:8002/'
)

# Run from Windows. No emulator is started/stopped and no backend is started here.
# BuildOnly (default): .\tools\verify-android.ps1
# Device: first start WSL Django:8000 and the one-shot capture tool:8002, then:
# .\tools\verify-android.ps1 -RunDevice -Serial emulator-5554 `
#     -Server http://10.0.2.2:8000/ -Diagnostic http://10.0.2.2:8002/
# Device tests use an existing isolated publisher and CREATE photos, not users.
# Set TEST_OWNER_USERNAME and TEST_OWNER_PASSWORD for that isolated local server.
# Existing server records are never deleted. Credentials/tokens are not persisted.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$taskProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskCommonRoot = Split-Path -Parent $taskProjectRoot
$taskEvidenceRoot = Join-Path $taskCommonRoot 'evidence\content\android'
$taskRunId = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$taskPrivateRoot = Join-Path $taskCommonRoot ('evidence\private\androidVerification\' + $taskRunId)
$taskOriginalJavaHome = $env:JAVA_HOME
$taskOriginalAndroidHome = $env:ANDROID_HOME
$taskOriginalAndroidSdkRoot = $env:ANDROID_SDK_ROOT

function Get-RelativePath {
    param([string]$Root, [string]$Path)
    $fullRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    $fullPath = [IO.Path]::GetFullPath($Path)
    if (-not $fullPath.StartsWith($fullRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Verification artifact must stay inside its expected directory.'
    }
    return $fullPath.Substring($fullRoot.Length).Replace('\', '/')
}

function Get-SourceManifest {
    $files = @(Get-ChildItem -LiteralPath (Join-Path $taskProjectRoot 'app\src') -Recurse -File)
    foreach ($relative in @('build.gradle.kts', 'settings.gradle.kts', 'gradle.properties',
            'app\build.gradle.kts', 'app\proguard-rules.pro', 'gradlew', 'gradlew.bat',
            'gradle\wrapper\gradle-wrapper.jar', 'gradle\wrapper\gradle-wrapper.properties',
            'gradle\gradle-daemon-jvm.properties', 'tools\verify-android.ps1')) {
        $path = Join-Path $taskProjectRoot $relative
        if (Test-Path -LiteralPath $path -PathType Leaf) { $files += Get-Item -LiteralPath $path }
    }
    $entries = @($files | Sort-Object FullName -Unique | ForEach-Object {
        [pscustomobject]@{
            path = Get-RelativePath $taskProjectRoot $_.FullName
            bytes = $_.Length
            sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    } | Sort-Object path)
    $canonical = ($entries | ForEach-Object { $_.path + [char]0 + $_.sha256 }) -join "`n"
    $digest = [Security.Cryptography.SHA256]::Create()
    try { $sha = [BitConverter]::ToString($digest.ComputeHash([Text.Encoding]::UTF8.GetBytes($canonical))).Replace('-', '').ToLowerInvariant() }
    finally { $digest.Dispose() }
    return [pscustomobject]@{ sha256 = $sha; filesCount = $entries.Count; files = $entries }
}

function Invoke-LoggedNative {
    param([string]$Executable, [string[]]$Arguments, [string]$LogName)
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { throw 'A required verification executable is missing.' }
    $logPath = Join-Path $taskPrivateRoot $LogName
    $oldPreference = $ErrorActionPreference
    Push-Location -LiteralPath $taskProjectRoot
    try {
        # Native stderr is diagnostic text, not proof of failure/success by itself.
        $ErrorActionPreference = 'Continue'
        $output = @(& $Executable @Arguments 2>&1 | ForEach-Object { $_.ToString() })
        $exitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $oldPreference; Pop-Location }
    $text = $output -join "`n"
    Set-Content -LiteralPath $logPath -Value $text -Encoding UTF8
    return [pscustomobject]@{ exitCode = $exitCode; text = $text; logPath = Get-RelativePath $taskCommonRoot $logPath }
}

function Get-InstrumentationVerdict {
    param([int]$ExitCode, [string]$Text, [int]$Expected)
    $failures = '(?im)FAILURES!!!|INSTRUMENTATION_FAILED|INSTRUMENTATION_ABORTED|Process crashed|Test run failed|^Error:|^INSTRUMENTATION_RESULT:\s*(?:shortMsg|Error)\s*='
    $matches = [regex]::Matches($Text, '\bOK\s*\((\d+)\s+tests?\)')
    $count = if ($matches.Count -eq 1) { [int]$matches[0].Groups[1].Value } else { 0 }
    $passed = $ExitCode -eq 0 -and -not [regex]::IsMatch($Text, $failures) -and $matches.Count -eq 1 -and $count -eq $Expected
    return [pscustomobject]@{ passed = $passed; tests = $count; expected = $Expected }
}

function Read-SafeXml {
    param([string]$Path)
    $options = New-Object Xml.XmlReaderSettings
    $options.DtdProcessing = [Xml.DtdProcessing]::Prohibit
    $options.XmlResolver = $null
    $reader = [Xml.XmlReader]::Create($Path, $options)
    try {
        $document = New-Object Xml.XmlDocument
        $document.XmlResolver = $null
        $document.Load($reader)
        return ,$document
    } finally { $reader.Dispose() }
}

function Get-UnitTestResults {
    $directory = Join-Path $taskProjectRoot 'app\build\test-results\testDebugUnitTest'
    $xmlFiles = @(Get-ChildItem -LiteralPath $directory -Filter 'TEST-*.xml' -File)
    if ($xmlFiles.Count -eq 0) { throw 'Gradle did not produce unit-test XML reports.' }
    $tests = 0; $failures = 0; $errors = 0; $skipped = 0; $suites = @()
    foreach ($file in $xmlFiles) {
        $document = Read-SafeXml $file.FullName
        $suite = $document.DocumentElement
        # PowerShell's XML adapter exposes the `name` attribute as .Name.
        if ($suite.LocalName -ne 'testsuite') { throw 'Unexpected Gradle unit-test XML format.' }
        $count = [int]$suite.GetAttribute('tests')
        $failed = [int]$suite.GetAttribute('failures')
        $errorCount = [int]$suite.GetAttribute('errors')
        $skipCount = [int]$suite.GetAttribute('skipped')
        $tests += $count; $failures += $failed; $errors += $errorCount; $skipped += $skipCount
        $suites += [pscustomobject]@{ name = $suite.GetAttribute('name'); tests = $count; failures = $failed; errors = $errorCount; skipped = $skipCount }
    }
    return [pscustomobject]@{
        passed = $tests -gt 0 -and $failures -eq 0 -and $errors -eq 0 -and $skipped -eq 0
        tests = $tests; failures = $failures; errors = $errors; skipped = $skipped; suites = $suites
    }
}

function Get-LintResults {
    $path = Join-Path $taskProjectRoot 'app\build\reports\lint-results-debug.xml'
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'Gradle did not produce the debug lint XML report.' }
    $document = Read-SafeXml $path
    $issues = @($document.SelectNodes('/issues/issue') | ForEach-Object {
        [pscustomobject]@{ id = $_.GetAttribute('id'); severity = $_.GetAttribute('severity') }
    })
    $fatal = @($issues | Where-Object { $_.severity -in @('Fatal', 'Error') }).Count
    return [pscustomobject]@{ passed = $fatal -eq 0; errors = $fatal; warnings = @($issues | Where-Object { $_.severity -eq 'Warning' }).Count; issues = $issues }
}

function Get-ArtifactHash {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw 'A required verification artifact is missing.' }
    $file = Get-Item -LiteralPath $Path
    return [pscustomobject]@{ path = Get-RelativePath $taskCommonRoot $file.FullName; bytes = $file.Length; sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
}

function Get-SdkRoot {
    # Match Gradle's local.properties before consulting optional environment variables.
    $localFile = Join-Path $taskProjectRoot 'local.properties'
    if (Test-Path -LiteralPath $localFile -PathType Leaf) {
        $sdkLine = Get-Content -LiteralPath $localFile | Where-Object { $_ -match '^\s*sdk\.dir\s*=' } | Select-Object -First 1
        if ($sdkLine) {
            $value = ($sdkLine -replace '^\s*sdk\.dir\s*=\s*', '').Replace('\:', ':').Replace('\\', '\')
            if (Test-Path -LiteralPath $value -PathType Container) { return [IO.Path]::GetFullPath($value) }
        }
    }
    foreach ($candidate in @($env:ANDROID_HOME, $env:ANDROID_SDK_ROOT, (Join-Path $env:LOCALAPPDATA 'Android\Sdk'), (Join-Path $env:LOCALAPPDATA 'Programs\Android\Sdk'))) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Container)) { return [IO.Path]::GetFullPath($candidate) }
    }
    throw 'Android SDK was not found. Configure Android Studio/local.properties first.'
}

function Assert-TestEndpoints {
    $uri = $null
    if (-not [URI]::TryCreate($Server, [UriKind]::Absolute, [ref]$uri) -or $uri.Scheme -ne 'http' -or $uri.Host -notin @('10.0.2.2','127.0.0.1','localhost') -or
            $uri.UserInfo -or $uri.Query -or $uri.Fragment -or $uri.AbsolutePath -ne '/') {
        throw 'Mutating device tests require an isolated local HTTP server, never production.'
    }
    $diagnosticUri = $null
    if (-not [URI]::TryCreate($Diagnostic, [UriKind]::Absolute, [ref]$diagnosticUri) -or $diagnosticUri.Scheme -ne 'http' -or
            $diagnosticUri.Host -notin @('10.0.2.2', '127.0.0.1', 'localhost') -or $diagnosticUri.Port -ne 8002 -or
            $diagnosticUri.UserInfo -or $diagnosticUri.Query -or $diagnosticUri.Fragment -or $diagnosticUri.AbsolutePath -ne '/') {
        throw 'Diagnostic must be the local HTTP 8002 root URL without credentials.'
    }
    if ($Serial -notmatch '^[A-Za-z0-9._:-]+$') { throw 'ADB serial contains unsupported characters.' }
}

function Invoke-AdbChecked {
    param([string[]]$Arguments, [string]$LogName)
    $result = Invoke-LoggedNative $taskAdb (@('-s', $Serial) + $Arguments) $LogName
    if ($result.exitCode -ne 0) { throw ('ADB command failed; private log: ' + $result.logPath) }
    return $result
}

function Export-Verification {
    param($Report)
    $json = $Report | ConvertTo-Json -Depth 14
    Set-Content -LiteralPath (Join-Path $taskPrivateRoot 'verification.json') -Value $json -Encoding UTF8
    $temporary = Join-Path $taskEvidenceRoot ('.verification-' + $taskRunId + '.json')
    Set-Content -LiteralPath $temporary -Value $json -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination (Join-Path $taskEvidenceRoot 'verification.json') -Force
}

New-Item -ItemType Directory -Path $taskPrivateRoot -Force | Out-Null
New-Item -ItemType Directory -Path $taskEvidenceRoot -Force | Out-Null
$taskReport = [ordered]@{
    schemaVersion = 1
    runId = $taskRunId
    generatedAtUtc = [DateTime]::UtcNow.ToString('o')
    scope = 'Windows Android build/device verification only; not PythonAnywhere deployment verification'
    mode = $(if ($RunDevice) { 'RunDevice' } else { 'BuildOnly' })
    status = 'failed'
    pythonAnywhereDeploymentVerified = $false
    notes = @('RunDevice uses a provisioned isolated local publisher and creates photos, not accounts. Existing records are not deleted.',
              'Start isolated WSL Django separately. This script never starts/stops an emulator.',
              'BuildOnly does not verify device rendering, server synchronization, or cloud deployment.',
              'Only current-run screenshot hashes in this JSON are verification evidence; older PNG files are not re-verified.')
    environment = [ordered]@{ powershell = $PSVersionTable.PSVersion.ToString(); os = [Environment]::OSVersion.VersionString }
    source = $null
    sourceStable = $false
    build = [ordered]@{ passed = $false; gradleLog = $null; apks = @() }
    unitTests = $null
    lint = $null
    device = [ordered]@{ requested = [bool]$RunDevice; status = 'not_run'; serial = $null; server = $null; diagnostic = $null; tests = 0; classes = @(); screenshots = @() }
    failure = $null
}

try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'This verifier must run on Windows, not WSL.' }
    Assert-TestEndpoints
    $taskReport.source = Get-SourceManifest
    $taskJavaHome = $env:JAVA_HOME
    $studioJbr = Join-Path $env:ProgramFiles 'Android\Android Studio\jbr'
    if (Test-Path -LiteralPath (Join-Path $studioJbr 'bin\java.exe') -PathType Leaf) { $taskJavaHome = $studioJbr }
    $userStudioJbr = Join-Path $env:LOCALAPPDATA 'Programs\Android\android-studio\jbr'
    if ((-not $taskJavaHome -or -not (Test-Path -LiteralPath (Join-Path $taskJavaHome 'bin\java.exe') -PathType Leaf)) -and (Test-Path -LiteralPath (Join-Path $userStudioJbr 'bin\java.exe') -PathType Leaf)) { $taskJavaHome = $userStudioJbr }
    if (-not $taskJavaHome -or -not (Test-Path -LiteralPath (Join-Path $taskJavaHome 'bin\java.exe') -PathType Leaf)) { throw 'JDK was not found. Configure JAVA_HOME or install Android Studio.' }
    $env:JAVA_HOME = $taskJavaHome
    $taskSdk = Get-SdkRoot
    # Finding the SDK for ADB does not configure Gradle. Pass the same resolved
    # directory to child processes without changing any persistent user setting.
    $env:ANDROID_HOME = $taskSdk
    $env:ANDROID_SDK_ROOT = $taskSdk
    $taskAdb = Join-Path $taskSdk 'platform-tools\adb.exe'
    $taskReport.environment.javaHome = $taskJavaHome
    $taskReport.environment.sdkRoot = $taskSdk
    $java = Invoke-LoggedNative (Join-Path $taskJavaHome 'bin\java.exe') @('-version') 'java-version.log'
    if ($java.exitCode -ne 0) { throw 'Unable to read JDK version.' }
    $javaMatch = [regex]::Match($java.text, '(?m)^(?:openjdk|java) version "([0-9A-Za-z+._-]+)"')
    if (-not $javaMatch.Success) { throw 'JDK output did not contain a recognized version.' }
    # Keep raw tool output private: JAVA_TOOL_OPTIONS may contain sensitive properties.
    $taskReport.environment.javaVersion = $javaMatch.Groups[1].Value
    $taskReport.environment.platforms = @(Get-ChildItem -LiteralPath (Join-Path $taskSdk 'platforms') -Directory | Select-Object -ExpandProperty Name)
    $taskReport.environment.buildTools = @(Get-ChildItem -LiteralPath (Join-Path $taskSdk 'build-tools') -Directory | Select-Object -ExpandProperty Name)
    $adbVersion = Invoke-LoggedNative $taskAdb @('version') 'adb-version.log'
    if ($adbVersion.exitCode -ne 0) { throw 'Unable to read ADB version.' }
    $adbMatch = [regex]::Match($adbVersion.text, '(?m)^Android Debug Bridge version ([0-9.]+)')
    if (-not $adbMatch.Success) { throw 'ADB output did not contain a recognized version.' }
    $taskReport.environment.adbVersion = $adbMatch.Groups[1].Value
    $wrapper = Join-Path $taskProjectRoot 'gradlew.bat'
    $gradleVersion = Invoke-LoggedNative $wrapper @('--version', '--offline', '--console=plain') 'gradle-version.log'
    $gradleMatch = [regex]::Match($gradleVersion.text, '(?m)^Gradle\s+([0-9A-Za-z+._-]+)')
    if ($gradleVersion.exitCode -ne 0 -or -not $gradleMatch.Success) { throw 'Unable to read the actual Gradle wrapper version.' }
    $taskReport.environment.gradleVersion = $gradleMatch.Groups[1].Value
    Write-Host 'Verifying Windows Gradle build, unit tests, and lint (offline dependency cache)...'
    $build = Invoke-LoggedNative $wrapper @('assembleDebug', 'assembleDebugAndroidTest', 'testDebugUnitTest', 'lintDebug', '--offline', '--no-daemon', '--console=plain') 'gradle.log'
    $taskReport.build.gradleLog = $build.logPath
    if ($build.exitCode -ne 0 -or $build.text -notmatch 'BUILD SUCCESSFUL') { throw 'Gradle verification failed; see the private gradle.log. Missing offline dependencies require separate environment setup.' }
    $taskReport.unitTests = Get-UnitTestResults
    $taskReport.lint = Get-LintResults
    if (-not $taskReport.unitTests.passed) { throw 'Unit-test XML contains failures/errors/skips or no executed tests.' }
    if (-not $taskReport.lint.passed) { throw 'Debug lint XML contains Error/Fatal findings.' }
    $appApk = Join-Path $taskProjectRoot 'app\build\outputs\apk\debug\app-debug.apk'
    $testApk = Join-Path $taskProjectRoot 'app\build\outputs\apk\androidTest\debug\app-debug-androidTest.apk'
    $taskReport.build.apks = @((Get-ArtifactHash $appApk), (Get-ArtifactHash $testApk))
    $taskReport.build.passed = $true
    if ($RunDevice) {
        $taskReport.device.status = 'failed'; $taskReport.device.serial = $Serial
        $taskReport.device.server = $Server; $taskReport.device.diagnostic = $Diagnostic
        if (-not $env:TEST_OWNER_USERNAME -or -not $env:TEST_OWNER_PASSWORD) { throw 'Set isolated local TEST_OWNER_USERNAME and TEST_OWNER_PASSWORD.' }
        Write-Host 'RunDevice creates test photos with the isolated publisher. Django must already be running.'
        $state = Invoke-AdbChecked @('get-state') 'device-state.log'
        if ($state.text.Trim() -ne 'device') { throw 'Selected ADB device is not ready; no emulator is automatically started.' }
        foreach ($property in @('ro.build.version.sdk', 'ro.build.version.release', 'ro.product.model', 'ro.opengles.version')) {
            $info = Invoke-AdbChecked @('shell', 'getprop', $property) ('device-' + $property + '.log')
            $taskReport.environment[$property] = $info.text.Trim()
        }
        $installApp = Invoke-AdbChecked @('install', '-r', '-t', $appApk) 'install-app.log'
        if ($installApp.text -notmatch '(?m)^Success\s*$') { throw 'ADB did not confirm application installation.' }
        $installTest = Invoke-AdbChecked @('install', '-r', '-t', $testApk) 'install-test.log'
        if ($installTest.text -notmatch '(?m)^Success\s*$') { throw 'ADB did not confirm test application installation.' }
        $classes = @(
            [pscustomobject]@{ name = 'com.haddol7.photoviewer.content.ContentDeviceTest'; expected = 8 },
            [pscustomobject]@{ name = 'com.haddol7.photoviewer.ui.ContentUiTest'; expected = 1 }
        )
        foreach ($class in $classes) {
            $test = Invoke-LoggedNative $taskAdb @('-s', $Serial, 'shell', 'am', 'instrument', '-w', '-e', 'class', $class.name,
                '-e', 'server', $Server, '-e', 'diagnostic', $Diagnostic,
                '-e', 'owner', $env:TEST_OWNER_USERNAME, '-e', 'password', $env:TEST_OWNER_PASSWORD,
                'com.haddol7.photoviewer.assessment02.test/android.test.InstrumentationTestRunner') ($class.name + '.log')
            $verdict = Get-InstrumentationVerdict $test.exitCode $test.text $class.expected
            $taskReport.device.classes += [pscustomobject]@{ name = $class.name; passed = $verdict.passed; expected = $class.expected; tests = $verdict.tests; logPath = $test.logPath }
            if (-not $verdict.passed) { throw ('Instrumentation did not confirm OK(' + $class.expected + ' tests): ' + $class.name) }
            $taskReport.device.tests += $verdict.tests
        }
        if ($taskReport.device.tests -ne 9) { throw 'Expected nine current real device tests.' }
        $staging = Join-Path $taskPrivateRoot 'screenshots'
        New-Item -ItemType Directory -Path $staging -Force | Out-Null
        foreach ($filename in @('content-start.png','content-face-preview.png','content-tags.png','content-classification-ocr.png','content-ocr-keyboard.png',
                'content-published.png','content-search-results.png','content-match-highlight.png')) {
            $local = Join-Path $staging $filename
            $pull = Invoke-AdbChecked @('pull', ('/sdcard/Android/data/com.haddol7.photoviewer.assessment02/files/evidence/' + $filename), $local) ('pull-' + $filename + '.log')
            $bytes = [IO.File]::ReadAllBytes($local)
            if ($bytes.Length -lt 24 -or [Convert]::ToBase64String($bytes, 0, 8) -ne 'iVBORw0KGgo=') { throw 'Pulled screenshot is not a PNG.' }
            $publicPath = Join-Path $taskEvidenceRoot $filename
            Copy-Item -LiteralPath $local -Destination $publicPath -Force
            $taskReport.device.screenshots += Get-ArtifactHash $publicPath
        }
        $taskReport.device.status = 'passed'
    }
    $after = Get-SourceManifest
    $taskReport.sourceStable = $after.sha256 -eq $taskReport.source.sha256
    if (-not $taskReport.sourceStable) { throw 'Source/assets changed while verification ran; rerun against a stable source tree.' }
    $apkAfter = @((Get-ArtifactHash $appApk), (Get-ArtifactHash $testApk))
    for ($index = 0; $index -lt $apkAfter.Count; $index++) {
        if ($apkAfter[$index].sha256 -ne $taskReport.build.apks[$index].sha256) {
            throw 'An APK changed after verification/install started; rerun without concurrent builds.'
        }
    }
    $taskReport.status = 'passed'
} catch {
    $taskReport.failure = $_.Exception.Message
    Write-Warning ('Verification failed: ' + $_.Exception.Message)
} finally {
    $env:JAVA_HOME = $taskOriginalJavaHome
    $env:ANDROID_HOME = $taskOriginalAndroidHome
    $env:ANDROID_SDK_ROOT = $taskOriginalAndroidSdkRoot
    Export-Verification $taskReport
}

Write-Host ('Verification JSON: ' + (Join-Path $taskEvidenceRoot 'verification.json'))
if ($taskReport.status -ne 'passed') { exit 1 }
Write-Host ('PASS (' + $taskReport.mode + '); PythonAnywhere deployment is not verified by this script.')
