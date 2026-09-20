/**
 * frontend/src/api/client.js
 * Centralized API client with JWT attachment, 401 auto-refresh, and 429 rate limit parsing.
 */

const BASE_URL = import.meta.env.VITE_API_URL || '';

let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

export async function apiRequest(endpoint, options = {}) {
  const url = `${BASE_URL}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  const accessToken = localStorage.getItem('access_token');
  if (accessToken && !headers.Authorization) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  const config = {
    ...options,
    headers,
  };

  try {
    const response = await fetch(url, config);

    // Rate Limit (429) Handling
    if (response.status === 429) {
      const retryAfter = response.headers.get('Retry-After') || '60';
      const data = await response.json().catch(() => ({}));
      const error = new Error(data.detail || 'Rate limit exceeded');
      error.status = 429;
      error.retryAfter = parseInt(retryAfter, 10);
      throw error;
    }

    // 401 Unauthorized -> Attempt token refresh once
    if (response.status === 401 && !options._retry && !endpoint.startsWith('/auth/login') && !endpoint.startsWith('/auth/dev-login') && !endpoint.startsWith('/auth/refresh')) {
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        if (isRefreshing) {
          return new Promise((resolve, reject) => {
            failedQueue.push({ resolve, reject });
          }).then((token) => {
            config.headers.Authorization = `Bearer ${token}`;
            return fetch(url, config).then((r) => r.json());
          });
        }

        options._retry = true;
        isRefreshing = true;

        try {
          const refreshRes = await fetch(`${BASE_URL}/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken }),
          });

          if (!refreshRes.ok) {
            throw new Error('Refresh token invalid');
          }

          const tokens = await refreshRes.json();
          localStorage.setItem('access_token', tokens.access_token);
          localStorage.setItem('refresh_token', tokens.refresh_token);

          processQueue(null, tokens.access_token);

          config.headers.Authorization = `Bearer ${tokens.access_token}`;
          const retryResponse = await fetch(url, config);
          return retryResponse.json();
        } catch (refreshErr) {
          processQueue(refreshErr, null);
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          window.dispatchEvent(new CustomEvent('auth:session_expired'));
          throw refreshErr;
        } finally {
          isRefreshing = false;
        }
      }
    }

    // Return empty for 204 No Content
    if (response.status === 204) {
      return null;
    }

    // Parse JSON
    const data = await response.json().catch(() => null);

    if (!response.ok) {
      const error = new Error(data?.detail || `Request failed with status ${response.status}`);
      error.status = response.status;
      error.data = data;
      throw error;
    }

    return data;
  } catch (err) {
    throw err;
  }
}
