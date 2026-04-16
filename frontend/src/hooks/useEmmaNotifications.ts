/**
 * useEmmaNotifications — Notification hook via Main API proxy.
 *
 * Fetches notifications through the Main API (port 8000) which proxies
 * to emma-agent-service. This avoids direct browser → microservice calls
 * that would fail outside the Docker network.
 *
 * HTTP endpoints:
 *   GET    /api/v1/emma/notifications
 *   PATCH  /api/v1/emma/notifications/:id/read
 *   POST   /api/v1/emma/notifications/read-all
 */
import { useEffect, useRef, useState } from "react";
import { API_CONFIG } from "../lib/config";

export interface EmmaNotification {
  id: string;
  user_id: string;
  notification_type: string;
  title: string;
  body: string;
  metadata?: Record<string, any>;
  action_url?: string;
  is_read: boolean;
  priority: string;
  created_at: string;
}

interface UseEmmaNotificationsOptions {
  /** Whether to auto-fetch notifications */
  enabled?: boolean;
}

const SSO_TOKEN_KEY = 'nexus_sso_tokens'

function getAccessToken(): string | null {
  if (typeof window === 'undefined') return null
  const stored = sessionStorage.getItem(SSO_TOKEN_KEY)
  if (!stored) return null
  try {
    const tokens = JSON.parse(stored)
    return tokens.access_token || null
  } catch {
    return null
  }
}

/** Build the API base URL matching emma.service.ts pattern */
function getApiBase(): string {
  const normalizedBaseUrl = (API_CONFIG.BASE_URL || '').replace(/\/$/, '')
  return `${normalizedBaseUrl}${API_CONFIG.API_V1}`
}

export function useEmmaNotifications(options: UseEmmaNotificationsOptions = {}) {
  const { enabled = true } = options;

  const [notifications, setNotifications] = useState<EmmaNotification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isConnected, setIsConnected] = useState(false);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch notifications via Main API proxy
  useEffect(() => {
    if (!enabled) return;

    const fetchNotifications = async () => {
      const token = getAccessToken();
      if (!token) return;

      try {
        const apiBase = getApiBase();
        const res = await fetch(`${apiBase}/emma/notifications?limit=50`, {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        });
        if (res.ok) {
          const data = await res.json();
          const items: EmmaNotification[] = data.notifications || [];
          setNotifications(items);
          setUnreadCount(items.filter((n) => !n.is_read).length);
          setIsConnected(true);
        }
      } catch (err) {
        console.warn("Failed to fetch notifications:", err);
        setIsConnected(false);
      }
    };

    // Initial fetch
    fetchNotifications();

    // Poll every 30s as lightweight alternative to WebSocket
    pollTimerRef.current = setInterval(fetchNotifications, 30_000);

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [enabled]);

  const markAsRead = async (notificationId: string) => {
    const token = getAccessToken();
    if (!token) return;

    try {
      const apiBase = getApiBase();
      const res = await fetch(`${apiBase}/emma/notifications/${notificationId}/read`, {
        method: "PATCH",
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      if (res.ok) {
        setNotifications((prev) =>
          prev.map((n) => (n.id === notificationId ? { ...n, is_read: true } : n))
        );
        setUnreadCount((prev) => Math.max(0, prev - 1));
      }
    } catch (err) {
      console.warn("Failed to mark notification as read:", err);
    }
  };

  const markAllAsRead = async () => {
    const token = getAccessToken();
    if (!token) return;

    try {
      const apiBase = getApiBase();
      const res = await fetch(`${apiBase}/emma/notifications/read-all`, {
        method: "POST",
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      if (res.ok) {
        setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
        setUnreadCount(0);
      }
    } catch (err) {
      console.warn("Failed to mark all as read:", err);
    }
  };

  return {
    notifications,
    unreadCount,
    isConnected,
    markAsRead,
    markAllAsRead,
  };
}
