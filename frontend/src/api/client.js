import axios from "axios";

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

export const configError = baseUrl
  ? null
  : "VITE_API_BASE_URL is not set. Copy frontend/.env.example to frontend/.env and point it at the backend.";

export const api = axios.create({ baseURL: baseUrl, timeout: 120000 });

let token = null;
let onUnauthorized = () => {};

export const getBaseUrl = () => baseUrl;
export const getToken = () => token;
export const setToken = (value) => {
  token = value;
};
export const setUnauthorizedHandler = (handler) => {
  onUnauthorized = handler;
};

api.interceptors.request.use((config) => {
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && token) onUnauthorized();
    return Promise.reject(error);
  },
);

/** An error with the same shape whether it came from axios or from fetch. */
export class ApiFailure extends Error {
  constructor({ status, code, message }) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

const FALLBACK = "Something went wrong. Try again.";

export function describeError(error) {
  if (error instanceof ApiFailure) return { status: error.status, code: error.code, message: error.message };

  const response = error?.response;
  if (response) {
    const detail = response.data?.detail;
    if (detail && typeof detail === "object" && !Array.isArray(detail)) {
      return { status: response.status, code: detail.error ?? "error", message: detail.message ?? FALLBACK };
    }
    if (Array.isArray(detail)) {
      const fields = detail.map((d) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("; ");
      return { status: 422, code: "validation", message: `Check the form. ${fields}` };
    }
    return { status: response.status, code: "error", message: FALLBACK };
  }
  if (error?.code === "ECONNABORTED") {
    return { status: 0, code: "timeout", message: "The request took too long. Try again." };
  }
  return {
    status: 0,
    code: "network",
    message: "Can't reach the server. Check your connection and that the backend is running.",
  };
}
