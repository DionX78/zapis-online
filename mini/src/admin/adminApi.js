const API_BASE = '/max_booking/api/admin';

function getInitData() {
  if (window.WebApp && window.WebApp.initData) {
    return window.WebApp.initData;
  }
  return '';
}

function buildUrl(path, orgId) {
  if (!orgId) return `${API_BASE}${path}`;
  const sep = path.includes('?') ? '&' : '?';
  return `${API_BASE}${path}${sep}org_id=${encodeURIComponent(orgId)}`;
}

async function request(path, orgId, options = {}) {
  const res = await fetch(buildUrl(path, orgId), {
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      'X-Max-Init-Data': getInitData(),
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    let detail = null;
    try {
      const j = JSON.parse(text);
      if (j && typeof j.detail === 'string') detail = j.detail;
    } catch {}
    throw new Error(detail || `HTTP ${res.status}: ${text}`);
  }
  return res.json();
}

export const adminApi = {
  getMe: (orgId) => request('/me', orgId),
  getOrgs: () => request('/orgs', null),
  getTimezones: () => request('/timezones'),
  updateOrg: (orgId, name) =>
    request('/org', orgId, { method: 'PUT', body: JSON.stringify({ name }) }),

  getDashboardToday: (orgId) => request('/dashboard/today', orgId),
  exportAnalytics: (orgId, params = {}) => {
    const qs = new URLSearchParams();
    if (params.date_from) qs.append('date_from', params.date_from);
    if (params.date_to) qs.append('date_to', params.date_to);
    if (params.format) qs.append('format', params.format);
    if (params.branch_id) qs.append('branch_id', params.branch_id);
    if (params.doctor_id) qs.append('doctor_id', params.doctor_id);
    return request(`/analytics/export?${qs.toString()}`, orgId);
  },
  getAnalyticsSummary: (orgId, params = {}) => {
    const qs = new URLSearchParams();
    if (params.date_from) qs.append('date_from', params.date_from);
    if (params.date_to) qs.append('date_to', params.date_to);
    if (params.branch_id) qs.append('branch_id', params.branch_id);
    if (params.doctor_id) qs.append('doctor_id', params.doctor_id);
    return request(`/analytics/summary?${qs.toString()}`, orgId);
  },
  getAnalyticsDoctor: (orgId, doctorId, params = {}) => {
    const qs = new URLSearchParams();
    if (params.date_from) qs.append('date_from', params.date_from);
    if (params.date_to) qs.append('date_to', params.date_to);
    return request(`/analytics/doctor/${doctorId}?${qs.toString()}`, orgId);
  },
  getAuditLog: (orgId, params = {}) => {
    const qs = new URLSearchParams();
    if (params.limit) qs.append('limit', params.limit);
    if (params.offset) qs.append('offset', params.offset);
    if (params.action) qs.append('action', params.action);
    if (params.date_from) qs.append('date_from', params.date_from);
    if (params.date_to) qs.append('date_to', params.date_to);
    const qsStr = qs.toString();
    return request(`/audit_log${qsStr ? '?' + qsStr : ''}`, orgId);
  },

  getRequests: (orgId, params = {}) => {
    const qs = new URLSearchParams();
    if (params.status) qs.append('status', params.status);
    if (params.date_from) qs.append('date_from', params.date_from);
    if (params.date_to) qs.append('date_to', params.date_to);
    if (params.auto_done) qs.append('auto_done', params.auto_done);
    if (params.page) qs.append('page', params.page);
    if (params.per_page) qs.append('per_page', params.per_page);
    const qsStr = qs.toString();
    return request(`/requests${qsStr ? '?' + qsStr : ''}`, orgId);
  },
  confirmRequest: (orgId, id) =>
    request(`/request/${id}/confirm`, orgId, { method: 'POST' }),
  rejectRequest: (orgId, id) =>
    request(`/request/${id}/reject`, orgId, { method: 'POST' }),
  markDone: (orgId, id, payload = null) =>
    request(`/request/${id}/done`, orgId, {
      method: 'POST',
      body: JSON.stringify(payload || {}),
    }),
  markNoShow: (orgId, id) =>
    request(`/request/${id}/no_show`, orgId, { method: 'POST' }),
  updatePayment: (orgId, id, payload) =>
    request(`/request/${id}/payment`, orgId, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  moveRequest: (orgId, requestId, newSlotId) =>
    request(`/request/${requestId}/move`, orgId, {
      method: 'POST',
      body: JSON.stringify({ new_slot_id: newSlotId }),
    }),
  editRequest: (orgId, requestId, payload) =>
    request(`/request/${requestId}/edit`, orgId, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  getRequestSlotOptions: (orgId, requestId) =>
    request(`/request/${requestId}/slot_options`, orgId),

  createRequest: (orgId, payload) =>
    request('/request/create', orgId, { method: 'POST', body: JSON.stringify(payload) }),
  searchClients: (orgId, q) =>
    request(`/clients/search?q=${encodeURIComponent(q || '')}`, orgId),
  setMarketingOptOut: (orgId, userId, optOut) =>
    request(`/client/${encodeURIComponent(userId)}/marketing`, orgId, {
      method: 'PUT',
      body: JSON.stringify({ opt_out: optOut }),
    }),
  getClientCard: (orgId, userId) =>
    request(`/client/${encodeURIComponent(userId)}/card`, orgId),
  updateClientCard: (orgId, userId, payload) =>
    request(`/client/${encodeURIComponent(userId)}/card`, orgId, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  resetClientNoShow: (orgId, userId) =>
    request(`/client/${encodeURIComponent(userId)}/reset_no_show`, orgId, { method: 'POST' }),
  exportClient: (orgId, userId) =>
    request(`/client/${encodeURIComponent(userId)}/export-json`, orgId),
  exportClientFile: (orgId, userId, format, target = 'admin') =>
    request(`/client/${encodeURIComponent(userId)}/export?format=${encodeURIComponent(format)}&target=${encodeURIComponent(target)}`, orgId),
  deleteClient: (orgId, userId) =>
    request(`/client/${encodeURIComponent(userId)}`, orgId, { method: 'DELETE' }),
  blockClient: (orgId, userId, reason = '') =>
    request(`/client/${encodeURIComponent(userId)}/block`, orgId, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  unblockClient: (orgId, userId) =>
    request(`/client/${encodeURIComponent(userId)}/block`, orgId, { method: 'DELETE' }),
  getBlockedUsers: (orgId) => request('/blocked_users', orgId),

  // Лист ожидания
  getWaitlist: (orgId, params = {}) => {
    const qs = new URLSearchParams();
    if (params.status) qs.append('status', params.status);
    if (params.service_id) qs.append('service_id', params.service_id);
    if (params.doctor_id) qs.append('doctor_id', params.doctor_id);
    if (params.branch_id) qs.append('branch_id', params.branch_id);
    if (params.limit) qs.append('limit', params.limit);
    if (params.offset) qs.append('offset', params.offset);
    const qsStr = qs.toString();
    return request(`/waitlist${qsStr ? '?' + qsStr : ''}`, orgId);
  },
  createWaitlist: (orgId, payload) =>
    request('/waitlist', orgId, { method: 'POST', body: JSON.stringify(payload) }),
  updateWaitlist: (orgId, wid, payload) =>
    request(`/waitlist/${wid}`, orgId, { method: 'PUT', body: JSON.stringify(payload) }),
  cancelWaitlist: (orgId, wid) =>
    request(`/waitlist/${wid}`, orgId, { method: 'DELETE' }),
  notifyWaitlist: (orgId, wid) =>
    request(`/waitlist/${wid}/notify`, orgId, { method: 'POST' }),
  fulfillWaitlist: (orgId, wid, requestId = null) =>
    request(`/waitlist/${wid}/fulfill`, orgId, {
      method: 'POST',
      body: JSON.stringify({ request_id: requestId }),
    }),
  sendClientMessage: (orgId, userId, text) =>
    request(`/client/${encodeURIComponent(userId)}/message`, orgId, {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),
  uploadClientPhoto: (orgId, userId, file) => {
    const fd = new FormData();
    fd.append('file', file);
    const url = buildUrl(`/client/${encodeURIComponent(userId)}/photo`, orgId);
    return fetch(url, {
      method: 'POST',
      cache: 'no-store',
      headers: { 'X-Max-Init-Data': getInitData() },
      body: fd,
    }).then(async (res) => {
      if (!res.ok) {
        const t = await res.text();
        let detail = null;
        try { const j = JSON.parse(t); if (j && typeof j.detail === 'string') detail = j.detail; } catch {}
        throw new Error(detail || `HTTP ${res.status}: ${t}`);
      }
      return res.json();
    });
  },
  deleteClientPhoto: (orgId, userId) =>
    request(`/client/${encodeURIComponent(userId)}/photo`, orgId, { method: 'DELETE' }),
  sendClientMessageWithFile: (orgId, userId, text, file) => {
    const fd = new FormData();
    fd.append('text', text || '');
    if (file) fd.append('file', file);
    const url = buildUrl(`/client/${encodeURIComponent(userId)}/message-with-file`, orgId);
    return fetch(url, {
      method: 'POST',
      cache: 'no-store',
      headers: { 'X-Max-Init-Data': getInitData() },
      body: fd,
    }).then(async (res) => {
      if (!res.ok) {
        const t = await res.text();
        let detail = null;
        try { const j = JSON.parse(t); if (j && typeof j.detail === 'string') detail = j.detail; } catch {}
        throw new Error(detail || `HTTP ${res.status}: ${t}`);
      }
      return res.json();
    });
  },

  getSettings: (orgId) => request('/settings', orgId),
  saveSettings: (orgId, settings) =>
    request('/settings', orgId, {
      method: 'POST',
      body: JSON.stringify({ settings }),
    }),

  getReviews: (orgId, params = {}) => {
    const qs = new URLSearchParams();
    if (params.filter) qs.append('filter', params.filter);
    if (params.doctor_id) qs.append('doctor_id', params.doctor_id);
    if (params.rating) qs.append('rating', params.rating);
    if (params.limit) qs.append('limit', params.limit);
    if (params.offset) qs.append('offset', params.offset);
    const qsStr = qs.toString();
    return request(`/reviews${qsStr ? '?' + qsStr : ''}`, orgId);
  },
  getClientReviews: (orgId, userId) =>
    request(`/client/${encodeURIComponent(userId)}/reviews`, orgId),

  getSlots: (orgId, dateFrom, dateTo, branchId, doctorId) => {
    let qs = `date_from=${dateFrom}&date_to=${dateTo}`;
    if (branchId) qs += `&branch_id=${branchId}`;
    if (doctorId) qs += `&doctor_id=${doctorId}`;
    return request(`/slots?${qs}`, orgId);
  },
  getAvailableSlots: (orgId, serviceId, dateFrom, dateTo, branchId, doctorId, slotsCount) => {
    const params = new URLSearchParams();
    if (serviceId) params.append('service_id', serviceId);
    params.append('date_from', dateFrom);
    params.append('date_to', dateTo);
    if (branchId) params.append('branch_id', branchId);
    if (doctorId) params.append('doctor_id', doctorId);
    if (slotsCount) params.append('slots_count', slotsCount);
    return request(`/slots/available?${params.toString()}`, orgId);
  },
  createSlot: (orgId, payload) =>
    request('/slots', orgId, { method: 'POST', body: JSON.stringify(payload) }),
  deleteSlot: (orgId, slotId) =>
    request(`/slots/${slotId}`, orgId, { method: 'DELETE' }),
  generateSlots: (orgId, payload) =>
    request('/slots/generate', orgId, { method: 'POST', body: JSON.stringify(payload) }),

  getBranches: (orgId) => request('/branches', orgId),
  createBranch: (orgId, payload) =>
    request('/branches', orgId, { method: 'POST', body: JSON.stringify(payload) }),
  updateBranch: (orgId, id, payload) =>
    request(`/branches/${id}`, orgId, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteBranch: (orgId, id) =>
    request(`/branches/${id}`, orgId, { method: 'DELETE' }),
  setPrimaryBranch: (orgId, id) =>
    request(`/branches/${id}/primary`, orgId, { method: 'PUT' }),

  getDoctors: (branchId) => request(`/doctors?branch_id=${branchId}`, null),
  getDoctorsByOrg: (orgId) => request('/doctors', orgId),
  createDoctor: (orgId, payload) =>
    request('/doctors', orgId, { method: 'POST', body: JSON.stringify(payload) }),
  updateDoctor: (orgId, id, payload) =>
    request(`/doctors/${id}`, orgId, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteDoctor: (orgId, id) =>
    request(`/doctors/${id}`, orgId, { method: 'DELETE' }),
  setDoctorScheduleStop: (orgId, doctorId, stopDate) =>
    request(`/doctors/${doctorId}/schedule_stop`, orgId, {
      method: 'PUT',
      body: JSON.stringify({ stop_date: stopDate || null }),
    }),
  getDoctorSchedule: (orgId, doctorId) =>
    request(`/doctors/${doctorId}/schedule`, orgId),
  setDoctorSchedule: (orgId, doctorId, shifts) =>
    request(`/doctors/${doctorId}/schedule`, orgId, {
      method: 'PUT',
      body: JSON.stringify({ shifts }),
    }),
  getDoctorScheduleExceptions: (orgId, doctorId) =>
    request(`/doctors/${doctorId}/schedule_exceptions`, orgId),
  createDoctorScheduleException: (orgId, doctorId, payload) =>
    request(`/doctors/${doctorId}/schedule_exceptions`, orgId, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deleteDoctorScheduleException: (orgId, doctorId, excId) =>
    request(`/doctors/${doctorId}/schedule_exceptions/${excId}`, orgId, {
      method: 'DELETE',
    }),
  regenerateDoctorSlots: (orgId, doctorId, horizonDays) =>
    request(`/doctors/${doctorId}/schedule/regenerate`, orgId, {
      method: 'POST',
      body: JSON.stringify(horizonDays ? { horizon_days: horizonDays } : {}),
    }),
  regenerateAllSlots: (orgId, horizonDays) =>
    request('/schedule/regenerate_all', orgId, {
      method: 'POST',
      body: JSON.stringify(horizonDays ? { horizon_days: horizonDays } : {}),
    }),
  uploadDoctorPhoto: (orgId, doctorId, file) => {
    const fd = new FormData();
    fd.append('file', file);
    const url = buildUrl(`/doctors/${doctorId}/photo`, orgId);
    return fetch(url, {
      method: 'POST',
      cache: 'no-store',
      headers: { 'X-Max-Init-Data': getInitData() },
      body: fd,
    }).then(async (res) => {
      if (!res.ok) {
        const t = await res.text();
        let detail = null;
        try { const j = JSON.parse(t); if (j && typeof j.detail === 'string') detail = j.detail; } catch {}
        throw new Error(detail || `HTTP ${res.status}: ${t}`);
      }
      return res.json();
    });
  },
  deleteDoctorPhoto: (orgId, doctorId) =>
    request(`/doctors/${doctorId}/photo`, orgId, { method: 'DELETE' }),
  getDoctorServices: (orgId, doctorId) =>
    request(`/doctors/${doctorId}/services`, orgId),
  setDoctorServices: (orgId, doctorId, serviceIds) =>
    request(`/doctors/${doctorId}/services`, orgId, {
      method: 'PUT',
      body: JSON.stringify({ service_ids: serviceIds }),
    }),
  getDoctorReviews: (orgId, doctorId) =>
    request(`/doctors/${doctorId}/reviews`, orgId),

  getServices: (orgId) => request('/services', orgId),
  createService: (orgId, payload) =>
    request('/services', orgId, { method: 'POST', body: JSON.stringify(payload) }),
  updateService: (orgId, id, payload) =>
    request(`/services/${encodeURIComponent(id)}`, orgId, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteService: (orgId, id) =>
    request(`/services/${encodeURIComponent(id)}`, orgId, { method: 'DELETE' }),

  getServiceCategories: (orgId) => request('/service_categories', orgId),
  createServiceCategory: (orgId, payload) =>
    request('/service_categories', orgId, { method: 'POST', body: JSON.stringify(payload) }),
  updateServiceCategory: (orgId, id, payload) =>
    request(`/service_categories/${id}`, orgId, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteServiceCategory: (orgId, id) =>
    request(`/service_categories/${id}`, orgId, { method: 'DELETE' }),

  getBroadcasts: (orgId) => request('/broadcasts', orgId),
  previewBroadcast: (orgId, segment) =>
    request('/broadcasts/preview', orgId, {
      method: 'POST',
      body: JSON.stringify({ segment }),
    }),
  createBroadcast: (orgId, payload) =>
    request('/broadcasts', orgId, { method: 'POST', body: JSON.stringify(payload) }),
  updateBroadcast: (orgId, bid, payload) =>
    request(`/broadcasts/${bid}`, orgId, { method: 'PUT', body: JSON.stringify(payload) }),
  startBroadcast: (orgId, bid) =>
    request(`/broadcasts/${bid}/start`, orgId, { method: 'POST' }),
  scheduleBroadcast: (orgId, bid, scheduledAt) =>
    request(`/broadcasts/${bid}/schedule`, orgId, {
      method: 'POST',
      body: JSON.stringify({ scheduled_at: scheduledAt }),
    }),
  unscheduleBroadcast: (orgId, bid) =>
    request(`/broadcasts/${bid}/unschedule`, orgId, { method: 'POST' }),
  cancelBroadcast: (orgId, bid) =>
    request(`/broadcasts/${bid}/cancel`, orgId, { method: 'POST' }),
  deleteBroadcast: (orgId, bid) =>
    request(`/broadcasts/${bid}`, orgId, { method: 'DELETE' }),
  duplicateBroadcast: (orgId, bid) =>
    request(`/broadcasts/${bid}/duplicate`, orgId, { method: 'POST' }),
  getBroadcastDetails: (orgId, bid) => request(`/broadcasts/${bid}`, orgId),
  getBroadcastSends: (orgId, bid) => request(`/broadcasts/${bid}/sends`, orgId),

  getAutoBroadcasts: (orgId) => request('/auto_broadcasts', orgId),
  createAutoBroadcast: (orgId, payload) =>
    request('/auto_broadcasts', orgId, { method: 'POST', body: JSON.stringify(payload) }),
  updateAutoBroadcast: (orgId, id, payload) =>
    request(`/auto_broadcasts/${id}`, orgId, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteAutoBroadcast: (orgId, id) =>
    request(`/auto_broadcasts/${id}`, orgId, { method: 'DELETE' }),
  toggleAutoBroadcast: (orgId, id) =>
    request(`/auto_broadcasts/${id}/toggle`, orgId, { method: 'POST' }),
  testAutoBroadcast: (orgId, id) =>
    request(`/auto_broadcasts/${id}/test`, orgId, { method: 'POST' }),

  uploadImage: (orgId, file) => {
    const fd = new FormData();
    fd.append('file', file);
    const url = buildUrl('/upload', orgId);
    return fetch(url, {
      method: 'POST',
      cache: 'no-store',
      headers: { 'X-Max-Init-Data': getInitData() },
      body: fd,
    }).then(async (res) => {
      if (!res.ok) {
        const text = await res.text();
        let detail = null;
        try {
          const j = JSON.parse(text);
          if (j && typeof j.detail === 'string') detail = j.detail;
        } catch {}
        throw new Error(detail || `HTTP ${res.status}: ${text}`);
      }
      return res.json();
    });
  },

  // Каналы / Боты
  getBots: (orgId) => request('/bots/ui/list', orgId),
  getBot: (orgId, botId) => request(`/bots/${botId}`, orgId),
  addBot: (orgId, payload) =>
    request('/bots/ui/add', orgId, { method: 'POST', body: JSON.stringify(payload) }),
  updateBot: (orgId, botId, payload) =>
    request(`/bots/ui/${botId}`, orgId, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteBot: (orgId, botId) =>
    request(`/bots/ui/${botId}`, orgId, { method: 'DELETE' }),
  checkBotToken: (orgId, payload) =>
    request('/bots/ui/check_token', orgId, { method: 'POST', body: JSON.stringify(payload) }),
  registerCallback: (orgId, botId) =>
    request(`/bots/ui/${botId}/register_callback`, orgId, { method: 'POST' }),
};
