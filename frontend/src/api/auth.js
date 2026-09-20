import { apiRequest } from './client';

export async function getMe() {
  return apiRequest('/auth/me');
}

export async function devLogin(email = 'iamkabshah@gmail.com') {
  return apiRequest('/auth/dev-login', {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
}

export async function logout(refreshToken) {
  if (!refreshToken) return null;
  return apiRequest('/auth/logout', {
    method: 'POST',
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
}

export function getGoogleLoginUrl() {
  const base = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  return `${base}/auth/login`;
}
