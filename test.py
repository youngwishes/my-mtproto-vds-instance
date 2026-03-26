import os
import uuid
import httpx

secret = str(os.urandom(16).hex())
response = httpx.post(
    "http://127.0.0.1:8000/api/v2/add-new-user",
    json={
        "username": str(uuid.uuid4()),
        "secret": secret,
    }
)
print(response.json())