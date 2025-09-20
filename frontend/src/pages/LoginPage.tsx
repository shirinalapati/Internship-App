import React from 'react';

interface LoginPageProps {
  error?: string;
}

const LoginPage: React.FC<LoginPageProps> = ({ error }) => {
  const getErrorMessage = (errorCode?: string) => {
    switch (errorCode) {
      case 'oauth_not_configured':
        return '❌ Google OAuth is not configured yet. Please use "Continue without signing in" for now.';
      case 'oauth_error':
        return '❌ OAuth authentication failed. Please try again.';
      case 'invalid_state':
        return '❌ Security validation failed. Please try again.';
      case 'no_code':
        return '❌ No authorization code received. Please try again.';
      case 'token_exchange_failed':
        return '❌ Failed to exchange authorization code. Please try again.';
      case 'user_info_failed':
        return '❌ Failed to retrieve user information. Please try again.';
      case 'oauth_callback_error':
        return '❌ OAuth callback error. Please try again.';
      default:
        return '❌ An error occurred during login. Please try again.';
    }
  };

  return (
    <div className="login-container">
      <div className="logo">🎯 Internship Matcher</div>
      <p className="tagline">Find your perfect internship match</p>

      {error && (
        <div className="error-message">
          <p>{getErrorMessage(error)}</p>
        </div>
      )}

      <div className="auth-buttons">
        <a href="/auth/google" className="google-btn">
          <i className="fab fa-google"></i>
          Continue with Google
        </a>
        
        <div className="divider">
          <span>or</span>
        </div>
        
        <a href="/dashboard" className="continue-btn">
          <i className="fas fa-arrow-right"></i>
          Continue without signing in
        </a>
      </div>

      <div className="features">
        <h3>🚀 What you'll get:</h3>
        <ul>
          <li>Personalized internship recommendations</li>
          <li>Resume-based skill matching</li>
          <li>Real-time job scraping</li>
          <li>Match score calculations</li>
          <li>Application tracking</li>
        </ul>
      </div>
    </div>
  );
};

export default LoginPage;