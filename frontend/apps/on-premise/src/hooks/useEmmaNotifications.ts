/**
 * useEmmaNotifications — Real-time notification hook via polling.
 *
 * Polls the Emma notification API and provides:
 * - Periodic notification updates (every 30s)
 * - Unread count badge
 * - Mark as read functionality
 *
 * Uses relative URLs proxied through Next.js rewrites to avoid
 * mixed content issues (HTTPS page → HTTP emma-agent-service).
 */
import { useCallback, useEffect, useRef, useState } from "react";

export interface EmmaNotification {
  id: string;
  tenant_id: string;
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
  /** Polling interval in ms (default: 30000) */
  pollInterval?: number;
  /** Whether to auto-connect */
  enabled?: boolean;
}

const NOTIFICATIONS_BASE = "/emma/notifications";

export function useEmmaNotifications(options: UseEmmaNotificationsOptions = {}) {
  const {
    pollInterval = 30000,
    enabled = true,
  } = options;

  const [notifications, setNotifications] = useState<EmmaNotification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isConnected, setIsConnected] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchNotifications = useCallback(async () => {
    try {
      const res = await fetch(`${NOTIFICATIONS_BASE}?limit=50`);
      if (res.ok) {
        const data = await res.json();
        const items: EmmaNotification[] = data.notifications || [];
        setNotifications(items);
        setUnreadCount(items.filter((n) => !n.is_read).length);
        setIsConnected(true);
      } else {
        setIsConnected(false);
      }
    } catch {
      setIsConnected(false);
    }
  }, []);

  // Initial fetch + polling interval
  useEffect(() => {
    if (!enabled) return;

    fetchNotifications();
    intervalRef.current = setInterval(fetchNotifications, pollInterval);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [enabled, pollInterval, fetchNotifications]);

  const markAsRead = async (notificationId: string) => {
    try {
      const res = await fetch(`${NOTIFICATIONS_BASE}/${notificationId}/read`, {
        method: "PATCH",
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
    try {
      const res = await fetch(`${NOTIFICATIONS_BASE}/read-all`, {
        method: "POST",
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
