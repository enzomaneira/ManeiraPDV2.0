$secret = "2f6729bdd4be467aa15df35244f2a65e"
$url = "https://backend-production-818f.up.railway.app/api/keeta/orders"
$body = '{"eventType":"CREATED","orderId":"test123"}'

function Get-HmacSha256Base64($message, $key) {
    $hmac = New-Object System.Security.Cryptography.HMACSHA256
    $hmac.Key = [System.Text.Encoding]::UTF8.GetBytes($key)
    $hashBytes = $hmac.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($message))
    return [System.Convert]::ToBase64String($hashBytes)
}

$sigBodyOnly = Get-HmacSha256Base64 $body $secret
Write-Output ("BODY-only signature: " + $sigBodyOnly)

Write-Output "---SENDING REQUEST WITH BODY-ONLY SIGNATURE (deve funcionar no codigo atualmente em producao)---"
try {
    $headers = @{ "X-App-Signature" = $sigBodyOnly }
    $resp = Invoke-WebRequest -Uri $url -Method POST -Body $body -ContentType "application/json" -Headers $headers -UseBasicParsing
    Write-Output ("STATUS: " + $resp.StatusCode)
    Write-Output ("BODY: " + $resp.Content)
} catch {
    $we = $_.Exception
    if ($we.Response) {
        Write-Output ("ERROR STATUS: " + [int]$we.Response.StatusCode)
        $stream = $we.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        Write-Output ("ERROR BODY: " + $reader.ReadToEnd())
    } else {
        Write-Output ("NO RESPONSE: " + $we.Message)
    }
}
