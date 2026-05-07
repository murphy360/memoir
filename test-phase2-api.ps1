#!/usr/bin/env pwsh
# Phase 2 API validation: threads on epics/events, not periods
$BASE = "http://localhost:8001"
$pass = 0; $fail = 0
$run  = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()

function Check($label, $cond) {
    if ($cond) { Write-Host "  PASS  $label" -ForegroundColor Green; $script:pass++ }
    else        { Write-Host "  FAIL  $label" -ForegroundColor Red;   $script:fail++ }
}
function HttpPost($path, $body) {
    Invoke-RestMethod "$BASE$path" -Method Post -Body ($body | ConvertTo-Json) -ContentType "application/json"
}
function HttpPatch($path, $body) {
    Invoke-RestMethod "$BASE$path" -Method Patch -Body ($body | ConvertTo-Json) -ContentType "application/json"
}
function HttpGet($path)  { Invoke-RestMethod "$BASE$path" -Method Get }
function HttpDelete($path) {
    try { Invoke-RestMethod "$BASE$path" -Method Delete } catch {}
}

Write-Host "`n=== Phase 2 API Validation (run $run) ===" -ForegroundColor Cyan

# Titles unique per run to survive re-runs
$threadTitle = "TestThread-$run"
$periodTitle = "TestPeriod-$run"
$epicTitle   = "TestEpic-$run"
$eventTitle  = "TestEvent-$run"

# -- Threads -----------------------------------------------------------------
Write-Host "`n--- Threads ---"
$thread = HttpPost "/api/threads" @{ title = $threadTitle; summary = $null }
Check "Create thread returns id"            ($thread.id -gt 0)
Check "Thread has event_count field"        ($thread.PSObject.Properties.Name -contains "event_count")
Check "Thread has epic_count field"         ($thread.PSObject.Properties.Name -contains "epic_count")
Check "Thread has no period_count field"    (-not ($thread.PSObject.Properties.Name -contains "period_count"))

# -- Periods ------------------------------------------------------------------
Write-Host "`n--- Periods ---"
$period = HttpPost "/api/periods" @{ title = $periodTitle; start_date_text = "2020"; end_date_text = "2022"; summary = $null }
Check "Create period returns id"            ($period.id -gt 0)
Check "Period has no thread_id field"       (-not ($period.PSObject.Properties.Name -contains "thread_id"))

# -- Epics --------------------------------------------------------------------
Write-Host "`n--- Epics ---"
$epic = HttpPost "/api/epics" @{ period_id = $period.id; title = $epicTitle; description = $null; weight = 5; start_date_text = $null; end_date_text = $null }
Check "Create epic returns id"              ($epic.id -gt 0)
Check "Epic has thread_id field"            ($epic.PSObject.Properties.Name -contains "thread_id")
Check "Epic thread_id starts null"          ($null -eq $epic.thread_id)

$epicPatched = HttpPatch "/api/epics/$($epic.id)" @{ thread_id = $thread.id }
Check "Patch epic sets thread_id"           ($epicPatched.thread_id -eq $thread.id)

$threads = HttpGet "/api/threads"
$threadNow = $threads | Where-Object { $_.id -eq $thread.id }
Check "Thread epic_count incremented to 1"  ($threadNow.epic_count -eq 1)

$epicCleared = HttpPatch "/api/epics/$($epic.id)" @{ thread_id = $null }
Check "Clear epic thread_id to null"        ($null -eq $epicCleared.thread_id)

# -- Events -------------------------------------------------------------------
Write-Host "`n--- Events ---"
$event = HttpPost "/api/events" @{ title = $eventTitle; period_id = $period.id; epic_id = $null; weight = 5; description = $null; location = $null; event_date_text = "Summer 2021" }
Check "Create event returns id"             ($event.id -gt 0)
Check "Event has thread_id field"           ($event.PSObject.Properties.Name -contains "thread_id")
Check "Event thread_id starts null"         ($null -eq $event.thread_id)

$eventPatched = HttpPatch "/api/events/$($event.id)" @{ thread_id = $thread.id }
Check "Patch event sets thread_id"          ($eventPatched.thread_id -eq $thread.id)

$threads = HttpGet "/api/threads"
$threadNow = $threads | Where-Object { $_.id -eq $thread.id }
Check "Thread event_count incremented to 1" ($threadNow.event_count -eq 1)

$eventCleared = HttpPatch "/api/events/$($event.id)" @{ thread_id = $null }
Check "Clear event thread_id to null"       ($null -eq $eventCleared.thread_id)

# -- Delete thread cascade -----------------------------------------------------
Write-Host "`n--- Thread delete cascade ---"
$t2 = HttpPost "/api/threads" @{ title = "TestThreadDel-$run"; summary = $null }
HttpPatch "/api/epics/$($epic.id)"   @{ thread_id = $t2.id } | Out-Null
HttpPatch "/api/events/$($event.id)" @{ thread_id = $t2.id } | Out-Null
HttpDelete "/api/threads/$($t2.id)"
$epics  = HttpGet "/api/epics"
$events = HttpGet "/api/events"
$epicAfterDel  = $epics  | Where-Object { $_.id -eq $epic.id }
$eventAfterDel = $events | Where-Object { $_.id -eq $event.id }
Check "Epic thread_id cleared when thread deleted"  ($null -eq $epicAfterDel.thread_id)
Check "Event thread_id cleared when thread deleted" ($null -eq $eventAfterDel.thread_id)

# -- Cleanup -------------------------------------------------------------------
Write-Host "`n--- Cleanup ---"
HttpDelete "/api/events/$($event.id)"
HttpDelete "/api/epics/$($epic.id)"
HttpDelete "/api/periods/$($period.id)"
HttpDelete "/api/threads/$($thread.id)"
Write-Host "  (test data removed)"

# -- Summary -------------------------------------------------------------------
Write-Host ""
$color = if ($fail -eq 0) { "Green" } else { "Yellow" }
Write-Host "Results: $pass passed, $fail failed" -ForegroundColor $color
if ($fail -gt 0) { exit 1 }
