import { useUser, useAuth } from '@clerk/nextjs';
import { useEffect, useState } from 'react';
import { api, Document, User } from '@/lib/api';
import { toast } from 'sonner';

// Generic hook for API calls
export function useApiCall<T>(
  apiCall: () => Promise<T>,
  dependencies: any[] = []
) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let mounted = true;

    const fetchData = async () => {
      try {
        setLoading(true);
        setError(null);
        const result = await apiCall();
        if (mounted) {
          setData(result);
        }
      } catch (err) {
        if (mounted) {
          setError(err as Error);
          console.error('API call failed:', err);
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };

    fetchData();

    return () => {
      mounted = false;
    };
  }, dependencies);

  return { data, loading, error, refetch: () => useApiCall(apiCall, dependencies) };
}

// Hook for current user data
export function useCurrentUser() {
  const { user: clerkUser, isLoaded } = useUser();
  const { getToken, isSignedIn } = useAuth();
  const [backendUser, setBackendUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!isLoaded) return;

    const syncAndFetchUser = async () => {
      console.log('👤 useCurrentUser - Starting sync process', {
        clerkUser: !!clerkUser,
        isSignedIn,
        userId: clerkUser?.id
      });

      if (!clerkUser || !isSignedIn) {
        console.log('👤 No user or not signed in, skipping sync');
        setBackendUser(null);
        setLoading(false);
        return;
      }

      try {
        console.log('👤 Starting user sync and fetch...');
        setLoading(true);
        setError(null);

        // Get the token from Clerk
        console.log('🔑 Getting token from Clerk...');
        const token = await getToken();
        
        if (!token) {
          throw new Error('No authentication token available');
        }
        console.log('🔑 Token obtained successfully');

        // First, sync the user with our backend
        console.log('🔄 Syncing user with backend...');
        await api.auth.syncUser({
          clerk_user_id: clerkUser.id,
          email: clerkUser.emailAddresses[0]?.emailAddress || '',
          full_name: clerkUser.fullName || clerkUser.firstName || 'User',
        });
        console.log('✅ User sync completed');

        // Then fetch the complete user data
        console.log('📥 Fetching current user data...');
        const userData = await api.auth.getCurrentUser();
        console.log('✅ User data fetched successfully:', userData);
        setBackendUser(userData);
      } catch (err) {
        console.error('❌ Error in useCurrentUser:', err);
        setError(err as Error);
        setBackendUser(null);
        
        // Si el error es de autenticación (401), no reintentar automáticamente
        if (err instanceof Error && err.message.includes('401')) {
          console.log('🚫 Authentication error, stopping sync attempts');
        }
      } finally {
        setLoading(false);
      }
    };

    syncAndFetchUser();
  }, [clerkUser, isLoaded, isSignedIn, getToken]);

  return { user: backendUser, loading, error, clerkUser };
}

// Hook for documents
export function useDocuments(params?: {
  page?: number;
  per_page?: number;
  tags?: string[];
  date_from?: string;
  date_to?: string;
}) {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [pagination, setPagination] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchDocuments = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await api.documents.list(params);
      setDocuments(response.data);
      setPagination(response.pagination);
    } catch (err) {
      setError(err as Error);
      toast.error('Failed to load documents');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, [params?.page, params?.per_page, params?.tags?.join(','), params?.date_from, params?.date_to]);

  const uploadDocument = async (file: File, metadata: { title: string; description?: string; tags?: string[] }) => {
    try {
      setLoading(true);
      const response = await api.documents.upload(file, metadata);
      toast.success('Document uploaded successfully');
      await fetchDocuments(); // Refresh the list
      return response;
    } catch (err) {
      toast.error('Failed to upload document');
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const deleteDocument = async (id: string) => {
    try {
      await api.documents.delete(id);
      toast.success('Document deleted successfully');
      await fetchDocuments(); // Refresh the list
    } catch (err) {
      toast.error('Failed to delete document');
      throw err;
    }
  };

  return {
    documents,
    pagination,
    loading,
    error,
    refetch: fetchDocuments,
    uploadDocument,
    deleteDocument,
  };
}

// Hook for a single document
export function useDocument(id: string) {
  const [document, setDocument] = useState<Document | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchDocument = async () => {
    if (!id) return;
    
    try {
      setLoading(true);
      setError(null);
      const doc = await api.documents.get(id);
      setDocument(doc);
    } catch (err) {
      setError(err as Error);
      toast.error('Failed to load document');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocument();
  }, [id]);

  const generateSummary = async () => {
    try {
      const response = await api.documents.generateSummary(id);
      toast.success('Summary generated successfully');
      return response;
    } catch (err) {
      toast.error('Failed to generate summary');
      throw err;
    }
  };

  const addTag = async (tagName: string) => {
    try {
      await api.documents.addTag(id, tagName);
      toast.success('Tag added successfully');
      await fetchDocument(); // Refresh document data
    } catch (err) {
      toast.error('Failed to add tag');
      throw err;
    }
  };

  const removeTag = async (tagName: string) => {
    try {
      await api.documents.removeTag(id, tagName);
      toast.success('Tag removed successfully');
      await fetchDocument(); // Refresh document data
    } catch (err) {
      toast.error('Failed to remove tag');
      throw err;
    }
  };

  const getDownloadUrl = async () => {
    try {
      const response = await api.documents.getDownloadUrl(id);
      return response;
    } catch (err) {
      toast.error('Failed to get download URL');
      throw err;
    }
  };

  return {
    document,
    loading,
    error,
    refetch: fetchDocument,
    generateSummary,
    addTag,
    removeTag,
    getDownloadUrl,
  };
}

// Hook for search
export function useSearch() {
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const searchDocuments = async (query: string, filters?: { tags?: string[]; document_ids?: string[] }) => {
    try {
      setLoading(true);
      setError(null);
      const response = await api.search.documents(query, filters);
      setResults(response.results || []);
      return response;
    } catch (err) {
      setError(err as Error);
      toast.error('Search failed');
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const askQuestion = async (question: string, context?: { document_ids?: string[] }) => {
    try {
      setLoading(true);
      setError(null);
      const response = await api.search.ask(question, context);
      return response;
    } catch (err) {
      setError(err as Error);
      toast.error('Failed to get answer');
      throw err;
    } finally {
      setLoading(false);
    }
  };

  return {
    results,
    loading,
    error,
    searchDocuments,
    askQuestion,
  };
}

// Hook for chat
export function useChat() {
  const [messages, setMessages] = useState<any[]>([]);
  const [sessions, setSessions] = useState<any[]>([]);
  const [currentSession, setCurrentSession] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const sendMessage = async (message: string, sessionId?: string) => {
    try {
      setLoading(true);
      setError(null);
      const response = await api.chat.send(message, sessionId);
      
      // Add the message to the current conversation
      setMessages(prev => [...prev, 
        { role: 'user', content: message },
        { role: 'assistant', content: response.answer }
      ]);
      
      return response;
    } catch (err) {
      setError(err as Error);
      toast.error('Failed to send message');
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const loadSessions = async () => {
    try {
      const response = await api.chat.getSessions();
      setSessions(response);
    } catch (err) {
      console.error('Failed to load chat sessions:', err);
    }
  };

  const loadSession = async (sessionId: string) => {
    try {
      const response = await api.chat.getSession(sessionId);
      setCurrentSession(response);
      setMessages(response.messages || []);
    } catch (err) {
      toast.error('Failed to load chat session');
      throw err;
    }
  };

  return {
    messages,
    sessions,
    currentSession,
    loading,
    error,
    sendMessage,
    loadSessions,
    loadSession,
    setMessages,
  };
}