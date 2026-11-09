[CmdletBinding()]
param([ValidateSet('before','after')][string]$Phase='before', [ValidateSet('regular','small')][string[]]$Sizes=@('regular','small'), [string]$Serial='emulator-5554', [switch]$WebOnly)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskAdb=Join-Path $env:LOCALAPPDATA 'Programs\Android\Sdk\platform-tools\adb.exe'
$taskDeviceConfig='/sdcard/Android/data/com.haddol7.photoviewer.assessment02/files/ui-audit-config.json'
$taskDeviceEvidence='/sdcard/Android/data/com.haddol7.photoviewer.assessment02/files/ui-audit'
function Invoke-Adb([string[]]$Arguments){$result=(& $taskAdb -s $Serial @Arguments 2>&1|Out-String);if($LASTEXITCODE -ne 0){throw "ADB failed: $result"};return $result}
$taskSize=Invoke-Adb @('shell','wm','size');$taskDensity=Invoke-Adb @('shell','wm','density')
$taskBackend=$null
$taskPublic=Join-Path $taskRoot 'evidence\ui-audit'
$null=New-Item -ItemType Directory -Path $taskPublic -Force
$taskResults=@()
try{
    $taskBuild=Get-Content (Join-Path $taskRoot 'evidence\content\android\verification.json') -Raw|ConvertFrom-Json
    if($taskBuild.status -ne 'passed'){throw 'Android build must pass first.'}
    foreach($apk in $taskBuild.build.apks){$null=Invoke-Adb @('install','-r','-t',(Join-Path $taskRoot $apk.path))}
    $taskLinux=(& wsl.exe -d Ubuntu --exec wslpath -a $taskRoot).Trim()
    foreach($taskScreenSize in $Sizes){
        $taskPixels=if($taskScreenSize -eq 'regular'){'1080x1920'}else{'840x1470'}
        $taskDpi=if($taskScreenSize -eq 'regular'){'440'}else{'420'}
        $null=Invoke-Adb @('shell','wm','size',$taskPixels);$null=Invoke-Adb @('shell','wm','density',$taskDpi)
        $taskInfo=[Diagnostics.ProcessStartInfo]::new('wsl.exe')
        foreach($value in @('-d','Ubuntu','--cd',$taskLinux,'--','/home/daeha/.venvs/mobile_web_service_02/bin/python','-u','tools/serve_ui_audit.py')){$taskInfo.ArgumentList.Add($value)}
        $taskInfo.UseShellExecute=$false;$taskInfo.CreateNoWindow=$true;$taskInfo.RedirectStandardInput=$true;$taskInfo.RedirectStandardOutput=$true;$taskInfo.RedirectStandardError=$true
        $taskBackend=[Diagnostics.Process]::new();$taskBackend.StartInfo=$taskInfo;$null=$taskBackend.Start()
        $taskReadyLine=$taskBackend.StandardOutput.ReadLineAsync()
        if(-not $taskReadyLine.Wait(25000)-or-not $taskReadyLine.Result){throw 'WSL UI fixture did not start.'}
        $taskReady=$taskReadyLine.Result|ConvertFrom-Json
        $taskPrivate=Join-Path $taskRoot $taskReady.fixture
        $taskAuth=Get-Content (Join-Path $taskPrivate 'test-auth.json') -Raw|ConvertFrom-Json
        $null=Invoke-Adb @('reverse',('tcp:'+$taskReady.port),('tcp:'+$taskReady.port))
        $taskConfig=@{server=('http://10.0.2.2:'+$taskReady.port+'/');web_server=('http://localhost:'+$taskReady.port+'/');username=$taskAuth.username;password=$taskAuth.password;phase=$Phase}
        $taskConfigPath=Join-Path $taskPrivate 'device-config.json';[IO.File]::WriteAllText($taskConfigPath,($taskConfig|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
        $null=Invoke-Adb @('shell','mkdir','-p','/sdcard/Android/data/com.haddol7.photoviewer.assessment02/files')
        $null=Invoke-Adb @('push',$taskConfigPath,$taskDeviceConfig)
        $taskTestClass=if($WebOnly){'com.haddol7.photoviewer.ui.UiAuditTest#testWebAllPages'}else{'com.haddol7.photoviewer.ui.UiAuditTest'}
        $taskTest=Invoke-Adb @('shell','am','instrument','-w','-e','class',$taskTestClass,'com.haddol7.photoviewer.assessment02.test/android.test.InstrumentationTestRunner')
        [IO.File]::WriteAllText((Join-Path $taskPrivate 'test-output.txt'),$taskTest,[Text.UTF8Encoding]::new($false))
        $taskScreens=Join-Path $taskPrivate 'captures';$null=New-Item -ItemType Directory -Path $taskScreens -Force
        $null=Invoke-Adb @('pull',$taskDeviceEvidence,$taskScreens)
        $taskExpected=if($WebOnly){'OK \(1 test\)'}else{'OK \(2 tests\)'}
        $taskPass=$taskTest -match $taskExpected -and $taskTest -notmatch 'FAILURES|INSTRUMENTATION_FAILED'
        $taskEntries=@(Get-ChildItem -LiteralPath $taskScreens -Recurse -File|ForEach-Object{@{path=[IO.Path]::GetRelativePath($taskRoot,$_.FullName).Replace('\','/');sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}})
        $taskComposerPass=$null
        if($Phase -eq 'after' -and $taskPass -and -not $WebOnly){
            $taskComposer=Invoke-Adb @('shell','am','instrument','-w','-e','class','com.haddol7.photoviewer.ui.ContentUiTest','-e','server',$taskConfig.server,'-e','owner',$taskAuth.username,'-e','password',$taskAuth.password,'com.haddol7.photoviewer.assessment02.test/android.test.InstrumentationTestRunner')
            [IO.File]::WriteAllText((Join-Path $taskPrivate 'composer-flow-output.txt'),$taskComposer,[Text.UTF8Encoding]::new($false))
            $taskComposerPass=$taskComposer -match 'OK \(1 test\)' -and $taskComposer -notmatch 'FAILURES|INSTRUMENTATION_FAILED'
            $null=Invoke-Adb @('pull','/sdcard/Android/data/com.haddol7.photoviewer.assessment02/files/evidence',(Join-Path $taskPrivate 'composer-flow'))
            $taskPass=$taskPass -and $taskComposerPass
        }
        $taskResults+=@{size=$taskScreenSize;pixels=$taskPixels;density=$taskDpi;pass=$taskPass;composer_flow_pass=$taskComposerPass;fixture=$taskReady.fixture;files=$taskEntries;apk_source_sha256=$taskBuild.source.sha256}
        $taskBackend.StandardInput.WriteLine('stop');$taskBackend.StandardInput.Close();if(-not $taskBackend.WaitForExit(5000)){$taskBackend.Kill($true)};$taskBackend=$null
        $null=Invoke-Adb @('reverse','--remove',('tcp:'+$taskReady.port))
        if(-not $taskPass){throw "UI audit failed for $taskScreenSize. See $taskPrivate/test-output.txt"}
        $taskScope=if($WebOnly){'WebView'}else{'Android native and WebView'}
        Write-Output "PASS: $Phase $taskScreenSize $taskScope capture audit."
    }
}finally{
    if($null -ne $taskBackend -and -not $taskBackend.HasExited){$taskBackend.StandardInput.WriteLine('stop');$taskBackend.StandardInput.Close();if(-not $taskBackend.WaitForExit(5000)){$taskBackend.Kill($true)}}
    $null=& $taskAdb -s $Serial shell rm -f $taskDeviceConfig
    if($null -ne (Get-Variable taskReady -ErrorAction SilentlyContinue)){$null=& $taskAdb -s $Serial reverse --remove ('tcp:'+$taskReady.port) 2>$null}
    $taskRestoreSize=if($taskSize -match 'Override size:\s*(\d+x\d+)'){$Matches[1]}else{'reset'}
    $taskRestoreDensity=if($taskDensity -match 'Override density:\s*(\d+)'){$Matches[1]}else{'reset'}
    $null=& $taskAdb -s $Serial shell wm size $taskRestoreSize;$null=& $taskAdb -s $Serial shell wm density $taskRestoreDensity
    $taskRecord=@{phase=$Phase;web_only=[bool]$WebOnly;verified_utc=(Get-Date).ToUniversalTime().ToString('o');environment='Windows Android emulator and WSL Django';results=$taskResults;external_llm_calls=0;production_verified=$false}
    $taskRecordName=if($WebOnly){$Phase+'-web.json'}else{$Phase+'.json'}
    [IO.File]::WriteAllText((Join-Path $taskPublic $taskRecordName),($taskRecord|ConvertTo-Json -Depth 10),[Text.UTF8Encoding]::new($false))
}
