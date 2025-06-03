import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios';

// API Configuration
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const API_VERSION = '/api/v1';

// Types
export interface ApiResponse<T = any> {
  data: T;
  message?: string;
  success: boolean;
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    page: number;
    per_page: number;
    total: number;
    pages: number;
  };
}

export interface Document {
  id: string;
  title: string;
  description: string;
  filename: string;
  file_type: string;
  file_size: number;
  indexed: string;
  created_at: string;
  updated_at: string;
  tags: string[];
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_superuser: boolean;
  clerk_user_id: string;
  tenant_id: string;
}

// Global token storage for client-side requests
let globalGetToken: (() => Promise<string | null>) | null = null;
let globalUserId: string | null = null;

// Function to set auth context for client-side usage
export const setAuthContext = (getToken: () => Promise<string | null>, userId: string | null) => {
  globalGetToken = getToken;
  globalUserId = userId;
};

// Create axios instance
const createApiClient = (): AxiosInstance => {
  console.log('🔧 Creating API client with:', {
    baseURL: `${API_BASE_URL}${API_VERSION}`,
    fullURL: `${API_BASE_URL}${API_VERSION}`,
    environment: process.env.NODE_ENV,
    isServer: typeof window === 'undefined'
  });
  
  const client = axios.create({
    baseURL: `${API_BASE_URL}${API_VERSION}`,
    timeout: 30000,
    headers: {
      'Content-Type': 'application/json',
    },
  });

  // Request interceptor to add auth token
  client.interceptors.request.use(
    async (config) => {
      console.log('📤 Making API request:', {
        method: config.method?.toUpperCase(),
        url: config.url,
        baseURL: config.baseURL,
        fullURL: `${config.baseURL}${config.url}`,
        headers: config.headers
      });
      
      try {
        // Try to get token from global context (client-side) or server-side auth
        let token: string | null = null;
        let userId: string | null = null;

        if (globalGetToken) {
          // Client-side: use global token function
          token = await globalGetToken();
          userId = globalUserId;
          console.log('🔑 Client-side auth:', { hasToken: !!token, userId });
        } else if (typeof window === 'undefined') {
          // Server-side: use auth() function
          try {
            const { auth } = await import('@clerk/nextjs');
            const { getToken, userId: serverUserId } = auth();
            token = await getToken();
            userId = serverUserId;
            console.log('🔑 Server-side auth:', { hasToken: !!token, userId });
          } catch (authError) {
            console.warn('⚠️ Server-side auth not available:', authError);
          }
        }
        
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }

        if (userId) {
          config.headers['X-User-ID'] = userId;
        }

        return config;
      } catch (error) {
        console.error('❌ Error in request interceptor:', error);
        return config;
      }
    },
    (error) => {
      return Promise.reject(error);
    }
  );

  // Response interceptor
  client.interceptors.response.use(
    (response: AxiosResponse) => {
      console.log('📥 API response received:', {
        status: response.status,
        statusText: response.statusText,
        url: response.config.url,
        data: response.data
      });
      return response;
    },
    (error) => {
      console.error('❌ API request failed:', {
        status: error.response?.status,
        statusText: error.response?.statusText,
        url: error.config?.url,
        message: error.message,
        code: error.code,
        data: error.response?.data
      });
      
      if (error.response?.status === 401) {
        console.warn('🚫 Unauthorized - redirecting to login');
        // Handle unauthorized
        if (typeof window !== 'undefined') {
          window.location.href = '/auth/login';
        }
      }
      return Promise.reject(error);
    }
  );

  return client;
};

// Create API client instance
export const apiClient = createApiClient();

// API Methods
export const api = {
  // Auth endpoints
  auth: {
    syncUser: async (userData: { clerk_user_id: string; email: string; full_name: string }) => {
      const response = await apiClient.post('/auth/sync-user', userData);
      return response.data;
    },
    getCurrentUser: async (): Promise<User> => {
      const response = await apiClient.get('/auth/me');
      return response.data;
    },
  },

  // Document endpoints
  documents: {
    list: async (params?: {
      page?: number;
      per_page?: number;
      tags?: string[];
      date_from?: string;
      date_to?: string;
    }): Promise<PaginatedResponse<Document>> => {
      const response = await apiClient.get('/documents', { params });
      return response.data;
    },
    
    get: async (id: string): Promise<Document> => {
      const response = await apiClient.get(`/documents/${id}`);
      return response.data;
    },
    
    upload: async (file: File, metadata: { title: string; description?: string; tags?: string[] }) => {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('title', metadata.title);
      if (metadata.description) {
        formData.append('description', metadata.description);
      }
      if (metadata.tags && metadata.tags.length > 0) {
        metadata.tags.forEach(tag => formData.append('tags', tag));
      }

      const response = await apiClient.post('/documents/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      return response.data;
    },
    
    delete: async (id: string) => {
      const response = await apiClient.delete(`/documents/${id}`);
      return response.data;
    },
    
    generateSummary: async (id: string) => {
      const response = await apiClient.post(`/documents/${id}/summary`);
      return response.data;
    },
    
    addTag: async (id: string, tagName: string) => {
      const response = await apiClient.post(`/documents/${id}/tags`, { tag_name: tagName });
      return response.data;
    },
    
    removeTag: async (id: string, tagName: string) => {
      const response = await apiClient.delete(`/documents/${id}/tags/${tagName}`);
      return response.data;
    },
    
    getDownloadUrl: async (id: string) => {
      const response = await apiClient.get(`/documents/${id}/download`);
      return response.data;
    },
  },

  // Search endpoints
  search: {
    documents: async (query: string, filters?: { tags?: string[]; document_ids?: string[] }) => {
      const response = await apiClient.post('/search/documents', {
        query,
        ...filters,
      });
      return response.data;
    },
    
    ask: async (question: string, context?: { document_ids?: string[] }) => {
      const response = await apiClient.post('/search/ask', {
        question,
        ...context,
      });
      return response.data;
    },
  },

  // Chat endpoints
  chat: {
    send: async (message: string, sessionId?: string) => {
      const response = await apiClient.post('/chat', {
        message,
        session_id: sessionId,
      });
      return response.data;
    },
    
    getSessions: async () => {
      const response = await apiClient.get('/chat/sessions');
      return response.data;
    },
    
    getSession: async (sessionId: string) => {
      const response = await apiClient.get(`/chat/sessions/${sessionId}`);
      return response.data;
    },
  },

  // Admin endpoints (for superusers)
  admin: {
    getUsers: async () => {
      const response = await apiClient.get('/admin/users');
      return response.data;
    },
    
    getTenants: async () => {
      const response = await apiClient.get('/admin/tenants');
      return response.data;
    },
    
    getSystemStats: async () => {
      const response = await apiClient.get('/admin/stats');
      return response.data;
    },
  },

  // Stripe endpoints
  stripe: {
    createCheckoutSession: async (data: { price_id: string; success_url?: string; cancel_url?: string }) => {
      const response = await apiClient.post('/stripe/create-checkout-session', data);
      return response.data;
    },

    getSubscription: async () => {
      const response = await apiClient.get('/stripe/subscription');
      return response.data;
    },

    createCustomerPortal: async (data: { return_url?: string }) => {
      const response = await apiClient.post('/stripe/create-customer-portal', data);
      return response.data;
    },

    syncSubscription: async () => {
      const response = await apiClient.post('/stripe/sync-subscription');
      return response.data;
    },

    cancelSubscription: async () => {
      const response = await apiClient.post('/stripe/cancel-subscription');
      return response.data;
    },
  },

  // Generic methods for custom endpoints
  get: async (endpoint: string) => {
    const response = await apiClient.get(endpoint);
    return response.data;
  },

  post: async (endpoint: string, data?: any) => {
    const response = await apiClient.post(endpoint, data);
    return response.data;
  },

  put: async (endpoint: string, data?: any) => {
    const response = await apiClient.put(endpoint, data);
    return response.data;
  },

  delete: async (endpoint: string) => {
    const response = await apiClient.delete(endpoint);
    return response.data;
  },
};

// Utility function for client-side API calls
export const clientApi = api;

// Utility function for server-side API calls (with custom token)
export const createServerApi = (token: string) => {
  const serverClient = axios.create({
    baseURL: `${API_BASE_URL}${API_VERSION}`,
    timeout: 30000,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
  });

  return {
    // Add server-specific methods here if needed
    getCurrentUser: async (): Promise<User> => {
      const response = await serverClient.get('/auth/me');
      return response.data;
    },
  };
};