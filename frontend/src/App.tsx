import React, { Suspense } from 'react';
import { BrowserRouter, Route, Routes, useLocation } from 'react-router-dom';
import { StackHandler, StackProvider, StackTheme } from '@stackframe/react';
import { stackClientApp } from './stack/client';
import { ThemeProvider } from './components/theme-provider';
import LandingPage from './pages/LandingPage';
import FindPage from './pages/FindPage';
import LoginPage from './pages/LoginPage';
import TestJobDisplay from './components/TestJobDisplay';

function HandlerRoutes() {
  const location = useLocation();

  return (
    <StackHandler app={stackClientApp} location={location.pathname} fullPage />
  );
}

function App() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center min-h-screen">Loading...</div>}>
      <BrowserRouter>
        <StackProvider app={stackClientApp}>
          <StackTheme>
            <ThemeProvider defaultTheme="system" storageKey="internship-ui-theme">
              <Routes>
                {/* Stack Auth handler routes */}
                <Route path="/handler/*" element={<HandlerRoutes />} />

                {/* Your app routes */}
                <Route path="/" element={<LandingPage />} />
                <Route path="/find" element={<FindPage />} />
                <Route path="/login" element={<LoginPage />} />
                <Route path="/test" element={<TestJobDisplay />} />
              </Routes>
            </ThemeProvider>
          </StackTheme>
        </StackProvider>
      </BrowserRouter>
    </Suspense>
  );
}

export default App;
