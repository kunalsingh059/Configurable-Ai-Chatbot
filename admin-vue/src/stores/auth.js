import { defineStore } from "pinia";
import { api } from "../services/api";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    token: localStorage.getItem("admin_token") || null,
    role: localStorage.getItem("admin_role") || null,
    tenantId: localStorage.getItem("admin_tenant_id") || null,
    businessName: localStorage.getItem("admin_business_name") || null,
    // The tenant's widget API key - only returned for business_owner logins.
    // This is what fixes the gap the old admin.html had: the key came back
    // from /auth/login but was never stored or shown anywhere.
    apiKey: localStorage.getItem("admin_api_key") || null,
  }),

  getters: {
    isAuthenticated: (state) => !!state.token,
    isSuperAdmin: (state) => state.role === "super_admin",
    isBusinessOwner: (state) => state.role === "business_owner",
  },

  actions: {
    async login(username, password) {
      const data = await api.login({ username, password });
      this.token = data.access_token;
      this.role = data.role;
      this.tenantId = data.tenant_id;
      this.businessName = data.business_name;
      this.apiKey = data.api_key;

      localStorage.setItem("admin_token", this.token);
      localStorage.setItem("admin_role", this.role);
      if (this.tenantId) localStorage.setItem("admin_tenant_id", this.tenantId);
      if (this.businessName) localStorage.setItem("admin_business_name", this.businessName);
      if (this.apiKey) localStorage.setItem("admin_api_key", this.apiKey);

      return data;
    },

    setBusinessName(name) {
      this.businessName = name;
      localStorage.setItem("admin_business_name", name);
    },

    async register(tenantId, businessName, username, email, password) {
      return api.register({ tenant_id: tenantId, business_name: businessName, username, email, password });
    },

    logout() {
      this.token = null;
      this.role = null;
      this.tenantId = null;
      this.businessName = null;
      this.apiKey = null;
      localStorage.removeItem("admin_token");
      localStorage.removeItem("admin_role");
      localStorage.removeItem("admin_tenant_id");
      localStorage.removeItem("admin_business_name");
      localStorage.removeItem("admin_api_key");
    },
  },
});