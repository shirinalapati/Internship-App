import React from 'react';
import HomePage from './pages/HomePage';
import LoginPage from './pages/LoginPage';
import './styles/index.css';

function App() {
  // For now, we'll determine which page to show based on the URL path
  // In a real app, you'd use React Router for this
  const path = window.location.pathname;
  
  // Mock user data - in a real app, this would come from authentication state
  const user = undefined; // You can set this to a user object for testing

  if (path === '/login') {
    return <LoginPage />;
  }

  return <HomePage user={user} />;
}

export default App;
