import React from 'react';
import { AlertCircle } from 'lucide-react';
import { Card, CardContent } from './ui/card';

interface ErrorMessageProps {
  error: string;
}

const ErrorMessage: React.FC<ErrorMessageProps> = ({ error }) => {
  return (
    <Card className="max-w-2xl mx-auto border-destructive">
      <CardContent className="pt-6">
        <div className="flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-semibold text-destructive">Error</h3>
            <p className="text-sm text-muted-foreground mt-1">{error}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default ErrorMessage;
