import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Logo } from "./Icons";

export default function AppShell() {
  const { email, signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <div className="shell">
      <header className="shell-header">
        <div className="container shell-bar">
          <NavLink to="/setup" className="brand">
            <Logo />
            <span>Interview Assistant</span>
          </NavLink>
          <nav className="shell-nav" aria-label="Main">
            <NavLink to="/setup">New interview</NavLink>
            <NavLink to="/history">History</NavLink>
          </nav>
          <div className="row shell-user">
            <span className="text-small shell-email">{email}</span>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => {
                signOut();
                navigate("/");
              }}
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      {/* Keyed by path so every route change replays the entrance animation. */}
      <main key={location.pathname} className="container page page-enter">
        <Outlet />
      </main>
    </div>
  );
}
