#!/usr/bin/env python3
"""
Google OAuth Setup Script
This script helps you set up Google OAuth credentials for the Internship Matcher app.
"""

import os
import webbrowser
from pathlib import Path

def print_banner():
    print("🔐 Google OAuth Setup for Internship Matcher")
    print("=" * 50)
    print()

def print_instructions():
    print("📋 Setup Instructions:")
    print("1. Go to Google Cloud Console")
    print("2. Create a new project or select existing one")
    print("3. Enable Google+ API")
    print("4. Create OAuth 2.0 credentials")
    print("5. Add authorized redirect URIs")
    print()

def get_google_cloud_console_url():
    return "https://console.cloud.google.com/apis/credentials"

def print_redirect_uris():
    print("🔗 Add these Redirect URIs to your Google OAuth credentials:")
    print("   - http://localhost:8000/auth/google/callback")
    print("   - https://your-railway-app.up.railway.app/auth/google/callback")
    print()

def create_env_file():
    print("📝 Creating .env file template...")
    
    env_content = """# Google OAuth Credentials
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

# For Railway deployment, also set:
# GOOGLE_REDIRECT_URI=https://your-railway-app.up.railway.app/auth/google/callback
"""
    
    with open(".env", "w") as f:
        f.write(env_content)
    
    print("✅ Created .env file")
    print("📝 Edit .env file with your actual credentials")
    print()

def main():
    print_banner()
    print_instructions()
    
    # Open Google Cloud Console
    print("🌐 Opening Google Cloud Console...")
    webbrowser.open(get_google_cloud_console_url())
    
    print_redirect_uris()
    create_env_file()
    
    print("🎯 Next Steps:")
    print("1. Copy your Client ID and Client Secret from Google Cloud Console")
    print("2. Edit the .env file with your credentials")
    print("3. For Railway deployment, run: railway variables set GOOGLE_CLIENT_ID=your_id")
    print("4. For Railway deployment, run: railway variables set GOOGLE_CLIENT_SECRET=your_secret")
    print("5. Restart your app: uvicorn app:app --reload")
    print()
    print("✅ Google OAuth will be enabled once credentials are set!")

if __name__ == "__main__":
    main() 