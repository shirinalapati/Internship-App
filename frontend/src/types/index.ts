export interface User {
  name?: string;
  email: string;
  provider: string;
}

export interface Job {
  title: string;
  company: string;
  location: string;
  description?: string;
  score?: number;
  match_score?: number;
  match_description: string;
  apply_link?: string;
  requirements?: string[];
  required_skills?: string[];
  url?: string;
}

export interface MatchResults {
  jobs: Job[];
  error?: string;
}