$url = "https://backend-production-818f.up.railway.app/api/keeta/orders"
try {
    $resp = Invoke-WebRequest -Uri $url -Method GET -UseBasicParsing
    Write-Output ("STATUS: " + $resp.StatusCode)
} catch {
    $we = $_.Exception
    if ($we.Response) {
        Write-Output ("ERROR STATUS: " + [int]$we.Response.StatusCode)
    } else {
        Write-Output ("NO RESPONSE: " + $we.Message)
    }
}

Write-Output "---POST TEST---"
try {
    $body = '{"eventType":"CREATED","orderId":"test123"}'
    $resp2 = Invoke-WebRequest -Uri $url -Method POST -Body $body -ContentType "application/json" -UseBasicParsing
    Write-Output ("STATUS: " + $resp2.StatusCode)
    Write-Output ("BODY: " + $resp2.Content)
} catch {
    $we2 = $_.Exception
    if ($we2.Response) {
        Write-Output ("ERROR STATUS: " + [int]$we2.Response.StatusCode)
        $stream = $we2.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        Write-Output ("ERROR BODY: " + $reader.ReadToEnd())
    } else {
        Write-Output ("NO RESPONSE: " + $we2.Message)
    }
}
