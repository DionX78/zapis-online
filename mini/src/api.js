const API_BASE = '/max_booking/api/mini';

function getInitData() {
  if (window.WebApp && window.WebApp.initData) {
    return window.WebApp.initData;
  }
  return '';
}

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      'X-Max-Init-Data': getInitData(),
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  getMe: () => request('/me'),
  getServices: () => request('/services'),
  getDoctors: () => request('/doctors'),
  getDates: (serviceId) => request(`/dates?service_id=${encodeURIComponent(serviceId)}`),
  getSlots: (serviceId, date) =>
    request(`/slots?service_id=${encodeURIComponent(serviceId)}&date=${encodeURIComponent(date)}`),
  book: (payload) =>
    request('/book', { method: 'POST', body: JSON.stringify(payload) }),
  getRepeat: (requestId) => request(`/history/${requestId}`),
  setFavoriteDoctor: (doctorId) =>
    request('/favorite_doctor', {
      method: 'PUT',
      body: JSON.stringify({ doctor_id: doctorId }),
    }),
  getSlot: (slotId) => request(`/slot/${slotId}`),
  createWaitlist: (payload) =>
    request('/waitlist', { method: 'POST', body: JSON.stringify(payload) }),
  getWaitlist: () => request('/waitlist'),
  cancelWaitlist: (wid) =>
    request(`/waitlist/${wid}`, { method: 'DELETE' }),
};