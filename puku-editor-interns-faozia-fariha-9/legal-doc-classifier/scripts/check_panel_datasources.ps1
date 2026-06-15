$cred = "Basic " + [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("admin:admin"))
$resp = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:3000/api/dashboards/uid/ffoewf4vz59tsa" -Headers @{Authorization=$cred}
$dash = $resp.Content | ConvertFrom-Json
foreach ($p in $dash.dashboard.panels) {
  Write-Output ("panel {0} '{1}' -> datasource: {2}" -f $p.id, $p.title, ($p.datasource | ConvertTo-Json -Compress))
}
