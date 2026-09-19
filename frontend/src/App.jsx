import { lazy, Suspense } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { configError } from "./api/client";
import Alert from "./components/Alert";
import AppShell from "./components/AppShell";
import ProtectedRoute from "./components/ProtectedRoute";
import History from "./pages/History";
import Interview from "./pages/Interview";
import Landing from "./pages/Landing";
import Setup from "./pages/Setup";

// Pulls in the chart library, so it loads only when someone opens a result.
const Results = lazy(() => import("./pages/Results"));

function NotFound() {
  return (
    <div className="container page stack">
      <h1>Page not found</h1>
      <p className="text-lead">That address doesn't lead anywhere.</p>
      <div><Link to="/" className="btn btn-secondary">Go home</Link></div>
    </div>
  );
}

export default function App() {
  if (configError) {
    return (
      <div className="container page">
        <Alert title="The app isn't configured">{configError}</Alert>
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        <Route path="/setup" element={<Setup />} />
        <Route path="/interview/:id" element={<Interview />} />
        <Route
          path="/interviews/:id"
          element={
            <Suspense fallback={<div className="skeleton skeleton-title" aria-busy="true" />}>
              <Results />
            </Suspense>
          }
        />
        <Route path="/history" element={<History />} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
