import json
import base64
import getpass
import os

def setup():
    print("This script will save your credentials (password in Keychain when available) to config.json")
    
    email = input("Enter your LibreLinkUp Email: ").strip()
    password = getpass.getpass("Enter your LibreLinkUp Password: ").strip()
    region = input("Enter your region (eu, global, de, fr, jp, ap, ae) [default: eu]: ").strip() or "eu"

    if not email or not password:
        print("Email and password are required.")
        return

    email_b64 = base64.b64encode(email.encode('utf-8')).decode('utf-8')
    password_store = None
    try:
        import keyring  # type: ignore
        keyring.set_password("schugaa", email, password)
        password_store = "__keyring__"
    except Exception:
        password_store = base64.b64encode(password.encode('utf-8')).decode('utf-8')

    config = {
        "email": email_b64,
        "password": password_store,
        "region": region
    }

    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)
    try:
        os.chmod("config.json", 0o600)
    except Exception:
        pass
    
    print("\nCredentials saved to config.json (password stored in Keychain when available)")

if __name__ == "__main__":
    setup()
