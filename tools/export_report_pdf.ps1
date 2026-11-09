param([Parameter(Mandatory=$true)][string]$InputDocx,[Parameter(Mandatory=$true)][string]$OutputPdf)
$ErrorActionPreference='Stop'
$taskWord=$null
$taskDocument=$null
try {
    $taskWord=New-Object -ComObject Word.Application
    $taskWord.Visible=$false
    $taskWord.DisplayAlerts=0
    $taskDocument=$taskWord.Documents.Open([IO.Path]::GetFullPath($InputDocx),$false,$true)
    $taskDocument.Repaginate()
    $taskDocument.ExportAsFixedFormat([IO.Path]::GetFullPath($OutputPdf),17)
    Write-Output ('PDF exported: '+[IO.Path]::GetFileName($OutputPdf))
} finally {
    if($null -ne $taskDocument){$taskDocument.Close(0);[void][Runtime.InteropServices.Marshal]::ReleaseComObject($taskDocument)}
    if($null -ne $taskWord){$taskWord.Quit();[void][Runtime.InteropServices.Marshal]::ReleaseComObject($taskWord)}
}
