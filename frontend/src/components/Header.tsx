import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useUser, UserButton, SignInButton } from '@clerk/react';
import { Sun, Moon, Menu, X } from 'lucide-react';
import { useTheme } from './theme-provider';
import Logo from './Logo';

const Header: React.FC = () => {
  const { isSignedIn } = useUser();
  const { theme, setTheme } = useTheme();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const update = () => setIsDark(theme === 'dark' || (theme === 'system' && mq.matches));
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, [theme]);

  const toggleTheme = () => setTheme(isDark ? 'light' : 'dark');
  const closeMenu = () => setMobileOpen(false);

  const navLinks = (
    <>
      <Link to="/find" onClick={closeMenu} className="font-mono text-xs text-text-secondary hover:text-text-primary transition-colors">
        Find
      </Link>
      {isSignedIn && (
        <Link to="/critique" onClick={closeMenu} className="font-mono text-xs text-text-secondary hover:text-text-primary transition-colors">
          Critique
        </Link>
      )}
      {isSignedIn && (
        <Link to="/saved" onClick={closeMenu} className="font-mono text-xs text-text-secondary hover:text-text-primary transition-colors">
          Saved
        </Link>
      )}
      {isSignedIn && (
        <Link to="/history" onClick={closeMenu} className="font-mono text-xs text-text-secondary hover:text-text-primary transition-colors">
          History
        </Link>
      )}
      {isSignedIn && (
        <Link to="/usage" onClick={closeMenu} className="font-mono text-xs text-text-secondary hover:text-text-primary transition-colors">
          Usage
        </Link>
      )}
      {isSignedIn && (
        <Link to="/developer" onClick={closeMenu} className="font-mono text-xs text-text-secondary hover:text-text-primary transition-colors">
          Developer
        </Link>
      )}
      <Link to="/docs" onClick={closeMenu} className="font-mono text-xs text-text-secondary hover:text-text-primary transition-colors">
        Docs
      </Link>
    </>
  );

  return (
    <header className="border-b border-lp-border bg-bg">
      <div className="max-w-[860px] mx-auto px-6 py-4">
        <div className="flex items-center justify-between">
          {/* Masthead */}
          <Link to="/" className="no-underline flex items-center gap-2">
            <Logo size={24} className="shrink-0 relative top-px" />
            <div className="font-serif text-xl text-text-primary leading-none">
              internshipmatcher<em className="not-italic text-text-secondary">.</em>
            </div>
          </Link>

          {/* Desktop nav */}
          <nav className="hidden sm:flex items-center gap-5">
            {navLinks}
            <button
              onClick={toggleTheme}
              className="text-text-tertiary hover:text-text-primary transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-text-primary rounded-sm"
              aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {isDark ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
            </button>
            {isSignedIn ? (
              <UserButton />
            ) : (
              <SignInButton mode="modal">
                <button className="font-mono text-xs text-text-secondary hover:text-text-primary transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-text-primary rounded-sm">
                  Sign in →
                </button>
              </SignInButton>
            )}
          </nav>

          {/* Mobile controls */}
          <div className="flex sm:hidden items-center gap-3">
            <button
              onClick={toggleTheme}
              className="text-text-tertiary hover:text-text-primary transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-text-primary rounded-sm"
              aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {isDark ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
            </button>
            <button
              onClick={() => setMobileOpen((o) => !o)}
              className="text-text-secondary hover:text-text-primary transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-text-primary rounded-sm"
              aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
              aria-expanded={mobileOpen}
            >
              {mobileOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {/* Mobile nav drawer */}
        {mobileOpen && (
          <nav className="sm:hidden flex flex-col gap-4 pt-4 mt-4 border-t border-lp-border">
            {navLinks}
            {isSignedIn ? (
              <div onClick={closeMenu}>
                <UserButton />
              </div>
            ) : (
              <SignInButton mode="modal">
                <button onClick={closeMenu} className="font-mono text-xs text-text-secondary hover:text-text-primary transition-colors text-left">
                  Sign in →
                </button>
              </SignInButton>
            )}
          </nav>
        )}
      </div>
    </header>
  );
};

export default Header;
