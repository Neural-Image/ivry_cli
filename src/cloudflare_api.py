import os
from dotenv import load_dotenv
import requests

load_dotenv()

def create_hostname(identifier):
    # api_email=os.environ.get("CLOUDFLARE_EMAIL")
    api_key = os.environ.get("CLOUDFLARE_API_KEY")
    zone_id = os.environ.get("ZONE_ID")
    target_content = os.environ.get("TARGET_CONTENT")

    res = requests.post(
        f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json={
            "name": identifier,
            "proxied": True,
            "content": target_content,
            "type": "CNAME",
        },
    )

if __name__ == "__main__":
    create_hostname("identifier-1234")