$cred = "Basic " + [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("admin:admin"))
$resp = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:3000/api/search?query=Legal" -Headers @{Authorization=$cred}
Write-Output $resp.Content
