import { apiRequest } from './client';

/**
 * Request an OTP code for a specific purpose.
 * Purposes:
 *  - "create_switch"
 *  - "checkin:{switch_id}"
 *  - "cancel:{switch_id}"
 *
 * @param {string} purpose
 * @param {boolean} resend - Set to true to invalidate existing code and reissue
 */
export async function requestOtp(purpose, resend = false) {
  return apiRequest('/otp/request', {
    method: 'POST',
    body: JSON.stringify({
      purpose,
      resend,
    }),
  });
}
