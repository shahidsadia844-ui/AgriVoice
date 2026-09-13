/**
 * AgriPak – shared API config
 * Backend: http://localhost:8000
 * Change API_BASE if backend runs on another host/port.
 */
const API_BASE = 'http://localhost:8000';

function getToken() {
  return localStorage.getItem('agri_token') || '';
}

function setAuth(token, user) {
  localStorage.setItem('agri_token', token);
  if (user) {
    localStorage.setItem('agri_user', JSON.stringify(user));
    if (user.name) localStorage.setItem('agri_user_name', user.name);
    if (user.selected_crop) localStorage.setItem('selectedCrop', user.selected_crop);
  }
}

function clearAuth() {
  localStorage.removeItem('agri_token');
  localStorage.removeItem('agri_user');
  localStorage.removeItem('agri_user_name');
}

function getUser() {
  try {
    return JSON.parse(localStorage.getItem('agri_user') || 'null');
  } catch {
    return null;
  }
}

function authHeaders() {
  const t = getToken();
  const h = { 'Content-Type': 'application/json' };
  if (t) h['Authorization'] = 'Bearer ' + t;
  return h;
}

async function apiPost(path, body) {
  const res = await fetch(API_BASE + path, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.message || ('HTTP ' + res.status));
  return data;
}

async function apiGet(path) {
  const res = await fetch(API_BASE + path, {
    method: 'GET',
    headers: authHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.message || ('HTTP ' + res.status));
  return data;
}

async function apiUpload(path, formData) {
  const t = getToken();
  const headers = {};
  if (t) headers['Authorization'] = 'Bearer ' + t;
  const res = await fetch(API_BASE + path, {
    method: 'POST',
    headers,
    body: formData,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.message || ('HTTP ' + res.status));
  return data;
}
