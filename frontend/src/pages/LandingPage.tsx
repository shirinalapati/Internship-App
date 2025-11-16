import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useUser } from '@stackframe/react';
import Header from '../components/Header';
import { Hero } from '../components/ui/animated-hero';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Sparkles, Zap, Target, TrendingUp, ArrowRight, CheckCircle2 } from 'lucide-react';

const LandingPage: React.FC = () => {
  const navigate = useNavigate();
  const user = useUser();

  const handleGetStarted = () => {
    navigate('/find');
  };

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="space-y-20 pb-12">
        {/* Animated Hero Section */}
        <Hero />

        {/* Features Section */}
        <section className="container grid md:grid-cols-3 gap-8 max-w-6xl mx-auto">
          <Card className="border-2 hover:border-primary transition-colors">
            <CardHeader>
              <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center mb-4">
                <Zap className="h-6 w-6 text-primary" />
              </div>
              <CardTitle>Lightning Fast Matching</CardTitle>
              <CardDescription>
                Our AI analyzes thousands of internships in seconds to find your perfect match
              </CardDescription>
            </CardHeader>
          </Card>

          <Card className="border-2 hover:border-primary transition-colors">
            <CardHeader>
              <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center mb-4">
                <Target className="h-6 w-6 text-primary" />
              </div>
              <CardTitle>Smart Skill Detection</CardTitle>
              <CardDescription>
                Advanced AI extracts and matches your skills with job requirements automatically
              </CardDescription>
            </CardHeader>
          </Card>

          <Card className="border-2 hover:border-primary transition-colors">
            <CardHeader>
              <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center mb-4">
                <TrendingUp className="h-6 w-6 text-primary" />
              </div>
              <CardTitle>Compatibility Scoring</CardTitle>
              <CardDescription>
                Each opportunity is scored based on your unique profile for better decision making
              </CardDescription>
            </CardHeader>
          </Card>
        </section>

        {/* How It Works Section */}
        <section id="how-it-works" className="container max-w-4xl mx-auto space-y-8">
          <div className="text-center space-y-4">
            <h2 className="text-4xl md:text-5xl font-bold">How It Works</h2>
            <p className="text-xl text-muted-foreground">
              Three simple steps to find your dream internship
            </p>
          </div>

          <div className="space-y-6">
            <Card className="border-l-4 border-l-primary">
              <CardContent className="pt-6">
                <div className="flex items-start gap-4">
                  <div className="h-10 w-10 rounded-full bg-primary text-primary-foreground flex items-center justify-center font-bold text-lg flex-shrink-0">
                    1
                  </div>
                  <div>
                    <h3 className="text-xl font-semibold mb-2">Upload Your Resume</h3>
                    <p className="text-muted-foreground">
                      Simply upload your resume in PDF or image format. Our system supports various formats
                      and automatically extracts relevant information.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="border-l-4 border-l-primary">
              <CardContent className="pt-6">
                <div className="flex items-start gap-4">
                  <div className="h-10 w-10 rounded-full bg-primary text-primary-foreground flex items-center justify-center font-bold text-lg flex-shrink-0">
                    2
                  </div>
                  <div>
                    <h3 className="text-xl font-semibold mb-2">AI Analysis & Matching</h3>
                    <p className="text-muted-foreground">
                      Our advanced AI analyzes your skills, experience, and education to intelligently
                      match you with internship opportunities from top companies.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="border-l-4 border-l-primary">
              <CardContent className="pt-6">
                <div className="flex items-start gap-4">
                  <div className="h-10 w-10 rounded-full bg-primary text-primary-foreground flex items-center justify-center font-bold text-lg flex-shrink-0">
                    3
                  </div>
                  <div>
                    <h3 className="text-xl font-semibold mb-2">Review & Apply</h3>
                    <p className="text-muted-foreground">
                      Browse your personalized matches sorted by compatibility score. Each listing shows
                      exactly why it matches your profile and provides direct application links.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </section>

        {/* Benefits Section */}
        <section className="container max-w-4xl mx-auto space-y-8 bg-muted/50 rounded-lg p-8 md:p-12">
          <div className="text-center space-y-4">
            <h2 className="text-4xl md:text-5xl font-bold">Why Choose Us?</h2>
          </div>

          <div className="grid md:grid-cols-2 gap-6">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="h-6 w-6 text-primary flex-shrink-0 mt-1" />
              <div>
                <h4 className="font-semibold mb-1">Comprehensive Job Database</h4>
                <p className="text-muted-foreground text-sm">
                  Access thousands of internships from GitHub, LinkedIn, and other top platforms
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <CheckCircle2 className="h-6 w-6 text-primary flex-shrink-0 mt-1" />
              <div>
                <h4 className="font-semibold mb-1">Real-time Updates</h4>
                <p className="text-muted-foreground text-sm">
                  Our database is constantly updated with the latest opportunities
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <CheckCircle2 className="h-6 w-6 text-primary flex-shrink-0 mt-1" />
              <div>
                <h4 className="font-semibold mb-1">Privacy Focused</h4>
                <p className="text-muted-foreground text-sm">
                  Your resume data is securely stored and never shared with third parties
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <CheckCircle2 className="h-6 w-6 text-primary flex-shrink-0 mt-1" />
              <div>
                <h4 className="font-semibold mb-1">No Cost, No Hassle</h4>
                <p className="text-muted-foreground text-sm">
                  Completely free to use - just upload and start matching
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* CTA Section */}
        <section className="container text-center space-y-6 py-12">
          <h2 className="text-4xl md:text-5xl font-bold max-w-3xl mx-auto">
            Ready to Find Your Dream Internship?
          </h2>
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
            Join thousands of students who have found their perfect internship match
          </p>
          <Button
            size="lg"
            className="text-lg px-8 py-6 h-auto"
            onClick={handleGetStarted}
          >
            <Sparkles className="h-5 w-5 mr-2" />
            Upload Your Resume Now
            <ArrowRight className="h-5 w-5 ml-2" />
          </Button>
        </section>
      </main>
    </div>
  );
};

export default LandingPage;