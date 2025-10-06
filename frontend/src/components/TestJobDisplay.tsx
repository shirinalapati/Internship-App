import React from 'react';
import { Job } from '../types';
import JobCard from './JobCard';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';

const TestJobDisplay: React.FC = () => {
  // Sample job data to test the display format
  const sampleJobs: Job[] = [
    {
      title: "Software Engineer Intern",
      company: "Google",
      location: "Mountain View, CA",
      match_score: 95,
      match_description: "🎯 Compatibility Score: 95/100\n\n✨ Why This Role Fits You:\nPerfect skill match with excellent growth opportunities in frontend development\n\n🚀 Growth Opportunities:\n• Skill Development: Advanced React patterns, TypeScript, cloud technologies\n• Career Impact: Strong foundation for senior developer career\n• Growth Potential: High\n\n📍 Location: Mountain View, CA",
      apply_link: "https://careers.google.com/jobs/123",
      required_skills: ["Python", "JavaScript", "React", "TypeScript", "AWS"]
    },
    {
      title: "Frontend Developer Intern",
      company: "Meta",
      location: "Menlo Park, CA", 
      match_score: 88,
      match_description: "🎯 Compatibility Score: 88/100\n\n✨ Why This Role Fits You:\nStrong alignment with React expertise and frontend development focus\n\n🚀 Growth Opportunities:\n• Skill Development: React Native, GraphQL, advanced state management\n• Career Impact: Experience with large-scale applications\n• Growth Potential: High\n\n📍 Location: Menlo Park, CA",
      apply_link: "https://careers.meta.com/jobs/456", 
      required_skills: ["React", "JavaScript", "CSS", "HTML"]
    },
    {
      title: "Backend Engineer Intern",
      company: "Netflix",
      location: "Los Gatos, CA",
      match_score: 75,
      match_description: "🎯 Compatibility Score: 75/100\n\n✨ Why This Role Fits You:\nGood Python skills with opportunity to learn backend architecture\n\n🚀 Growth Opportunities:\n• Skill Development: Microservices, distributed systems, Python frameworks\n• Career Impact: Large-scale backend systems experience\n• Growth Potential: Medium-High\n\n📍 Location: Los Gatos, CA",
      apply_link: "https://jobs.netflix.com/jobs/789",
      required_skills: ["Python", "SQL", "AWS", "Docker", "Microservices"]
    }
  ];

  return (
    <div className="space-y-6 p-6">
      <Card>
        <CardHeader>
          <CardTitle>Test Job Display Component</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            This component tests the job display format with sample intelligent matching data.
          </p>
        </CardContent>
      </Card>

      <div className="space-y-6">
        <div className="text-center">
          <h2 className="text-2xl font-bold">Sample Job Results</h2>
          <p className="text-muted-foreground mt-2">
            Testing display of {sampleJobs.length} intelligent job matches
          </p>
        </div>

        <div className="grid gap-6 max-w-4xl mx-auto">
          {sampleJobs.map((job, index) => (
            <JobCard key={index} job={job} />
          ))}
        </div>
      </div>
    </div>
  );
};

export default TestJobDisplay;