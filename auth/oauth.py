import os
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.oauth2.rfc6749 import OAuth2Token

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")

# OAuth configuration
GOOGLE_OAUTH_CONFIG = {
    "client_id": GOOGLE_CLIENT_ID,
    "client_secret": GOOGLE_CLIENT_SECRET,
    "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
    "token_endpoint": "https://oauth2.googleapis.com/token",
    "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
    "scopes": ["openid", "email", "profile"]
}

async def get_google_oauth_client():
    """Create and return Google OAuth client"""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise ValueError("Google OAuth credentials not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables.")
    
    return AsyncOAuth2Client(
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scope=" ".join(GOOGLE_OAUTH_CONFIG["scopes"])
    )

async def get_authorization_url(client: AsyncOAuth2Client, redirect_uri: str, state: str):
    """Generate authorization URL for Google OAuth"""
    authorization_url, _ = client.create_authorization_url(
        GOOGLE_OAUTH_CONFIG["authorization_endpoint"],
        redirect_uri=redirect_uri,
        state=state
    )
    return authorization_url

async def exchange_code_for_token(client: AsyncOAuth2Client, code: str, redirect_uri: str):
    """Exchange authorization code for access token"""
    try:
        token = await client.fetch_token(
            GOOGLE_OAUTH_CONFIG["token_endpoint"],
            code=code,
            redirect_uri=redirect_uri
        )
        return token
    except Exception as e:
        print(f"❌ Error exchanging code for token: {e}")
        return None

async def get_user_info(token: OAuth2Token):
    """Get user information from Google using access token"""
    try:
        client = AsyncOAuth2Client(
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            token=token
        )
        
        response = await client.get(GOOGLE_OAUTH_CONFIG["userinfo_endpoint"])
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Error getting user info: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error getting user info: {e}")
        return None 