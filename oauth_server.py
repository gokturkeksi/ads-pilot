# oauth_server.py – tiny Flask app to complete the OAuth consent flow
import os, json, logging, requests
from flask import Flask, request, redirect
from google_auth_oauthlib.flow import InstalledAppFlow

app = Flask(__name__)

# Load .env automatically (optional but handy)
from dotenv import load_dotenv
load_dotenv()


# Scopes required by the pipeline (read‑only)
SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
]

# Load client config from environment variables (or a local client_secret.json)
CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    raise RuntimeError("Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in the environment.")

# Build a temporary client config dictionary – the flow class expects the same shape as a
# downloaded client_secret.json file.
client_config = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost:8080/"],
    }
}

@app.route("/login")
def login():
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    flow.redirect_uri = "http://localhost:8080/callback"
    auth_url, _ = flow.authorization_url(prompt="consent")
    return redirect(auth_url)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    flow.redirect_uri = "http://localhost:8080/callback"
    flow.fetch_token(code=code)
    credentials = flow.credentials
    # Store the *refresh token* in Cloudflare KV via the REST API used by the pipeline.
    # The KV key is defined in the .env (default: miner/oauth/refresh_token).
    kv_key = os.getenv("REFRESH_TOKEN_KV_KEY", "miner/oauth/refresh_token")
    cf_account = os.getenv("CLOUD_FLARE_ACCOUNT_ID")
    cf_namespace = os.getenv("CLOUD_FLARE_KV_NAMESPACE_ID")
    cf_token = os.getenv("CLOUD_FLARE_API_TOKEN")
    if not all([cf_account, cf_namespace, cf_token]):
        return "Cloudflare credentials missing – set them in .env", 500
    url = f"https://api.cloudflare.com/client/v4/accounts/{cf_account}/storage/kv/namespaces/{cf_namespace}/values/{kv_key}"
    headers = {"Authorization": f"Bearer {cf_token}", "Content-Type": "application/json"}
    resp = requests.put(url, headers=headers, data=json.dumps({"refresh_token": credentials.refresh_token}))
    if resp.status_code != 200:
        return f"KV write failed: {resp.text}", 500
    return (
        "✅ Refresh token stored successfully! You can now stop the server.\n"
        f"Refresh token: {credentials.refresh_token[:8]}..."
    )

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Flask defaults to 127.0.0.1:8080 – matches the redirect URI above.
    app.run(port=8080)
