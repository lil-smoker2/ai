/** Auth state: JWT + current user, with register/login/logout. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useContext,
  useEffect,
  type ReactNode,
} from "react";
import { api, ApiError, getToken, setToken } from "../../services/api";
import type { TokenResponse, User } from "../../types/api";

interface AuthContextValue {
  user: User | undefined;
  loading: boolean;
  error: string | null;
  clearError: () => void;
  login: (email: string, password: string) => void;
  loginWithGoogle: (credential: string) => void;
  register: (input: {
    full_name: string;
    email: string;
    password: string;
    terms_accepted: boolean;
  }) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  const onAuthed = (data: TokenResponse) => {
    setToken(data.access_token);
    queryClient.setQueryData(["me"], data.user);
  };

  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api<User>("/api/auth/me"),
    enabled: !!getToken(),
    retry: false,
  });

  // Local single-user mode: with no session yet, ask the app to sign us in
  // automatically (no login, password or terms). On a hosted deployment this
  // returns 404 and we simply fall through to the normal login screen.
  const bootstrap = useQuery({
    queryKey: ["authBootstrap"],
    queryFn: () => api<TokenResponse>("/api/auth/local", { method: "POST" }),
    enabled: !getToken(),
    retry: false,
    staleTime: Infinity,
  });

  useEffect(() => {
    if (bootstrap.data && !getToken()) {
      onAuthed(bootstrap.data);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bootstrap.data]);

  // An expired or revoked token must not leave the app in a fake session.
  if (me.error !== null && getToken()) {
    const status = me.error instanceof ApiError ? me.error.status : undefined;
    if (status === 401) {
      setToken(null);
      queryClient.clear();
    }
  }

  const login = useMutation({
    mutationFn: (input: { email: string; password: string }) =>
      api<TokenResponse>("/api/auth/login", { body: input }),
    onSuccess: onAuthed,
  });

  const registerUser = useMutation({
    mutationFn: (input: {
      full_name: string;
      email: string;
      password: string;
      terms_accepted: boolean;
    }) => api<TokenResponse>("/api/auth/register", { body: input }),
    onSuccess: onAuthed,
  });

  // Google Identity Services hands us an ID token; the backend verifies it
  // and returns our own JWT, so the rest of the app is unchanged.
  const googleLogin = useMutation({
    mutationFn: (credential: string) =>
      api<TokenResponse>("/api/auth/google", { body: { credential } }),
    onSuccess: onAuthed,
  });

  const logout = () => {
    setToken(null);
    queryClient.clear();
  };

  const mutationError = login.error ?? registerUser.error ?? googleLogin.error;
  const value: AuthContextValue = {
    user: me.data,
    loading:
      (bootstrap.isPending && !getToken()) || (me.isPending && !!getToken()),
    error: mutationError
      ? mutationError.message || "Authentication failed"
      : null,
    clearError: () => {
      login.reset();
      registerUser.reset();
      googleLogin.reset();
    },
    login: (email, password) => login.mutate({ email, password }),
    loginWithGoogle: (credential) => googleLogin.mutate(credential),
    register: (input) => registerUser.mutate(input),
    logout,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
