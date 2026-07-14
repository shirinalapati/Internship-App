import React, { Suspense, useEffect, useRef } from 'react';
import { BrowserRouter, Route, Routes, useLocation } from 'react-router-dom';
import { ClerkProvider, useAuth } from '@clerk/react';
import { ThemeProvider } from './components/theme-provider';
import { captureUTM, getStoredUTM, clearUTM } from './lib/utm';
import { API_BASE_URL } from './lib/api';
import LandingPage from './pages/LandingPage';
import FindPage from './pages/FindPage';
import HistoryPage from './pages/HistoryPage';
import SavedJobsPage from './pages/SavedJobsPage';
import UsagePage from './pages/UsagePage';
import CritiquePage from './pages/CritiquePage';
import DeveloperPage from './pages/DeveloperPage';
import DocsPage from './pages/DocsPage';
import LoginPage from './pages/LoginPage';
import TestJobDisplay from './components/TestJobDisplay';

declare global {
  interface Window { dataLayer: Record<string, unknown>[]; }
}

function PageTracker() {
  const location = useLocation();
  useEffect(() => {
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push({
      event: 'page_view',
      page_path: location.pathname + location.search,
    });
  }, [location]);
  return null;
}

function UTMTracker() {
  const location = useLocation();
  const { isSignedIn, getToken } = useAuth();
  const attributed = useRef(false);

  // Capture UTM from the landing URL (first-touch, runs once).
  // Also push to GTM so GA4 sees the session source immediately.
  useEffect(() => {
    captureUTM(location.search);
    const utm = getStoredUTM();
    if (utm) {
      window.dataLayer = window.dataLayer || [];
      window.dataLayer.push({ event: 'utm_captured', ...utm });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Once the user signs in, associate their Clerk user ID with the stored UTM.
  useEffect(() => {
    if (!isSignedIn || attributed.current) return;
    const utm = getStoredUTM();
    if (!utm) return;
    attributed.current = true;
    (async () => {
      try {
        const token = await getToken();
        await fetch(`${API_BASE_URL}/api/track-attribution`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify(utm),
        });
        clearUTM();
      } catch {
        // fire-and-forget — attribution failure must never affect the user
      }
    })();
  }, [isSignedIn, getToken]);

  return null;
}

function App() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center min-h-screen">Loading...</div>}>
      <ClerkProvider publishableKey={process.env.REACT_APP_CLERK_PUBLISHABLE_CLIENT_KEY!}>
        <BrowserRouter>
          <ThemeProvider defaultTheme="system" storageKey="internship-ui-theme">
            <PageTracker />
            <UTMTracker />
            <Routes>
              <Route path="/" element={<LandingPage />} />
              <Route path="/find" element={<FindPage />} />
              <Route path="/history" element={<HistoryPage />} />
              <Route path="/saved" element={<SavedJobsPage />} />
              <Route path="/usage" element={<UsagePage />} />
              <Route path="/critique" element={<CritiquePage />} />
              <Route path="/developer" element={<DeveloperPage />} />
              <Route path="/docs" element={<DocsPage />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/test" element={<TestJobDisplay />} />
            </Routes>
          </ThemeProvider>
        </BrowserRouter>
      </ClerkProvider>
    </Suspense>
  );
}

export default App;
