# Environment Variables in React (Create React App)

## ✅ Fixed!

Your Stack Auth environment variables are now properly configured.

## 📁 Two Separate `.env` Files

You have **two** `.env` files in your project:

### 1. **Root `.env`** (Backend - Python/FastAPI)
**Location:** `/Internship-App/.env`

Contains **server-side** secrets (NEVER exposed to browser):
```bash
GOOGLE_CLIENT_SECRET=...          # Backend only
OPENAI_API_KEY=...                # Backend only
REDIS_URL=...                     # Backend only
STACK_AUTH_SECRET_KEY=...         # Backend only - NEVER expose!
```

### 2. **Frontend `.env`** (React/Browser)
**Location:** `/Internship-App/frontend/.env`

Contains **client-side** config (exposed to browser - must be safe):
```bash
REACT_APP_STACK_AUTH_PROJECT_ID=...
REACT_APP_STACK_AUTH_PUBLISHABLE_CLIENT_KEY=...
```

## 🔑 Key Rules for Create React App

### 1. **Must start with `REACT_APP_`**
```typescript
// ❌ WRONG - Won't work
process.env.STACK_AUTH_PROJECT_ID

// ✅ CORRECT
process.env.REACT_APP_STACK_AUTH_PROJECT_ID
```

### 2. **Variables are embedded at BUILD time**
- Environment variables are baked into the build
- Changing `.env` requires **restarting** the dev server
- Use `npm start` to restart

### 3. **Only safe values in frontend `.env`**
```bash
# ✅ SAFE - Public/publishable keys
REACT_APP_STACK_AUTH_PROJECT_ID=...
REACT_APP_STACK_AUTH_PUBLISHABLE_CLIENT_KEY=...
REACT_APP_API_URL=http://localhost:8000

# ❌ NEVER put these in frontend .env!
REACT_APP_SECRET_KEY=...           # ❌ Secrets visible in browser!
REACT_APP_OPENAI_API_KEY=...       # ❌ Anyone can see this!
```

## 🔄 When to Restart Dev Server

After creating or modifying `frontend/.env`, you MUST restart:

```bash
# Stop the server (Ctrl+C)
# Then restart
cd frontend
npm start
```

## 🧪 Testing Your Variables

Add this temporary code to any component to verify:

```typescript
console.log('Project ID:', process.env.REACT_APP_STACK_AUTH_PROJECT_ID);
console.log('Client Key:', process.env.REACT_APP_STACK_AUTH_PUBLISHABLE_CLIENT_KEY);
```

If you see `undefined`, you need to:
1. Check the variable name has `REACT_APP_` prefix
2. Restart your dev server
3. Verify the `.env` file is in `frontend/` directory

## 📝 Your Updated `client.ts`

```typescript
export const stackClientApp = new StackClientApp({
  // ✅ Now correctly using REACT_APP_ prefix
  projectId: process.env.REACT_APP_STACK_AUTH_PROJECT_ID || '',
  publishableClientKey: process.env.REACT_APP_STACK_AUTH_PUBLISHABLE_CLIENT_KEY || '',
  tokenStore: "cookie",
  redirectMethod: {
    useNavigate,
  }
});
```

## 🔒 Security Notes

### Safe to Expose (Frontend)
- ✅ Project IDs
- ✅ Publishable keys
- ✅ Public API endpoints
- ✅ Feature flags

### NEVER Expose (Backend Only)
- ❌ Secret keys
- ❌ API keys (OpenAI, Google, etc.)
- ❌ Database credentials
- ❌ OAuth client secrets

## 🚀 Deployment

When deploying to production:

### Frontend (Vercel, Netlify, etc.)
Add environment variables in your hosting dashboard:
```
REACT_APP_STACK_AUTH_PROJECT_ID=...
REACT_APP_STACK_AUTH_PUBLISHABLE_CLIENT_KEY=...
REACT_APP_API_URL=https://your-api.com
```

### Backend (Render, Railway, etc.)
Add in your hosting dashboard (NO `REACT_APP_` prefix):
```
OPENAI_API_KEY=...
REDIS_URL=...
STACK_AUTH_SECRET_KEY=...
```

## ✅ Summary

- ✅ Created `frontend/.env` with `REACT_APP_` prefix
- ✅ Updated `client.ts` to use correct variable names
- ✅ Added `.env` to `.gitignore`
- ✅ Root `.env` stays for backend secrets

**Now restart your frontend dev server and it should work!** 🎉

