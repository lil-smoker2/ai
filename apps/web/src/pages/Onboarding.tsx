/** Onboarding: essential setup only. Never asks for bank credentials or PINs. */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../services/api";
import { useAuth } from "../features/auth/AuthProvider";
import type { User } from "../types/api";

const CURRENCIES = ["KES", "UGX", "TZS", "RWF", "NGN", "USD", "EUR", "GBP"];
const COUNTRIES = ["Kenya", "Uganda", "Tanzania", "Rwanda", "Nigeria", "Other"];

export function Onboarding() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [currency, setCurrency] = useState(user?.currency ?? "KES");
  const [country, setCountry] = useState(user?.country ?? "Kenya");
  const [isStudent, setIsStudent] = useState<boolean | null>(user?.is_student ?? null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) navigate("/login", { replace: true });
  }, [user, navigate]);

  const finish = async (studentValue: boolean | null) => {
    setError(null);
    try {
      await api<User>("/api/auth/me", {
        method: "PATCH",
        body: { currency, country, is_student: studentValue, onboarded: true },
      });
      navigate("/app", { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save your setup");
    }
  };

  const steps = [
    <div key="0" className="onboard-step">
      <h2>Preferred currency</h2>
      <p>Money records will use this currency by default.</p>
      <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
        {CURRENCIES.map((c) => (
          <option key={c} value={c}>{c}</option>
        ))}
      </select>
    </div>,
    <div key="1" className="onboard-step">
      <h2>Country</h2>
      <p>Used for local context. More markets supported over time.</p>
      <select value={country} onChange={(e) => setCountry(e.target.value)}>
        {COUNTRIES.map((c) => (
          <option key={c} value={c}>{c}</option>
        ))}
      </select>
    </div>,
    <div key="2" className="onboard-step">
      <h2>Are you a student?</h2>
      <p>Optional. Student Life tools help with fees, hostel and food planning.</p>
      <div className="btn-row">
        <button className="btn" onClick={() => setIsStudent(true)}>Yes, I'm a student</button>
        <button className="btn" onClick={() => setIsStudent(false)}>No / skip</button>
      </div>
    </div>,
  ];

  return (
    <div className="auth-page onboard">
      <h1>Set up LifeSmart</h1>
      <p className="muted">Step {step + 1} of {steps.length} — optional steps can be skipped.</p>
      {error && <p className="error-banner" role="alert">{error}</p>}
      {steps[step]}
      <div className="btn-row spaced">
        {step > 0 && (
          <button className="btn ghost" onClick={() => setStep((s) => s - 1)}>Back</button>
        )}
        {step < steps.length - 1 ? (
          <button
            className="btn primary"
            onClick={() => (step === 2 ? undefined : setStep((s) => s + 1))}
          >
            Continue
          </button>
        ) : (
          <button className="btn primary" onClick={() => finish(isStudent)}>
            Finish Setup
          </button>
        )}
        <button className="btn ghost" onClick={() => finish(isStudent)}>
          Skip &amp; Finish
        </button>
      </div>
    </div>
  );
}
