import React from 'react';
import { Job } from '../types';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { MapPin, ExternalLink, Building2, TrendingUp } from 'lucide-react';
import { cn } from '../lib/utils';

interface JobCardProps {
  job: Job;
  isNewResult?: boolean;
}

const JobCard: React.FC<JobCardProps> = ({ job, isNewResult = false }) => {
  const getMatchScoreBadgeVariant = (score: number): 'default' | 'secondary' | 'destructive' | 'outline' => {
    if (score >= 70) return 'default';
    if (score >= 40) return 'secondary';
    return 'outline';
  };

  const score = job.match_score || job.score || 0;

  // Parse the match_description which contains our enhanced format
  const formatMatchDescription = (desc: string) => {
    if (!desc) return [];
    
    return desc
      .split('\n')
      .map((line, index) => {
        if (!line.trim()) return null; // Skip empty lines
        
        // Handle bold markdown
        let formatted = line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        
        // Add styling for emojis and special sections
        if (line.includes('🎯')) {
          return <p key={index} dangerouslySetInnerHTML={{ __html: formatted }} className="text-sm font-semibold text-primary" />;
        } else if (line.includes('✨') || line.includes('🚀') || line.includes('📍')) {
          return <p key={index} dangerouslySetInnerHTML={{ __html: formatted }} className="text-sm font-medium text-foreground mt-2" />;
        } else if (line.startsWith('•')) {
          return <p key={index} dangerouslySetInnerHTML={{ __html: formatted }} className="text-sm text-muted-foreground ml-2" />;
        } else {
          return <p key={index} dangerouslySetInnerHTML={{ __html: formatted }} className="text-sm text-muted-foreground" />;
        }
      })
      .filter(Boolean); // Remove null entries
  };

  return (
    <Card className={cn(
      "transition-all hover:shadow-lg",
      isNewResult && "animate-slide-in-up border-primary"
    )}>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <CardTitle className="text-xl mb-2">{job.title}</CardTitle>
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2 text-muted-foreground">
                <Building2 className="h-4 w-4" />
                <span className="font-medium">{job.company}</span>
              </div>
              <div className="flex items-center gap-2 text-muted-foreground">
                <MapPin className="h-4 w-4" />
                <span className="text-sm">{job.location}</span>
              </div>
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <Badge variant={getMatchScoreBadgeVariant(score)} className="text-base px-3 py-1">
              <TrendingUp className="h-4 w-4 mr-1" />
              {score}% Match
            </Badge>
          </div>
        </div>
      </CardHeader>

      {job.description && (
        <CardContent className="border-t pt-4">
          <div className="text-sm text-muted-foreground line-clamp-2">
            {job.description}
          </div>
        </CardContent>
      )}

      <CardContent className="border-t pt-4">
        <div className="space-y-4">
          {/* Required Skills */}
          {(job.required_skills && job.required_skills.length > 0) && (
            <div>
              <h4 className="font-semibold text-sm mb-2 flex items-center gap-2">
                <span className="text-primary">•</span>
                Required Skills
              </h4>
              <div className="flex flex-wrap gap-1">
                {job.required_skills.slice(0, 6).map((skill, index) => (
                  <Badge key={index} variant="outline" className="text-xs">
                    {skill}
                  </Badge>
                ))}
                {job.required_skills.length > 6 && (
                  <Badge variant="outline" className="text-xs">
                    +{job.required_skills.length - 6} more
                  </Badge>
                )}
              </div>
            </div>
          )}

          {/* Match Analysis */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-primary" />
              <h4 className="font-semibold text-sm">AI Career Fit Analysis</h4>
            </div>
            <div className="space-y-1">
              {formatMatchDescription(job.match_description)}
            </div>
          </div>
        </div>
      </CardContent>

      {(job.apply_link || job.url) && (
        <CardFooter className="border-t">
          <Button 
            className="w-full"
            onClick={() => window.open(job.apply_link || job.url, '_blank', 'noopener,noreferrer')}
          >
            <ExternalLink className="h-4 w-4 mr-2" />
            Apply Now
          </Button>
        </CardFooter>
      )}
    </Card>
  );
};

export default JobCard;
