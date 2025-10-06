import React from 'react';
import { Loader2 } from 'lucide-react';

interface LoadingSpinnerProps {
  show?: boolean;
}

const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ show = false }) => {
  if (!show) return null;

  return (
    <div className="flex flex-col items-center justify-center py-12">
      <Loader2 className="h-12 w-12 animate-spin text-primary" />
      <p className="mt-4 text-sm text-muted-foreground">Analyzing your resume...</p>
    </div>
  );
};

export default LoadingSpinner;
