import yaml
from pathlib import Path
import json
IVRY_CREDENTIAL_DIR = Path.home() / ".ivry"


def get_apikey():
        token_path = IVRY_CREDENTIAL_DIR / "token.txt"
        if token_path.exists():
            with open(IVRY_CREDENTIAL_DIR / "token.txt", "r", encoding="utf-8") as f:
                return f.read()
        else:
            raise Exception("Sorry, you need to login with your apikey first. You can get your apikey from our website:https://test-pc.neuralimage.net after you login and become a creator!")
            