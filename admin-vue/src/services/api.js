const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

/**
 * All authenticated admin calls go through here. Mirrors the old
 * admin.html's authFetch(): attaches the JWT, and throws on 401/403 so
 * callers (and the router guard) can react to an expired/invalid session
 * or a deactivated account.
 */
async function request(path, { method = "GET", body, token, isForm = false } = {}) {
  const headers = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (body && !isForm) headers["Content-Type"] = "application/json";

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });

  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    throw new ApiError(data.detail || "Request failed", res.status);
  }
  return data;
}

export const api = {
  register: (payload) => request("/auth/register", { method: "POST", body: payload }),
  login: (payload) => request("/auth/login", { method: "POST", body: payload }),
  forgotPassword: (email) => request("/auth/forgot-password", { method: "POST", body: { email } }),
  resetPassword: (token, newPassword) =>
    request("/auth/reset-password", { method: "POST", body: { token, new_password: newPassword } }),

  // Super admin
  listOwners: (token) => request("/superadmin/business-owners", { token }),
  activateOwner: (token, id) =>
    request(`/superadmin/business-owners/${id}/activate`, { method: "POST", token }),
  deactivateOwner: (token, id) =>
    request(`/superadmin/business-owners/${id}/deactivate`, { method: "POST", token }),

  // Business owner - tools
  listTools: (token) => request("/admin/tools", { token }),
  createTool: (token, tool) => request("/admin/tools", { method: "POST", body: tool, token }),
  updateTool: (token, id, tool) =>
    request(`/admin/tools/${id}`, { method: "PUT", body: tool, token }),
  deleteTool: (token, id) => request(`/admin/tools/${id}`, { method: "DELETE", token }),

  // Business owner - settings
  getBusinessName: (token) => request("/admin/business-name", { token }),
  updateBusinessName: (token, businessName) =>
    request("/admin/business-name", { method: "PATCH", body: { business_name: businessName }, token }),

  // Business owner - documents
  listDocuments: (token) => request("/admin/documents", { token }),
  uploadDocument: (token, file) => {
    const formData = new FormData();
    formData.append("file", file);
    return request("/admin/documents", { method: "POST", body: formData, token, isForm: true });
  },
  deleteDocument: (token, id) => request(`/admin/documents/${id}`, { method: "DELETE", token }),
};

export { ApiError, API_BASE };