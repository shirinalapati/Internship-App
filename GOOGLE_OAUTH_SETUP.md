# 🔐 Google OAuth Setup Guide

## Step 1: Create a Google Cloud Project

1. **Go to Google Cloud Console** (should be open in your browser)
2. **Create a new project** or select an existing one:
   - Click "Select a project" at the top
   - Click "New Project"
   - Name it: "Internship Matcher OAuth"
   - Click "Create"

## Step 2: Enable Google+ API

1. In the left sidebar, click **"APIs & Services"** → **"Library"**
2. Search for **"Google+ API"** or **"Google Identity"**
3. Click on it and click **"Enable"**

## Step 3: Configure OAuth Consent Screen

1. Go to **"APIs & Services"** → **"OAuth consent screen"**
2. Choose **"External"** user type
3. Fill in the required information:
   - **App name**: "Internship Matcher"
   - **User support email**: Your email
   - **Developer contact information**: Your email
4. Click **"Save and Continue"**
5. Skip scopes section, click **"Save and Continue"**
6. Add test users (your email), click **"Save and Continue"**
7. Click **"Back to Dashboard"**

## Step 4: Create OAuth 2.0 Credentials

1. Go to **"APIs & Services"** → **"Credentials"**
2. Click **"Create Credentials"** → **"OAuth 2.0 Client IDs"**
3. Choose **"Web application"**
4. Fill in the details:
   - **Name**: "Internship Matcher OAuth"
   - **Authorized JavaScript origins**:
     - `http://localhost:8000`
     - `https://your-railway-app-name.up.railway.app` (replace with your Railway URL)
   - **Authorized redirect URIs**:
     - `http://localhost:8000/auth/google/callback`
     - `https://your-railway-app-name.up.railway.app/auth/google/callback`
5. Click **"Create"**

## Step 5: Get Your Credentials

After creating, you'll see:
- **Client ID**: Copy this
- **Client Secret**: Copy this

## Step 6: Set Up Environment Variables

1. **Create a `.env` file** in your project root:
   ```bash
   cp env_template.txt .env
   ```

2. **Edit the `.env` file** and replace the placeholders:
   ```
   GOOGLE_CLIENT_ID=your_actual_client_id_here
   GOOGLE_CLIENT_SECRET=your_actual_client_secret_here
   GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
   ```

## Step 7: Test Locally

1. **Restart your server**:
   ```bash
   uvicorn app:app --reload --host 0.0.0.0 --port 8000
   ```

2. **Go to** `http://localhost:8000`
3. **Click "Continue with Google"**
4. **You should now be redirected to Google's login page**

## Step 8: Deploy to Railway

1. **Set Railway environment variables**:
   ```bash
   railway variables set GOOGLE_CLIENT_ID="your_client_id"
   railway variables set GOOGLE_CLIENT_SECRET="your_client_secret"
   railway variables set GOOGLE_REDIRECT_URI="https://your-railway-app-name.up.railway.app/auth/google/callback"
   ```

2. **Deploy**:
   ```bash
   railway up
   ```

## Troubleshooting

- **"OAuth client was not found"**: Check that your Client ID is correct
- **"Invalid redirect URI"**: Make sure the redirect URI in Google Console matches your app's callback URL
- **"Access blocked"**: Add your email as a test user in the OAuth consent screen

## Your Railway URL

To find your Railway URL, run:
```bash
railway status
```

This will show you the URL where your app is deployed. 