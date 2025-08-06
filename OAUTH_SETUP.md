# OAuth Setup Guide

This guide will help you set up Google and Apple OAuth authentication for your internship matching application.

## Environment Variables

Create a `.env` file in your project root with the following variables:

```env
# OAuth Configuration
GOOGLE_CLIENT_ID=your_google_client_id_here
GOOGLE_CLIENT_SECRET=your_google_client_secret_here

APPLE_CLIENT_ID=your_apple_client_id_here
APPLE_CLIENT_SECRET=your_apple_client_secret_here

# Session Secret Key (change this to a random string in production)
SECRET_KEY=your-super-secret-key-change-in-production

# Application URL (for OAuth redirects)
BASE_URL=http://localhost:8000
```

## Google OAuth Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google+ API
4. Go to "Credentials" → "Create Credentials" → "OAuth 2.0 Client IDs"
5. Configure the consent screen
6. Set application type to "Web application"
7. Add authorized redirect URIs:
   - `http://localhost:8000/auth/google/callback` (for development)
   - `https://yourdomain.com/auth/google/callback` (for production)
8. Copy the Client ID and Client Secret to your `.env` file

## Apple OAuth Setup

1. Go to [Apple Developer](https://developer.apple.com/)
2. Sign in with your Apple ID
3. Go to "Certificates, Identifiers & Profiles"
4. Create a new "Services ID"
5. Configure Sign in with Apple
6. Add your domain and redirect URL:
   - `http://localhost:8000/auth/apple/callback` (for development)
   - `https://yourdomain.com/auth/apple/callback` (for production)
7. Create a private key for Sign in with Apple
8. Copy the Services ID and configure the client secret

## Production Deployment

For production deployment on Railway:

1. Add environment variables in Railway dashboard:
   ```
   GOOGLE_CLIENT_ID=your_production_google_client_id
   GOOGLE_CLIENT_SECRET=your_production_google_client_secret
   APPLE_CLIENT_ID=your_production_apple_client_id
   APPLE_CLIENT_SECRET=your_production_apple_client_secret
   SECRET_KEY=your-production-secret-key
   BASE_URL=https://your-railway-app.up.railway.app
   ```

2. Update OAuth redirect URIs to include your production URL:
   - Google: `https://your-railway-app.up.railway.app/auth/google/callback`
   - Apple: `https://your-railway-app.up.railway.app/auth/apple/callback`

## Testing

1. Start your development server: `uvicorn app:app --reload --host 0.0.0.0 --port 8000`
2. Go to `http://localhost:8000/login`
3. Test both Google and Apple sign-in buttons
4. Verify that authentication redirects work correctly

## Security Notes

- Always use HTTPS in production
- Keep your client secrets secure and never commit them to version control
- Use a strong, random SECRET_KEY for session management
- Consider implementing rate limiting for authentication endpoints
- Regularly rotate your OAuth credentials 