[CmdletBinding()]
param(
    [ValidateSet('Menu','Setup','Verify','Sample','Webcam','Monitor','Video','LocalServer','Cloud')]
    [string]$Action = 'Menu',
    [string]$Distribution = '',
    [string]$Source = '0',
    [switch]$InstallWsl
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if ($Action -eq 'Menu') {
    Write-Host '공통평가 02 노트북 실행'
    Write-Host '1. 최초 환경 설치'
    Write-Host '2. 파일과 실행 환경 검사'
    Write-Host '3. 동봉 영상으로 로컬 분석 (서버 전송 없음)'
    Write-Host '4. 평가용 원본 YOLO 웹캠 검출 (서버 전송 없음)'
    Write-Host '5. 웹캠 관측을 운영 서버에 등록'
    Write-Host '6. 영상 관측을 운영 서버에 등록'
    Write-Host '7. 로컬 Django 서버 실행'
    Write-Host '8. 운영 웹사이트 열기'
    $selection = Read-Host '번호'
    $actions = @{'1'='Setup';'2'='Verify';'3'='Sample';'4'='Webcam';'5'='Monitor';'6'='Video';'7'='LocalServer';'8'='Cloud'}
    if (-not $actions.ContainsKey($selection)) { throw '메뉴 번호를 확인하세요.' }
    $Action = $actions[$selection]
    if ($Action -eq 'Video') { $Source = Read-Host '분석할 영상의 Windows 전체 경로' }
}
if ($Action -eq 'Cloud') { Start-Process 'https://daejinha.pythonanywhere.com/'; exit 0 }
if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw '관리자 PowerShell에서 wsl --install -d Ubuntu-24.04 실행 후 재부팅하세요. START_HERE.md 참고.'
}
$installed = @(& wsl.exe --list --quiet 2>$null | ForEach-Object { $_.Replace([string][char]0,'').Trim() } | Where-Object { $_ })
if ($LASTEXITCODE -ne 0) { throw 'WSL 목록을 읽지 못했습니다. wsl --status를 확인하세요.' }
if (-not $Distribution) {
    if ('Ubuntu-24.04' -in $installed) { $Distribution = 'Ubuntu-24.04' }
    elseif ('Ubuntu' -in $installed) { $Distribution = 'Ubuntu' }
}
if (-not $Distribution -or $Distribution -notin $installed) {
    if (-not $InstallWsl) {
        throw 'Ubuntu가 없습니다. 관리자 PowerShell에서 .\Start-Laptop.ps1 -Action Setup -InstallWsl 을 실행하세요.'
    }
    & wsl.exe --install -d Ubuntu-24.04 --no-launch
    if ($LASTEXITCODE -ne 0) { throw 'WSL 설치를 완료한 후 재부팅하고 다시 실행하세요.' }
    Write-Host 'Ubuntu-24.04를 한 번 열어 Linux 사용자와 비밀번호를 만든 뒤 START.cmd를 다시 실행하세요.'
    exit 0
}
$wslRoot = (& wsl.exe -d $Distribution --exec wslpath -a -u $taskRoot).Trim()
if ($LASTEXITCODE -ne 0 -or -not $wslRoot.StartsWith('/mnt/')) { throw 'Windows 소스 폴더의 WSL 경로 변환 실패.' }
if ($Action -eq 'Video') {
    $resolvedVideo = (Resolve-Path -LiteralPath $Source).Path
    $Source = (& wsl.exe -d $Distribution --exec wslpath -a -u $resolvedVideo).Trim()
    if ($LASTEXITCODE -ne 0) { throw '영상 경로 변환 실패.' }
}
& wsl.exe -d $Distribution --exec bash "$wslRoot/laptop/run.sh" $Action $Source
if ($LASTEXITCODE -ne 0) { throw "WSL 실행 실패 ($LASTEXITCODE). 위 오류를 확인하세요. Windows Python으로 전환하지 않습니다." }
