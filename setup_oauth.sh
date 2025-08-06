#!/bin/bash

echo "🔐 Setting up Google OAuth Environment Variables"
echo "================================================="
echo ""
echo "Please enter your Google OAuth credentials from Google Cloud Console:"
echo ""

# Prompt for Google Client ID
read -p "Google Client ID: " GOOGLE_CLIENT_ID

# Prompt for Google Client Secret (hidden input)
read -s -p "Google Client Secret: " GOOGLE_CLIENT_SECRET
echo ""

# Set Railway environment variables
echo ""
echo "🚀 Setting Railway environment variables..."

railway variables set GOOGLE_CLIENT_ID="$GOOGLE_CLIENT_ID"
railway variables set GOOGLE_CLIENT_SECRET="$GOOGLE_CLIENT_SECRET"
railway variables set GOOGLE_REDIRECT_URI="https://internshipbasedonresume-production.up.railway.app/auth/google/callback"

echo ""
echo "✅ Environment variables set successfully!"
echo ""
echo "🔧 Next steps:"
echo "1. Make sure your Google Cloud Console OAuth client has these URLs:"
echo "   - Authorized JavaScript origins:"
echo "     * http://localhost:8000"
echo "     * https://internshipbasedonresume-production.up.railway.app"
echo ""
echo "   - Authorized redirect URIs:"
echo "     * http://localhost:8000/auth/google/callback"
echo "     * https://internshipbasedonresume-production.up.railway.app/auth/google/callback"
echo ""
echo "2. Deploy the app: railway up"
echo "3. Test login with Google!" 