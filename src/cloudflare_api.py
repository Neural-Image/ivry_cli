import os
from dotenv import load_dotenv
import requests

import base64

load_dotenv()

def create_hostname(identifier, target_content):
    # api_email=os.environ.get("CLOUDFLARE_EMAIL")
    api_key = os.environ.get("CLOUDFLARE_DNS_API_TOKEN")
    zone_id = os.environ.get("ZONE_ID")

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

def create_tunnel(identifier):
    # api_email=os.environ.get("CLOUDFLARE_EMAIL")
    api_key = os.environ.get("CLOUDFLARE_TUNNEL_API_TOKEN")
    account_id = os.environ.get("ACCOUNT_ID")

    res = requests.post(
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/cfd_tunnel",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json={
            "name": identifier,
            "config_src": "local",
        },
    )
    res.raise_for_status()

if __name__ == "__main__":
    # create_hostname("identifier-1234")
    create_tunnel("identifier-1234")