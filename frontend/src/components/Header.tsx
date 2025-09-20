import React from 'react';
import { User } from '../types';

interface HeaderProps {
  user?: User;
}

const Header: React.FC<HeaderProps> = ({ user }) => {
  return (
    <div className="header">
      <div className="logo">🎯 Internship Matcher</div>
      <div className="user-info">
        {user ? (
          <>
            <div className="user-avatar">
              {user.name ? user.name[0].toUpperCase() : user.email[0].toUpperCase()}
            </div>
            <div>
              <div>{user.name || user.email}</div>
              <div style={{ fontSize: '0.8rem', opacity: 0.8 }}>
                {user.provider.charAt(0).toUpperCase() + user.provider.slice(1)}
              </div>
            </div>
            <a href="/logout" className="logout-btn">
              <i className="fas fa-sign-out-alt"></i> Logout
            </a>
          </>
        ) : (
          <a href="/login" className="login-btn">
            <i className="fas fa-sign-in-alt"></i> Sign In
          </a>
        )}
      </div>
    </div>
  );
};

export default Header;