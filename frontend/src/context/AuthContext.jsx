import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import * as api from "../api";
import { setToken, setUnauthorizedHandler } from "../api/client";

const AuthContext = createContext(null);
const STORAGE_KEY = "interview-session";

// The token lives in this context. sessionStorage only keeps it across a page refresh in the
// same tab; it is gone when the tab closes.
function readStored() {
  try {
    return JSON.parse(sessionStorage.getItem(STORAGE_KEY)) ?? null;
  } catch {
    return null;
  }
}

function writeStored(value) {
  try {
    if (value) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // storage can be blocked; the context still works for this page load
  }
}

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(() => {
    const stored = readStored();
    setToken(stored?.token ?? null);
    return stored;
  });
  const [expired, setExpired] = useState(false);

  const signIn = useCallback(async (email, password) => {
    const token = await api.login(email, password);
    setToken(token);
    const next = { token, email };
    writeStored(next);
    setAuth(next);
    setExpired(false);
  }, []);

  const signUp = useCallback(
    async (email, password) => {
      await api.register(email, password);
      await signIn(email, password);
    },
    [signIn],
  );

  const signOut = useCallback(() => {
    setToken(null);
    writeStored(null);
    setAuth(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      signOut();
      setExpired(true);
    });
  }, [signOut]);

  const value = useMemo(
    () => ({ email: auth?.email ?? null, isSignedIn: Boolean(auth?.token), expired, signIn, signUp, signOut }),
    [auth, expired, signIn, signUp, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
