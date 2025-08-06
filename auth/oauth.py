from authlib.integrations.starlette_client import OAuth
from fastapi import Request
import os
from dotenv import load_dotenv

load_dotenv()

# OAuth configuration
oauth = OAuth()

# Google OAuth
oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid_configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

# Apple OAuth
oauth.register(
    name='apple',
    client_id=os.getenv('APPLE_CLIENT_ID'),
    client_secret=os.getenv('APPLE_CLIENT_SECRET'),
    server_metadata_url='https://appleid.apple.com/.well-known/openid_configuration',
    client_kwargs={
        'scope': 'name email'
    }
)

async def get_user_info_google(token):
    """Get user information from Google"""
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(
                'https://www.googleapis.com/oauth2/v2/userinfo',
                headers={'Authorization': f'Bearer {token["access_token"]}'}
            )
            return response.json()
    except Exception as e:
        print(f"Error getting Google user info: {e}")
        return None

async def get_user_info_apple(token):
    """Get user information from Apple"""
    try:
        # Apple returns user info in the ID token
        from jose import jwt
        import json
        
        # Decode the ID token (simplified - in production you should verify the signature)
        decoded = jwt.get_unverified_claims(token.get('id_token', ''))
        return {
            'email': decoded.get('email'),
            'name': decoded.get('name', 'Apple User'),
            'id': decoded.get('sub')
        }
    except Exception as e:
        print(f"Error getting Apple user info: {e}")
        return None 