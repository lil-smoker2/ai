import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { useAuth } from "../features/auth/AuthProvider";
import { GoogleSignInButton, GoogleSignInDivider } from "../features/auth/GoogleSignInButton";

const schema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(8, "Password must be at least 8 characters"),
});

type FormValues = z.infer<typeof schema>;

export function Login() {
  const { login, user, error: authError, clearError } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [showPassword, setShowPassword] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const from = (location.state as { from?: string } | null)?.from ?? "/app";

  useEffect(() => {
    if (user) navigate(from, { replace: true });
  }, [user, from, navigate]);

  const onSubmit = (values: FormValues) => {
    clearError();
    login(values.email, values.password);
  };

  return (
    <div className="auth-page">
      <h1>Sign in to LifeSmart</h1>
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="auth-form">
        {authError && <p className="error-banner" role="alert">{authError}</p>}
        <label>
          Email
          <input type="email" autoComplete="email" {...register("email")} />
          {errors.email && <span className="field-error">{errors.email.message}</span>}
        </label>
        <label>
          Password
          <div className="password-row">
            <input
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              {...register("password")}
            />
            <button
              type="button"
              className="icon-btn"
              aria-label={showPassword ? "Hide password" : "Show password"}
              onClick={() => setShowPassword((v) => !v)}
            >
              {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
          {errors.password && <span className="field-error">{errors.password.message}</span>}
        </label>
        <button className="btn primary" type="submit" disabled={isSubmitting}>
          Sign In
        </button>
        <div className="auth-links">
          <span>Forgot password? (recovery not yet configured)</span>
          <Link to="/register">Create Account</Link>
        </div>
      </form>
      <GoogleSignInDivider />
      <GoogleSignInButton text="signin_with" />
    </div>
  );
}
