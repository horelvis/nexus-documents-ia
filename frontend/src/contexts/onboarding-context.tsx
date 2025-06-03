"use client";

import React, { createContext, useContext, useState, useEffect } from 'react';
import { useCurrentUser } from '@/hooks/use-api';

export interface OnboardingStep {
  id: string;
  title: string;
  description: string;
  completed: boolean;
  optional?: boolean;
}

export interface OnboardingState {
  isOnboardingComplete: boolean;
  currentStep: number;
  steps: OnboardingStep[];
  hasSeenWelcome: boolean;
}

interface OnboardingContextType {
  state: OnboardingState;
  completeStep: (stepId: string) => void;
  goToStep: (stepIndex: number) => void;
  skipOnboarding: () => void;
  restartOnboarding: () => void;
  markWelcomeSeen: () => void;
}

const OnboardingContext = createContext<OnboardingContextType | undefined>(undefined);

const INITIAL_STEPS: OnboardingStep[] = [
  {
    id: 'welcome',
    title: 'Welcome to Nexus',
    description: 'Get familiar with our AI-powered document management platform',
    completed: false,
  },
  {
    id: 'profile_setup',
    title: 'Complete Your Profile',
    description: 'Set up your profile information and preferences',
    completed: false,
  },
  {
    id: 'first_upload',
    title: 'Upload Your First Document',
    description: 'Learn how to upload and organize your documents',
    completed: false,
  },
  {
    id: 'explore_search',
    title: 'Try Document Search',
    description: 'Discover how to find information in your documents',
    completed: false,
  },
  {
    id: 'chat_tutorial',
    title: 'Chat with Your Documents',
    description: 'Learn how to ask questions about your documents',
    completed: false,
  },
  {
    id: 'dashboard_tour',
    title: 'Explore Your Dashboard',
    description: 'Get familiar with your document dashboard',
    completed: false,
  },
];

const STORAGE_KEY = 'nexus_onboarding_state';

export function OnboardingProvider({ children }: { children: React.ReactNode }) {
  const { user } = useCurrentUser();
  const [state, setState] = useState<OnboardingState>({
    isOnboardingComplete: false,
    currentStep: 0,
    steps: INITIAL_STEPS,
    hasSeenWelcome: false,
  });

  // Load onboarding state from localStorage
  useEffect(() => {
    if (typeof window !== 'undefined' && user) {
      const stored = localStorage.getItem(`${STORAGE_KEY}_${user.id}`);
      if (stored) {
        try {
          const parsedState = JSON.parse(stored);
          setState(parsedState);
        } catch (error) {
          console.error('Error parsing onboarding state:', error);
        }
      }
    }
  }, [user]);

  // Save onboarding state to localStorage
  useEffect(() => {
    if (typeof window !== 'undefined' && user) {
      localStorage.setItem(`${STORAGE_KEY}_${user.id}`, JSON.stringify(state));
    }
  }, [state, user]);

  const completeStep = (stepId: string) => {
    setState(prevState => {
      const newSteps = prevState.steps.map(step =>
        step.id === stepId ? { ...step, completed: true } : step
      );
      
      const completedSteps = newSteps.filter(step => step.completed).length;
      const isComplete = completedSteps === newSteps.length;
      
      // If current step is completed, move to next step
      const currentStepIndex = prevState.steps.findIndex(step => step.id === stepId);
      const nextStep = currentStepIndex < newSteps.length - 1 ? currentStepIndex + 1 : currentStepIndex;
      
      return {
        ...prevState,
        steps: newSteps,
        isOnboardingComplete: isComplete,
        currentStep: isComplete ? prevState.currentStep : nextStep,
      };
    });
  };

  const goToStep = (stepIndex: number) => {
    setState(prevState => ({
      ...prevState,
      currentStep: Math.max(0, Math.min(stepIndex, prevState.steps.length - 1)),
    }));
  };

  const skipOnboarding = () => {
    setState(prevState => ({
      ...prevState,
      isOnboardingComplete: true,
      hasSeenWelcome: true,
    }));
  };

  const restartOnboarding = () => {
    setState({
      isOnboardingComplete: false,
      currentStep: 0,
      steps: INITIAL_STEPS.map(step => ({ ...step, completed: false })),
      hasSeenWelcome: false,
    });
  };

  const markWelcomeSeen = () => {
    setState(prevState => ({
      ...prevState,
      hasSeenWelcome: true,
    }));
  };

  return (
    <OnboardingContext.Provider value={{
      state,
      completeStep,
      goToStep,
      skipOnboarding,
      restartOnboarding,
      markWelcomeSeen,
    }}>
      {children}
    </OnboardingContext.Provider>
  );
}

export function useOnboarding() {
  const context = useContext(OnboardingContext);
  if (context === undefined) {
    throw new Error('useOnboarding must be used within an OnboardingProvider');
  }
  return context;
}