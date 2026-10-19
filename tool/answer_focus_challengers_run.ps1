# Sequential, resumable offline research. Launch hidden; no application changes.
$researchRoot = Split-Path -Parent $PSScriptRoot
$researchOut = Join-Path $researchRoot 'local-benchmarks/answer-focus-challengers'
$researchPython = Join-Path $researchRoot '.venv/Scripts/python.exe'
$researchScript = Join-Path $PSScriptRoot 'answer_focus_challengers.py'
New-Item -ItemType Directory -Force -Path $researchOut | Out-Null
Set-Location -LiteralPath $researchRoot
$researchProcess = Get-Process -Id $PID
$researchProcess.PriorityClass = 'BelowNormal'
$researchStarted = (Get-Date).ToUniversalTime().ToString('o')
foreach ($researchAction in @('qwen', 'nemotron', 'review')) {
    $researchLog = Join-Path $researchOut ($researchAction + '.log')
    @{ status='running'; action=$researchAction; pid=$PID; started_utc=$researchStarted;
       updated_utc=(Get-Date).ToUniversalTime().ToString('o'); log=$researchLog } |
        ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $researchOut 'run-status.json')
    & $researchPython -I -u $researchScript $researchAction 2>&1 | Out-File -Encoding UTF8 -LiteralPath $researchLog
    $researchExit = $LASTEXITCODE
    if ($researchExit -ne 0) {
        @{ status='failed'; action=$researchAction; exit_code=$researchExit; pid=$PID;
           updated_utc=(Get-Date).ToUniversalTime().ToString('o'); log=$researchLog } |
            ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $researchOut 'run-status.json')
        exit $researchExit
    }
}
@{ status='inference_complete_review_pending'; pid=$PID; started_utc=$researchStarted;
   updated_utc=(Get-Date).ToUniversalTime().ToString('o') } |
    ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $researchOut 'run-status.json')
