import hmac, hashlib, base64

CLIENT_SECRET = "2f6729bdd4be467aa15df35244f2a65e"
url = "https://backend-production-818f.up.railway.app/api/keeta/orders"
body = '{"eventType":"CREATED","orderId":"test123"}'

string_to_sign = f"{url}&{body}"
sig = base64.b64encode(hmac.new(CLIENT_SECRET.encode(), string_to_sign.encode(), hashlib.sha256).digest()).decode()
print("URL+BODY signature:", sig)

sig2 = base64.b64encode(hmac.new(CLIENT_SECRET.encode(), body.encode(), hashlib.sha256).digest()).decode()
print("BODY-only signature:", sig2)
