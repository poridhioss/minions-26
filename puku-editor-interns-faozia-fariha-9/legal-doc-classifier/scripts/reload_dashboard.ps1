$cred = "Basic " + [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("admin:admin"))
$body = Get-Content "E:\Projects\legal-doc-classifier\grafana\dashboards\dashboard.json" -Raw
$dashboard = ConvertFrom-Json $body
# /api/dashboards/db expects: { dashboard, message, overwrite, folderId }
$payload = @{
  dashboard = $dashboard
  message   = "Fix datasource uid"
  overwrite = $true
  folderId  = 0
} | ConvertTo-Json -Depth 50
$payload | Set-Content "E:\Projects\legal-doc-classifier\scripts\payload.json" -Encoding UTF8
Invoke-WebRequest -UseBasicParsing -Method Post `
  -Uri "http://localhost:3000/api/dashboards/db" `
  -Headers @{Authorization=$cred} `
  -ContentType "application/json" `
  -InFile "E:\Projects\legal-doc-classifier\scripts\payload.json"
