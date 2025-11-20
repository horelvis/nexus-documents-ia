import { apiClient } from './api-client';

export const fetcher = async <T>(url: string): Promise<T> => {
  const response = await apiClient.get<T>(url);
  
  if (response.error) {
    // Throw an object that SWR can use for error handling
    const error = new Error(response.error);
    (error as any).status = response.status;
    throw error;
  }
  
  return response.data as T;
};
