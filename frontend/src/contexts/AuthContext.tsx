import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { apiRequest, buildWebSocketUrl } from '../services/api';
import { UserProfile } from '../types';

export interface RealtimeEvent {
  event: string;
  data: unknown;
  receivedAt: number;
}

interface AuthContextValue {
  user: UserProfile | null;
  token: string | null;
  loading: boolean;
  wsConnected: boolean;
  lastEvent: RealtimeEvent | null;
  login: (email: string, password: string) => Promise<UserProfile>;
  register: (payload: Record<string, unknown>) => Promise<UserProfile>;
  refreshProfile: () => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('dalalink_token'));
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const [lastEvent, setLastEvent] = useState<RealtimeEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const refreshProfile = useCallback(async () => {
    const t = localStorage.getItem('dalalink_token');
    if (!t) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await apiRequest<UserProfile>('/auth/me', {}, t);
      setUser(me);
    } catch {
      localStorage.removeItem('dalalink_token');
      setToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshProfile();
  }, [refreshProfile]);

  useEffect(() => {
    if (!token) {
      wsRef.current?.close();
      wsRef.current = null;
      setWsConnected(false);
      return;
    }

    let cancelled = false;
    let reconnectTimer: number | undefined;

    const connect = () => {
      if (cancelled) return;
      try {
        const ws = new WebSocket(buildWebSocketUrl(token));
        wsRef.current = ws;

        ws.onopen = () => {
          if (!cancelled) setWsConnected(true);
        };
        ws.onmessage = (ev) => {
          try {
            const parsed = JSON.parse(ev.data);
            setLastEvent({ event: parsed.event, data: parsed.data, receivedAt: Date.now() });
          } catch {
            // ignore malformed ws frame
          }
        };
        ws.onclose = () => {
          if (!cancelled) {
            setWsConnected(false);
            reconnectTimer = window.setTimeout(connect, 3000);
          }
        };
      } catch {
        setWsConnected(false);
      }
    };

    connect();
    return () => {
      cancelled = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, [token]);

  const login = async (email: string, password: string): Promise<UserProfile> => {
    const res = await apiRequest<{ access_token: string; user: UserProfile }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    localStorage.setItem('dalalink_token', res.access_token);
    setToken(res.access_token);
    setUser(res.user);
    return res.user;
  };

  const register = async (payload: Record<string, unknown>): Promise<UserProfile> => {
    const res = await apiRequest<{ access_token: string; user: UserProfile }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    localStorage.setItem('dalalink_token', res.access_token);
    setToken(res.access_token);
    setUser(res.user);
    return res.user;
  };

  const logout = () => {
    localStorage.removeItem('dalalink_token');
    setToken(null);
    setUser(null);
    wsRef.current?.close();
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        loading,
        wsConnected,
        lastEvent,
        login,
        register,
        refreshProfile,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
