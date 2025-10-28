import React, { useState } from 'react';
import { Job } from '../types';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { MapPin, ExternalLink, Building2, TrendingUp, Brain, ChevronDown, ChevronUp, AlertTriangle, Clock } from 'lucide-react';
import { cn } from '../lib/utils';

interface JobCardProps {
  job: Job;
  isNewResult?: boolean;
}

const JobCard: React.FC<JobCardProps> = ({ job, isNewResult = false }) => {
  const [showAIReasoning, setShowAIReasoning] = useState(false);

  const getMatchScoreBadgeVariant = (score: number): 'default' | 'secondary' | 'destructive' | 'outline' => {
    if (score >= 70) return 'default';
    if (score >= 40) return 'secondary';
    return 'outline';
  };

  const score = job.match_score || job.score || 0;
  const hasAIReasoning = job.ai_reasoning && job.ai_reasoning.reasoning;

  // Calculate time ago from first_seen
  const getTimeAgo = (dateString?: string): string => {
    if (!dateString) return '';

    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 60) {
      return `${diffMins} minute${diffMins !== 1 ? 's' : ''} ago`;
    } else if (diffHours < 24) {
      return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
    } else if (diffDays === 1) {
      return 'Yesterday';
    } else if (diffDays < 7) {
      return `${diffDays} days ago`;
    } else if (diffDays < 30) {
      const weeks = Math.floor(diffDays / 7);
      return `${weeks} week${weeks !== 1 ? 's' : ''} ago`;
    } else {
      const months = Math.floor(diffDays / 30);
      return `${months} month${months !== 1 ? 's' : ''} ago`;
    }
  };

  // Check if job is new (posted within last 48 hours)
  const isNewJob = (dateString?: string): boolean => {
    if (!dateString) return false;
    const date = new Date(dateString);
    const now = new Date();
    const diffHours = (now.getTime() - date.getTime()) / 3600000;
    return diffHours <= 48;
  };

  const timeAgo = getTimeAgo(job.first_seen);
  const showNewBadge = isNewJob(job.first_seen);

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
            <div className="flex items-center gap-2 mb-2">
              <CardTitle className="text-xl">{job.title}</CardTitle>
              {showNewBadge && (
                <Badge variant="default" className="text-xs px-2 py-0.5 bg-green-600 hover:bg-green-700">
                  NEW
                </Badge>
              )}
            </div>
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2 text-muted-foreground">
                <Building2 className="h-4 w-4" />
                <span className="font-medium">{job.company}</span>
              </div>
              <div className="flex items-center gap-2 text-muted-foreground">
                <MapPin className="h-4 w-4" />
                <span className="text-sm">{job.location}</span>
              </div>
              {timeAgo && (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Clock className="h-4 w-4" />
                  <span className="text-sm">Posted {timeAgo}</span>
                </div>
              )}
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

          {/* AI Reasoning Section - Only show for "think deeper" results */}
          {hasAIReasoning && (
            <div className="space-y-3 border-t pt-4">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowAIReasoning(!showAIReasoning)}
                className="flex items-center gap-2 h-auto p-2 justify-start w-full text-left"
              >
                <Brain className="h-4 w-4 text-blue-600" />
                <span className="font-semibold text-sm">AI Reasoning</span>
                <Badge variant="outline" className="text-xs ml-auto">
                  Think Deeper
                </Badge>
                {showAIReasoning ? (
                  <ChevronUp className="h-4 w-4 ml-1" />
                ) : (
                  <ChevronDown className="h-4 w-4 ml-1" />
                )}
              </Button>

              {showAIReasoning && job.ai_reasoning && (
                <div className="space-y-3 bg-blue-50/50 rounded-lg p-4 border border-blue-100">
                  {/* Complexity Analysis */}
                  <div>
                    <h5 className="font-medium text-sm text-blue-900 mb-2">Resume Complexity Assessment</h5>
                    <div className="flex items-center gap-2 mb-1">
                      <Badge variant={
                        job.ai_reasoning.resume_complexity === 'ADVANCED' ? 'default' :
                        job.ai_reasoning.resume_complexity === 'INTERMEDIATE' ? 'secondary' : 'outline'
                      } className="text-xs">
                        {job.ai_reasoning.resume_complexity}
                      </Badge>
                      <span className="text-sm text-muted-foreground">
                        ({job.ai_reasoning.complexity_score}/100)
                      </span>
                    </div>
                  </div>

                  {/* Experience Match */}
                  <div>
                    <h5 className="font-medium text-sm text-blue-900 mb-1">Experience Level Match</h5>
                    <Badge variant={
                      job.ai_reasoning.experience_match === 'excellent' ? 'default' :
                      job.ai_reasoning.experience_match === 'good' ? 'secondary' : 'outline'
                    } className="text-xs">
                      {job.ai_reasoning.experience_match}
                    </Badge>
                  </div>

                  {/* AI Reasoning */}
                  <div>
                    <h5 className="font-medium text-sm text-blue-900 mb-2">AI Analysis</h5>
                    <p className="text-sm text-blue-800 leading-relaxed">
                      {job.ai_reasoning.reasoning}
                    </p>
                  </div>

                  {/* Skill Matches - Always show this section */}
                  <div>
                    <h5 className="font-medium text-sm text-green-900 mb-2">✅ Your Matching Skills</h5>
                    {job.ai_reasoning.skill_matches && job.ai_reasoning.skill_matches.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {job.ai_reasoning.skill_matches.map((skill, index) => (
                          <Badge key={index} variant="default" className="text-xs bg-green-100 text-green-800 border-green-300">
                            {skill}
                          </Badge>
                        ))}
                      </div>
                    ) : (
                      <div className="text-sm text-gray-600 italic bg-gray-50 p-2 rounded border">
                        No skills matched to this job
                      </div>
                    )}
                  </div>

                  {/* Skill Gaps - Always show this section */}
                  <div>
                    <h5 className="font-medium text-sm text-orange-900 mb-2">📚 Skills to Develop</h5>
                    {job.ai_reasoning.skill_gaps && job.ai_reasoning.skill_gaps.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {job.ai_reasoning.skill_gaps.slice(0, 5).map((skill, index) => (
                          <Badge key={index} variant="outline" className="text-xs border-orange-300 text-orange-800">
                            {skill}
                          </Badge>
                        ))}
                        {job.ai_reasoning.skill_gaps.length > 5 && (
                          <Badge variant="outline" className="text-xs border-orange-300 text-orange-800">
                            +{job.ai_reasoning.skill_gaps.length - 5} more
                          </Badge>
                        )}
                      </div>
                    ) : (
                      <div className="text-sm text-gray-600 italic bg-gray-50 p-2 rounded border">
                        No additional skills required
                      </div>
                    )}
                  </div>

                  {/* Red Flags */}
                  {job.ai_reasoning.red_flags && job.ai_reasoning.red_flags.length > 0 && (
                    <div>
                      <h5 className="font-medium text-sm text-red-900 mb-2 flex items-center gap-2">
                        <AlertTriangle className="h-4 w-4" />
                        Considerations
                      </h5>
                      <ul className="space-y-1">
                        {job.ai_reasoning.red_flags.map((flag, index) => (
                          <li key={index} className="text-sm text-red-800 flex items-start gap-2">
                            <span className="text-red-500 mt-1">•</span>
                            {flag}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
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
