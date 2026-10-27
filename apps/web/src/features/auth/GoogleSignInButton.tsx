/** "Sign in with Google" button backed by Google Identity Services.
 *
 * Renders nothing when VITE_GOOGLE_CLIENT_ID is not configured, so email/password
 * auth always works. Google supplies the branded button; we only wire the ID
 * token it returns to our backend via AuthProvider.loginWithGoogle.
 */
import { useEffect, useRef } from "react";
import { useAuth } from "./AuthProvider";

interface CredentialResponse {
  credential: string;
  select_by?: string;
}

interface GoogleId {
  initialize: (options: {
    client_id: string;
    callback: (response: CredentialResponse) => void;
    auto_select?: boolean;
  }) => void;
  renderButton: (
    element: HTMLElement,
    options: {
      theme?: "outline" | "filled_blue" | "filled_black";
      size?: "large" | "medium" | "small";
      text?: "signin_with" | "signup_with" | "continue_with";
      shape?: "rectangular" | "pill" | "circle" | "square";
      width?: number;
    },
  ) => void;
}

declare global {
  interface Window {
    google?: { accounts?: { id?: GoogleId } };
  }
}

const GSI_SRC = "https://accounts.google.com/gsi/client";

/** Load the GSI script once and resolve when the API is available. */
function loadGsi(): Promise<GoogleId | null> {
  if (window.google?.accounts?.id) {
    return Promise.resolve(window.google.accounts.id);
  }
  return new Promise((resolve) => {
    const existing = document.querySelector<HTMLScriptElement>(
      `script[src="${GSI_SRC}"]`,
    );
    const script =
      existing ??
      Object.assign(document.createElement("script"), {
        src: GSI_SRC,
        async: true,
      });
    const finish = () => resolve(window.google?.accounts?.id ?? null);
    script.addEventListener("load", finish);
    script.addEventListener("error", () => resolve(null));
    if (!existing) document.head.appendChild(script);
  });
}

export function GoogleSignInButton({ text = "signin_with" }: { text?: "signin_with" | "signup_with" }) {
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
  const containerRef = useRef<HTMLDivElement>(null);
  const { loginWithGoogle } = useAuth();

  useEffect(() => {
    if (!clientId) return;
    let cancelled = false;
    loadGsi().then((id) => {
      if (cancelled || !id || !containerRef.current) return;
      id.initialize({
        client_id: clientId,
        // credential is a Google-issued ID token (JWT); verified server-side.
        callback: (response) => {
          if (response.credential) loginWithGoogle(response.credential);
        },
      });
      id.renderButton(containerRef.current, {
        theme: "outline",
        size: "large",
        text,
        shape: "pill",
      });
    });
    return () => {
      cancelled = true;
    };
  }, [clientId, text, loginWithGoogle]);

  if (!clientId) return null;
  return <div className="google-btn-row" ref={containerRef} />;
}

export function GoogleSignInDivider() {
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
  if (!clientId) return null;
  return (
    <div className="auth-divider" role="separator">
      <span>or</span>
    </div>
  );
}
