#!/bin/bash

echo "🔐 Setting up Google OAuth for User Metadata Storage"
echo "====================================================="
echo ""
echo "This will enable Google Sign-in and user metadata storage."
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
echo "🔧 Now re-enabling Google OAuth button..."
echo ""

# Re-enable the Google OAuth button
sed -i '' 's/<!-- Temporarily disabled until OAuth is configured/<!-- Google OAuth enabled/' templates/login.html
sed -i '' 's/-->//' templates/login.html

echo "🚀 Deploying changes to Railway..."
git add .
git commit -m "Enable Google OAuth for user metadata storage"
git push origin main
railway up

echo ""
echo "🎉 Google OAuth is now enabled!"
echo "Users can now sign in with Google and their metadata will be stored."
echo ""
echo "Your app will now:"
echo "✅ Store user profile data (name, email, profile picture)"
echo "✅ Track user login sessions"
echo "✅ Associate resume uploads with user accounts"
echo "✅ Provide personalized job recommendations" 