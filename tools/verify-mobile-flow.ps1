[CmdletBinding()]
param([string]$Serial='emulator-5554',[switch]$CaptureWeb)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskSdk=if($env:ANDROID_HOME){$env:ANDROID_HOME}else{Join-Path $env:LOCALAPPDATA 'Programs\Android\Sdk'}
$taskAdb=Join-Path $taskSdk 'platform-tools\adb.exe'
$taskOut=Join-Path $taskRoot 'evidence\mobile-flow'
$taskBackend=$null
New-Item -ItemType Directory -Path $taskOut -Force | Out-Null
function Invoke-Adb {
    param([string[]]$Arguments)
    $result=@(& $taskAdb -s $Serial @Arguments 2>&1 | ForEach-Object {$_.ToString()})
    if($LASTEXITCODE -ne 0){throw ('ADB failed: '+($result -join ' '))}
    return $result -join "`n"
}
function Capture-WebPage {
    param([string]$Url,[string]$Name)
    $null=Invoke-Adb @('shell','am','start','-a','android.intent.action.VIEW','-d',$Url,'-p','com.android.chrome')
    $ready=$false
    for($attempt=0;$attempt -lt 12;$attempt++){
        $null=Invoke-Adb @('shell','uiautomator','dump','/sdcard/common02-mobile-flow.xml')
        $xml=Invoke-Adb @('shell','cat','/sdcard/common02-mobile-flow.xml')
        if($xml.Contains('Translate page?') -and $xml.Contains('com.android.chrome')){
            $tree=[xml]$xml
            $heading=$tree.SelectSingleNode("//node[@text='사진과 이야기를 함께']")
            if($null -ne $heading -and $heading.bounds -match '^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$'){
                $x=[int](([int]$Matches[1]+[int]$Matches[3])/2);$y=[int](([int]$Matches[2]+[int]$Matches[4])/2)
                $null=Invoke-Adb @('shell','input','tap',([string]$x),([string]$y))
            }
            Start-Sleep -Seconds 3
            continue
        }
        if($xml.Contains('YOLO: person, bus') -and $xml.Contains('com.android.chrome')){$ready=$true;break}
        # Decline Chrome's optional notification promotion; never grant a permission.
        if($xml.Contains('Chrome notifications make things easier')){
            $tree=[xml]$xml
            $button=$tree.SelectSingleNode("//node[@resource-id='com.android.chrome:id/negative_button' and @text='No thanks']")
            if($null -ne $button -and $button.bounds -match '^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$'){
                $x=[int](([int]$Matches[1]+[int]$Matches[3])/2);$y=[int](([int]$Matches[2]+[int]$Matches[4])/2)
                $null=Invoke-Adb @('shell','input','tap',([string]$x),([string]$y));continue
            }
        }
        if($xml -match 'Accept.*continue|동의.*계속|Terms of Service'){throw 'Chrome first-run agreement needs the user; no agreement was accepted automatically.'}
    }
    if(-not $ready){throw 'The actual Chrome page did not display the expected YOLO photo title.'}
    $null=Invoke-Adb @('shell','screencap','-p',('/sdcard/'+$Name))
    $null=Invoke-Adb @('pull',('/sdcard/'+$Name),(Join-Path $taskOut $Name))
}
try{
    if((Invoke-Adb @('get-state')).Trim() -ne 'device'){throw 'Start the selected Android emulator first.'}
    $taskLinuxRoot=(& wsl.exe -d Ubuntu --exec wslpath -a $taskRoot).Trim()
    if($LASTEXITCODE -ne 0){throw 'WSL source path resolution failed.'}
    $taskPython='/home/daeha/.venvs/mobile_web_service_02/bin/python'
    if(-not (Test-Path (Join-Path $taskRoot 'evidence\private\local\db.sqlite3'))){
        & wsl.exe -d Ubuntu --cd $taskLinuxRoot -- $taskPython tools/verify_yolo_pipeline.py
        if($LASTEXITCODE -ne 0){throw 'The real YOLO fixture verification failed.'}
    }
    $proof=Get-Content (Join-Path $taskRoot 'evidence\yolo-pipeline\verification.json') -Raw | ConvertFrom-Json
    $expected=$proof.real_pipeline.uploads[0]
    $build=Get-Content (Join-Path $taskRoot 'evidence\content\android\verification.json') -Raw | ConvertFrom-Json
    if($build.status -ne 'passed'){throw 'Run PhotoViewer/tools/verify-android.ps1 before device verification.'}
    foreach($apk in $build.build.apks){
        $file=Join-Path $taskRoot $apk.path
        if((Get-FileHash $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $apk.sha256){throw 'APK differs from the verified build.'}
        $installed=Invoke-Adb @('install','-r','-t',$file)
        if($installed -notmatch '(?m)^Success\s*$'){throw 'ADB did not confirm APK installation.'}
    }
    $info=[Diagnostics.ProcessStartInfo]::new('wsl.exe')
    foreach($value in @('-d','Ubuntu','--cd',$taskLinuxRoot,'--',$taskPython,'-u','tools/serve_verified_fixture.py')){$info.ArgumentList.Add($value)}
    $info.UseShellExecute=$false;$info.CreateNoWindow=$true
    $info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    $taskBackend=[Diagnostics.Process]::new();$taskBackend.StartInfo=$info
    if(-not $taskBackend.Start()){throw 'WSL fixture server could not be started.'}
    $readyLine=$taskBackend.StandardOutput.ReadLineAsync()
    if(-not $readyLine.Wait(20000)){throw 'WSL fixture server did not become ready.'}
    if(-not $readyLine.Result){throw 'WSL fixture server exited before readiness.'}
    $ready=$readyLine.Result | ConvertFrom-Json
    if(-not $ready.ready){throw 'Unexpected WSL fixture readiness response.'}
    $origin='http://10.0.2.2:'+$ready.port+'/'
    $result=Invoke-Adb @('shell','am','instrument','-w','-e','class','com.haddol7.photoviewer.ui.YoloSyncTest',
        '-e','server',$origin,'-e','post_id',([string]$expected.id),'-e','image_sha256',$expected.image_sha256,
        'com.haddol7.photoviewer.assessment02.test/android.test.InstrumentationTestRunner')
    [IO.File]::WriteAllText((Join-Path $taskOut 'android-test.txt'),$result,[Text.UTF8Encoding]::new($false))
    if($result -notmatch 'OK \(1 test\)' -or $result -match 'FAILURES|INSTRUMENTATION_FAILED'){throw 'Native YOLO synchronization test failed.'}
    foreach($name in @('yolo-native-list.png','yolo-native-detail.png','yolo-sync.json')){
        $null=Invoke-Adb @('pull',('/sdcard/Android/data/com.haddol7.photoviewer.assessment02/files/evidence/'+$name),(Join-Path $taskOut $name))
    }
    if($CaptureWeb){
        Capture-WebPage $origin 'yolo-mobile-web-list.png'
        Capture-WebPage ($origin+'post/'+$expected.id+'/') 'yolo-mobile-web-detail.png'
    }
    $record=[ordered]@{verified_utc=(Get-Date).ToUniversalTime().ToString('o');environment='Windows Android with WSL Django';
        server=$origin;native_test_pass=$true;native_tests=1;web_captured=[bool]$CaptureWeb;post_id=$expected.id;
        image_sha256=$expected.image_sha256;screenshots=@()}
    foreach($file in Get-ChildItem -LiteralPath $taskOut -Filter '*.png' -File){
        $record.screenshots+=@{file=$file.Name;sha256=(Get-FileHash $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
    }
    $record | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $taskOut 'verification.json') -Encoding utf8
    Write-Host ('PASS: native YOLO synchronization; mobile web captured = '+[bool]$CaptureWeb)
}finally{
    if($null -ne $taskBackend -and -not $taskBackend.HasExited){
        $taskBackend.StandardInput.WriteLine('stop');$taskBackend.StandardInput.Close()
        if(-not $taskBackend.WaitForExit(15000)){throw 'The owned WSL fixture server did not stop; inspect before rerunning.'}
    }
    if($null -ne $taskBackend){$taskBackend.Dispose()}
}
