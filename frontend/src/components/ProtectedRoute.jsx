import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({ children }) {
  const { isSignedIn } = useAuth();
  const location = useLocation();
  return isSignedIn ? children : <Navigate to="/" replace state={{ from: location.pathname }} />;
}
