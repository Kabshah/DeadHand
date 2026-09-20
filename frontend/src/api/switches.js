import { apiRequest } from './client';

export async function getSwitches(search = '') {
  const query = search && search.trim() ? `?q=${encodeURIComponent(search.trim())}` : '';
  return apiRequest(`/switches${query}`);
}

export async function getSwitch(id) {
  return apiRequest(`/switches/${id}`);
}

export async function createSwitch({ recipient_email, interval_hours, secret_message, otp_code }) {
  return apiRequest('/switches', {
    method: 'POST',
    body: JSON.stringify({
      recipient_email,
      interval_hours: parseFloat(interval_hours),
      secret_message,
      otp_code: otp_code.trim(),
    }),
  });
}

export async function checkinSwitch(id, otp_code) {
  return apiRequest(`/switches/${id}/checkin`, {
    method: 'POST',
    body: JSON.stringify({
      otp_code: otp_code.trim(),
    }),
  });
}

export async function cancelSwitch(id, otp_code) {
  return apiRequest(`/switches/${id}/cancel`, {
    method: 'POST',
    body: JSON.stringify({
      otp_code: otp_code.trim(),
    }),
  });
}

export async function getHealth() {
  return apiRequest('/health');
}
