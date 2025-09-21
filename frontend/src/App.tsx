import React, { Suspense } from 'react';
import HomePage from './pages/HomePage';
import LoginPage from './pages/LoginPage';
import './styles/index.css';
import { StackHandler, StackProvider, StackTheme } from '@stackframe/react';
import { stackClientApp } from './stack/client';

function AppInner() {
  // For now, we'll determine which page to show based on the URL path
  // In a real app, you'd use React Router for this
  const path = window.location.pathname;
  
  // Mock user data - in a real app, this would come from authentication state
  const user = undefined; // You can set this to a user object for testing

  if (path === '/login') {
    return <LoginPage />;
  }

  if (path.startsWith('/handler/')) {
    return <StackHandler app={stackClientApp} location={path} fullPage />;
  }

  return <HomePage user={user} />;
}

function App() {
  return (
    <Suspense fallback={null}>
      <StackProvider app={stackClientApp}>
        <StackTheme>
          <AppInner />
        </StackTheme>
      </StackProvider>
    </Suspense>
  );
}

export default App;
