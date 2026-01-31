import json
import base64
import getpass

def setup():
    print("This script will base64 encode your credentials and save them to config.json")
    
    email = input("Enter your LibreLinkUp Email: ").strip()
    password = getpass.getpass("Enter your LibreLinkUp Password: ").strip()
    region = input("Enter your region (eu, global, de, fr, jp, ap, ae) [default: eu]: ").strip() or "eu"

    if not email or not password:
        print("Email and password are required.")
        return

    email_b64 = base64.b64encode(email.encode('utf-8')).decode('utf-8')
    password_b64 = base64.b64encode(password.encode('utf-8')).decode('utf-8')

    config = {
        "email": email_b64,
        "password": password_b64,
        "region": region
    }

    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)
    
    print("\nCredentials saved securely (base64 encoded) to config.json")

if __name__ == "__main__":
    setup()
