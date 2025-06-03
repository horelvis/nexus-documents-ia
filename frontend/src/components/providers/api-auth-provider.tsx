'use client';

import { useAuth } from '@clerk/nextjs';
import { useEffect } from 'react';
import { setAuthContext } from '@/lib/api';

interface ApiAuthProviderProps {
  children: React.ReactNode;
}

export function ApiAuthProvider({ children }: ApiAuthProviderProps) {
  const { getToken, userId, isLoaded } = useAuth();

  useEffect(() => {
    if (isLoaded) {
      // Set the global auth context for API calls
      setAuthContext(getToken, userId);
    }
  }, [getToken, userId, isLoaded]);

  return <>{children}</>;
}