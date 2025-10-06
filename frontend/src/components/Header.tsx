import React from 'react';
import { useUser, useStackApp } from '@stackframe/react';
import { ThemeToggle } from './theme-toggle';
import { Button } from './ui/button';
import { Briefcase, LogOut, LogIn } from 'lucide-react';

const Header: React.FC = () => {
  const user = useUser();
  const app = useStackApp();

  const handleSignOut = async () => {
    await user?.signOut();
    window.location.href = '/';
  };

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-16 items-center justify-between">
        <div className="flex items-center gap-2">
          <Briefcase className="h-6 w-6" />
          <span className="text-xl font-bold">InternMatch AI</span>
        </div>
        <div className="flex items-center gap-4">
          <ThemeToggle />
          {user ? (
            <>
              <div className="flex items-center gap-2">
                <div className="h-8 w-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center font-semibold text-sm">
                  {user.displayName ? user.displayName[0].toUpperCase() : user.primaryEmail?.[0].toUpperCase() || 'U'}
                </div>
                <div className="hidden sm:flex flex-col">
                  <span className="text-sm font-medium leading-none">{user.displayName || user.primaryEmail}</span>
                  <span className="text-xs text-muted-foreground">Signed in</span>
                </div>
              </div>
              <Button 
                variant="outline" 
                size="sm"
                onClick={handleSignOut}
              >
                <LogOut className="h-4 w-4 mr-2" />
                Logout
              </Button>
            </>
          ) : (
            <Button 
              size="sm"
              onClick={() => window.location.href = '/handler/sign-in'}
            >
              <LogIn className="h-4 w-4 mr-2" />
              Sign In
            </Button>
          )}
        </div>
      </div>
    </header>
  );
};

export default Header;
