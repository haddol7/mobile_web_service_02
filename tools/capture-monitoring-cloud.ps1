[CmdletBinding()]
param([string]$Serial='emulator-5554',[switch]$VisualReview)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskAdb='C:\Users\1\AppData\Local\Programs\Android\Sdk\platform-tools\adb.exe'
$taskOut=Join-Path $taskRoot 'evidence/ui-audit/cloud'
function Adb([string[]]$Arguments){$result=(& $taskAdb -s $Serial @Arguments 2>&1|Out-String);if($LASTEXITCODE -ne 0){throw $result};return $result}
function Capture([string]$Path,[string]$Expected,[string]$Name){
    $null=Adb @('shell','am','start','-a','android.intent.action.VIEW','-d',('https://daejinha.pythonanywhere.com'+$Path),'-p','com.android.chrome')
    $ready=$false
    for($attempt=0;$attempt -lt 12;$attempt++){
        $null=Adb @('shell','uiautomator','dump','/sdcard/common02-cloud-capture.xml')
        $raw=Adb @('shell','cat','/sdcard/common02-cloud-capture.xml');$tree=[xml]$raw
        $heading=$tree.SelectNodes('//node[@text!=""]')|Where-Object {$_.text -eq $Expected}|Select-Object -Last 1
        if($null -eq $heading){
            if($VisualReview -and $attempt -ge 2 -and $raw.Contains('daejinha.pythonanywhere.com') -and $null -eq $tree.SelectSingleNode('//node[@class="android.widget.ProgressBar"]')){$ready=$true;break}
            continue
        }
        if($raw -match 'Translate page\?|Open tabs to visit different pages'){
            if($heading.bounds -match '^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$'){
                $x=[int](([int]$Matches[1]+[int]$Matches[3])/2);$y=[int](([int]$Matches[2]+[int]$Matches[4])/2)
                $null=Adb @('shell','input','tap',([string]$x),([string]$y))
            }
            continue
        }
        if($null -ne $tree.SelectSingleNode('//node[@class="android.widget.ProgressBar"]')){continue}
        $ready=$true;break
    }
    if(-not $ready){throw ('Chrome capture not ready: '+$Path)}
    $null=Adb @('shell','screencap','-p','/sdcard/common02-cloud-capture.png')
    $null=Adb @('pull','/sdcard/common02-cloud-capture.png',(Join-Path $taskOut $Name))
    [IO.File]::WriteAllText((Join-Path $taskOut ($Name+'.xml')),$raw,[Text.UTF8Encoding]::new($false))
    Write-Output ('CAPTURE: Chrome '+$Path+'; visual review required')
}
Capture '/' '관제 현황' 'mobile-web-dashboard.png'
Capture '/detections/' '감지 기록' 'mobile-web-list.png'
$proof=Get-Content (Join-Path $taskRoot 'evidence/cloud/verification.json') -Raw|ConvertFrom-Json
Capture ('/post/'+$proof.new_post.id+'/') $proof.new_post.title 'mobile-web-detail.png'
Capture '/api_root/' 'Api Root' 'api-root-browser.png'
