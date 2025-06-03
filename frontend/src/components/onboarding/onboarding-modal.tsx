"use client";

import { useOnboarding } from '@/contexts/onboarding-context';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { 
  ArrowRight, 
  ArrowLeft, 
  X, 
  CheckCircle, 
  Circle,
  Sparkles,
  User,
  Upload,
  Search,
  MessageSquare,
  LayoutDashboard
} from 'lucide-react';
import { useState } from 'react';

const stepIcons: Record<string, React.ComponentType<any>> = {
  welcome: Sparkles,
  profile_setup: User,
  first_upload: Upload,
  explore_search: Search,
  chat_tutorial: MessageSquare,
  dashboard_tour: LayoutDashboard,
};

export function OnboardingModal() {
  const { state, completeStep, goToStep, skipOnboarding, markWelcomeSeen } = useOnboarding();
  const [isOpen, setIsOpen] = useState(!state.isOnboardingComplete && !state.hasSeenWelcome);

  const currentStep = state.steps[state.currentStep];
  const completedSteps = state.steps.filter(step => step.completed).length;
  const progressPercentage = (completedSteps / state.steps.length) * 100;

  const handleNext = () => {
    if (state.currentStep < state.steps.length - 1) {
      goToStep(state.currentStep + 1);
    } else {
      // Onboarding complete
      setIsOpen(false);
      skipOnboarding();
    }
  };

  const handlePrevious = () => {
    if (state.currentStep > 0) {
      goToStep(state.currentStep - 1);
    }
  };

  const handleSkip = () => {
    setIsOpen(false);
    skipOnboarding();
  };

  const handleStepClick = (stepIndex: number) => {
    goToStep(stepIndex);
  };

  const handleClose = () => {
    setIsOpen(false);
    markWelcomeSeen();
  };

  if (!isOpen || state.isOnboardingComplete) {
    return null;
  }

  const StepIcon = stepIcons[currentStep?.id] || Circle;

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-gray-900">Getting Started</h2>
            <p className="text-gray-600">Let's set up your Nexus experience</p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleClose}
            className="text-gray-400 hover:text-gray-600"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Progress Bar */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-700">
              Progress: {completedSteps} of {state.steps.length} steps
            </span>
            <span className="text-sm text-gray-500">{Math.round(progressPercentage)}% complete</span>
          </div>
          <Progress value={progressPercentage} className="h-2" />
        </div>

        {/* Steps Navigation */}
        <div className="grid grid-cols-3 lg:grid-cols-6 gap-2 mb-8">
          {state.steps.map((step, index) => {
            const Icon = stepIcons[step.id] || Circle;
            const isActive = index === state.currentStep;
            const isCompleted = step.completed;
            
            return (
              <button
                key={step.id}
                onClick={() => handleStepClick(index)}
                className={`p-3 rounded-lg border-2 transition-all ${
                  isActive
                    ? 'border-blue-500 bg-blue-50'
                    : isCompleted
                    ? 'border-green-500 bg-green-50'
                    : 'border-gray-200 bg-gray-50 hover:border-gray-300'
                }`}
              >
                <div className="flex flex-col items-center space-y-1">
                  {isCompleted ? (
                    <CheckCircle className="h-5 w-5 text-green-500" />
                  ) : (
                    <Icon className={`h-5 w-5 ${isActive ? 'text-blue-500' : 'text-gray-400'}`} />
                  )}
                  <span className={`text-xs font-medium ${
                    isActive ? 'text-blue-700' : isCompleted ? 'text-green-700' : 'text-gray-500'
                  }`}>
                    {step.title.split(' ')[0]}
                  </span>
                </div>
              </button>
            );
          })}
        </div>

        {/* Current Step Content */}
        <Card className="mb-8">
          <CardHeader>
            <div className="flex items-center space-x-3">
              <div className={`p-3 rounded-lg ${
                currentStep?.completed ? 'bg-green-100' : 'bg-blue-100'
              }`}>
                <StepIcon className={`h-6 w-6 ${
                  currentStep?.completed ? 'text-green-600' : 'text-blue-600'
                }`} />
              </div>
              <div>
                <CardTitle className="flex items-center space-x-2">
                  <span>{currentStep?.title}</span>
                  {currentStep?.completed && (
                    <Badge variant="default" className="bg-green-500">
                      <CheckCircle className="h-3 w-3 mr-1" />
                      Complete
                    </Badge>
                  )}
                </CardTitle>
                <CardDescription>{currentStep?.description}</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <OnboardingStepContent stepId={currentStep?.id} />
          </CardContent>
        </Card>

        {/* Navigation Buttons */}
        <div className="flex items-center justify-between">
          <div className="flex space-x-2">
            <Button
              variant="outline"
              onClick={handlePrevious}
              disabled={state.currentStep === 0}
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              Previous
            </Button>
            <Button variant="ghost" onClick={handleSkip}>
              Skip Tour
            </Button>
          </div>
          
          <Button onClick={handleNext}>
            {state.currentStep === state.steps.length - 1 ? 'Finish' : 'Next'}
            {state.currentStep < state.steps.length - 1 && (
              <ArrowRight className="h-4 w-4 ml-2" />
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function OnboardingStepContent({ stepId }: { stepId: string }) {
  const { completeStep } = useOnboarding();

  const handleMarkComplete = () => {
    completeStep(stepId);
  };

  switch (stepId) {
    case 'welcome':
      return (
        <div className="space-y-4">
          <div className="bg-gradient-to-r from-blue-50 to-purple-50 p-6 rounded-lg">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              Welcome to Nexus Document Management! 🎉
            </h3>
            <p className="text-gray-600 mb-4">
              Transform how you manage documents with AI-powered features:
            </p>
            <ul className="space-y-2 text-sm text-gray-600">
              <li className="flex items-center space-x-2">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <span>Upload and organize any document type</span>
              </li>
              <li className="flex items-center space-x-2">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <span>Search through your documents with AI</span>
              </li>
              <li className="flex items-center space-x-2">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <span>Chat with your documents to get answers</span>
              </li>
              <li className="flex items-center space-x-2">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <span>Generate summaries and insights</span>
              </li>
            </ul>
          </div>
          <Button onClick={handleMarkComplete} className="w-full">
            Let's Get Started!
          </Button>
        </div>
      );

    case 'profile_setup':
      return (
        <div className="space-y-4">
          <p className="text-gray-600">
            Your profile is automatically set up with your account information. 
            You can update your preferences anytime in the settings.
          </p>
          <div className="bg-gray-50 p-4 rounded-lg">
            <h4 className="font-medium text-gray-900 mb-2">Profile Status:</h4>
            <div className="space-y-2">
              <div className="flex items-center space-x-2">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <span className="text-sm">Account verified</span>
              </div>
              <div className="flex items-center space-x-2">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <span className="text-sm">Profile information synced</span>
              </div>
              <div className="flex items-center space-x-2">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <span className="text-sm">Ready to upload documents</span>
              </div>
            </div>
          </div>
          <Button onClick={handleMarkComplete} className="w-full">
            Profile Setup Complete
          </Button>
        </div>
      );

    case 'first_upload':
      return (
        <div className="space-y-4">
          <p className="text-gray-600">
            Upload your first document to get started. We support PDF, Word, text files, and more.
          </p>
          <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
            <Upload className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-500 mb-4">
              Click "Upload Document" in your dashboard to add your first file
            </p>
            <p className="text-sm text-gray-400">
              Supported formats: PDF, DOC, DOCX, TXT, MD, CSV, XLS, XLSX
            </p>
          </div>
          <Button onClick={handleMarkComplete} className="w-full">
            I'll Upload a Document
          </Button>
        </div>
      );

    case 'explore_search':
      return (
        <div className="space-y-4">
          <p className="text-gray-600">
            Once you have documents, use our powerful search to find information quickly.
          </p>
          <div className="bg-blue-50 p-4 rounded-lg">
            <h4 className="font-medium text-blue-900 mb-2">Search Features:</h4>
            <ul className="space-y-1 text-sm text-blue-800">
              <li>• Search by keywords across all documents</li>
              <li>• Filter by tags, date, or file type</li>
              <li>• AI-powered semantic search</li>
              <li>• Find similar documents</li>
            </ul>
          </div>
          <Button onClick={handleMarkComplete} className="w-full">
            Got it, I'll try searching
          </Button>
        </div>
      );

    case 'chat_tutorial':
      return (
        <div className="space-y-4">
          <p className="text-gray-600">
            Chat with your documents to ask questions and get intelligent answers.
          </p>
          <div className="bg-purple-50 p-4 rounded-lg">
            <h4 className="font-medium text-purple-900 mb-2">Try asking:</h4>
            <ul className="space-y-1 text-sm text-purple-800">
              <li>• "What are the key points in my contract?"</li>
              <li>• "Summarize this research paper"</li>
              <li>• "Find all mentions of budget in my reports"</li>
              <li>• "What are the action items from this meeting?"</li>
            </ul>
          </div>
          <Button onClick={handleMarkComplete} className="w-full">
            Ready to Chat with Documents
          </Button>
        </div>
      );

    case 'dashboard_tour':
      return (
        <div className="space-y-4">
          <p className="text-gray-600">
            Your dashboard gives you an overview of all your documents and activity.
          </p>
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-gray-50 p-3 rounded-lg">
              <h5 className="font-medium text-gray-900 text-sm mb-1">Stats Cards</h5>
              <p className="text-xs text-gray-600">Track your document count and storage</p>
            </div>
            <div className="bg-gray-50 p-3 rounded-lg">
              <h5 className="font-medium text-gray-900 text-sm mb-1">Quick Actions</h5>
              <p className="text-xs text-gray-600">Upload, search, and chat buttons</p>
            </div>
            <div className="bg-gray-50 p-3 rounded-lg">
              <h5 className="font-medium text-gray-900 text-sm mb-1">Recent Documents</h5>
              <p className="text-xs text-gray-600">Your latest uploaded files</p>
            </div>
            <div className="bg-gray-50 p-3 rounded-lg">
              <h5 className="font-medium text-gray-900 text-sm mb-1">User Menu</h5>
              <p className="text-xs text-gray-600">Profile and settings access</p>
            </div>
          </div>
          <Button onClick={handleMarkComplete} className="w-full">
            Finish Onboarding
          </Button>
        </div>
      );

    default:
      return (
        <div className="text-center py-8">
          <p className="text-gray-500">Step content not found</p>
        </div>
      );
  }
}