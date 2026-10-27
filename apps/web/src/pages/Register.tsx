import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { useAuth } from "../features/auth/AuthProvider";
import { GoogleSignInButton, GoogleSignInDivider } from "../features/auth/GoogleSignInButton";

const schema = z
  .object({
    full_name: z.string().min(1, "Full name is required"),
    email: z.string().email("Enter a valid email"),
    password: z.string().min(8, "Password must be at least 8 characters"),
    confirm_password: z.string(),
    terms_accepted: z.boolean().refine((v) => v === true, {
      message: "You must accept the terms and privacy policy",
    }),
  })
  .refine((v) => v.password === v.confirm_password, {
    path: ["confirm_password"],
    message: "Passwords do not match",
  });

type FormValues = z.infer<typeof schema>;

export function Register() {
  const { register: registerUser, user, error: authError, clearError } = useAuth();
  const navigate = useNavigate();
  const [showPassword, setShowPassword] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  useEffect(() => {
    if (user) navigate("/onboarding", { replace: true });
  }, [user, navigate]);

  const onSubmit = (values: FormValues) => {
    clearError();
    registerUser({
      full_name: values.full_name,
      email: values.email,
      password: values.password,
      terms_accepted: values.terms_accepted,
    });
  };

  return (
    <div className="auth-page">
      <h1>Create your LifeSmart account</h1>
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="auth-form">
        {authError && <p className="error-banner" role="alert">{authError}</p>}
        <label>
          Full name
          <input autoComplete="name" {...register("full_name")} />
          {errors.full_name && <span className="field-error">{errors.full_name.message}</span>}
        </label>
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
              autoComplete="new-password"
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
        <label>
          Confirm password
          <input
            type={showPassword ? "text" : "password"}
            autoComplete="new-password"
            {...register("confirm_password")}
          />
          {errors.confirm_password && (
            <span className="field-error">{errors.confirm_password.message}</span>
          )}
        </label>
        <label className="checkbox-row">
          <input type="checkbox" {...register("terms_accepted")} />
          <span>I accept the terms and acknowledge the privacy policy</span>
        </label>
        {errors.terms_accepted && (
          <span className="field-error">{errors.terms_accepted.message}</span>
        )}
        <button className="btn primary" type="submit" disabled={isSubmitting}>
          Create Account
        </button>
        <div className="auth-links">
          <Link to="/login">Sign In Instead</Link>
        </div>
      </form>
      <GoogleSignInDivider />
      <GoogleSignInButton text="signup_with" />
    </div>
  );
}
