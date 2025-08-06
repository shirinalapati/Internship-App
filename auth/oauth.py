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
    """Get user info from Google using the access token"""
    async with oauth.google.client as client:
        resp = await client.get('userinfo', token=token)
        user_info = resp.json()
        return {
            'id': user_info.get('sub'),
            'email': user_info.get('email'),
            'name': user_info.get('name'),
            'given_name': user_info.get('given_name'),
            'family_name': user_info.get('family_name'),
            'picture': user_info.get('picture'),
            'provider': 'google'
        }

async def get_user_info_apple(token):
    """Get user info from Apple using the access token"""
    # Apple doesn't provide a userinfo endpoint, so we decode the ID token
    import json
    from jose import jwt
    
    # For Apple, the user info is in the ID token
    id_token = token.get('id_token')
    if id_token:
        # Note: In production, you should verify the token signature
        payload = jwt.get_unverified_claims(id_token)
        return {
            'id': payload.get('sub'),
            'email': payload.get('email'),
            'name': payload.get('name', payload.get('email', '').split('@')[0]),
            'provider': 'apple'
        }
    return None 