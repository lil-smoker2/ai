import { Link } from "react-router-dom";
import { Leaf } from "lucide-react";
import { AssetImage } from "../features/assets/AssetImage";

export function Welcome() {
  return (
    <div className="welcome">
      <header className="welcome-header">
        <span className="brand">
          <Leaf size={20} aria-hidden /> LifeSmart
        </span>
        <nav aria-label="Welcome navigation">
          <Link to="/login" className="btn ghost">Sign In</Link>
        </nav>
      </header>
      <main>
        <h1>Plan. Manage. Grow.</h1>
        <p className="tagline">
          One place for what you own, what you need, what you can afford and
          what to do next - inventory, shopping, money, savings, goals, tasks
          and student life.
        </p>
        {/* Discovered from the dynamic asset library; no hardcoded filename. */}
        <div className="welcome-illustration" aria-hidden>
          <AssetImage category="illustrations" size={160} />
        </div>
        <div className="welcome-actions">
          <Link to="/register" className="btn primary">Get Started</Link>
          <Link to="/login" className="btn">Sign In</Link>
        </div>
        <section className="explain">
          <h2>How LifeSmart works</h2>
          <ul>
            <li>Record what you own and what you want - shortages are calculated for you.</li>
            <li>Track cash, M-PESA and bank balances with precise, honest numbers.</li>
            <li>Turn goals into costed plans with explainable priorities.</li>
            <li>Place pictures in asset folders - the scanner discovers them automatically.</li>
          </ul>
        </section>
      </main>
    </div>
  );
}
