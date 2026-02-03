/**
 * useEmmaNotifications — Real-time notification hook via WebSocket.
 *
 * Connects to the Emma notification WebSocket and provides:
 * - Real-time notification updates
 * - Unread count badge
 * - Mark as read functionality
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
  /** Emma Agent Service base URL */
  baseUrl?: string;
  /** Whether to auto-connect */
  enabled?: boolean;
}

export function useEmmaNotifications(options: UseEmmaNotificationsOptions = {}) {
  const {
    baseUrl = process.env.NEXT_PUBLIC_EMMA_SERVICE_URL || "http://localhost:8009",
    enabled = true,
  } = options;

  const [notifications, setNotifications] = useState<EmmaNotification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  // Fetch initial notifications
  useEffect(() => {
    if (!enabled) return;

    const fetchNotifications = async () => {
      try {
        const res = await fetch(`${baseUrl}/emma/notifications?limit=50`);
        if (res.ok) {
          const data = await res.json();
          setNotifications(data.notifications || []);
          setUnreadCount(
            (data.notifications || []).filter((n: EmmaNotification) => !n.is_read).length
          );
        }
      } catch (err) {
        console.warn("Failed to fetch notifications:", err);
      }
    };

    fetchNotifications();
  }, [baseUrl, enabled]);

  // WebSocket connection for real-time updates
  useEffect(() => {
    if (!enabled) return;

    const wsUrl = baseUrl.replace(/^http/, "ws") + "/emma/ws/notifications";
    let ws: WebSocket;

    const connect = () => {
      try {
        ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          setIsConnected(true);
        };

        ws.onmessage = (event) => {
          try {
            const notification: EmmaNotification = JSON.parse(event.data);
            setNotifications((prev) => [notification, ...prev].slice(0, 100));
            if (!notification.is_read) {
              setUnreadCount((prev) => prev + 1);
            }
          } catch (err) {
            console.warn("Failed to parse notification:", err);
          }
        };

        ws.onclose = () => {
          setIsConnected(false);
          // Auto-reconnect after 5 seconds
          setTimeout(connect, 5000);
        };

        ws.onerror = () => {
          ws.close();
        };
      } catch (err) {
        console.warn("WebSocket connection failed:", err);
      }
    };

    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [baseUrl, enabled]);

  const markAsRead = async (notificationId: string) => {
    try {
      const res = await fetch(`${baseUrl}/emma/notifications/${notificationId}/read`, {
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
      const res = await fetch(`${baseUrl}/emma/notifications/read-all`, {
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
