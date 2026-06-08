$cred = "Basic " + [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("admin:admin"))
$queries = @(
  "legal_classifier_request_total",
  "legal_classifier_prediction_label_total",
  "legal_classifier_prediction_confidence",
  "rate(legal_classifier_prediction_latency_seconds_count[1m])"
)
foreach ($q in $queries) {
  $url = "http://localhost:3000/api/datasources/proxy/1/api/v1/query?query=" + [uri]::EscapeDataString($q)
  $resp = Invoke-WebRequest -UseBasicParsing -Uri $url -Headers @{Authorization=$cred}
  Write-Output ("=== {0} ===" -f $q)
  Write-Output ($resp.Content.Substring(0, [Math]::Min($resp.Content.Length, 240)))
  Write-Output ""
}
