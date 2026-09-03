import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "../stores/auth";

import LoginView from "../views/LoginView.vue";
import RegisterView from "../views/RegisterView.vue";
import ForgotPasswordView from "../views/ForgotPasswordView.vue";
import ResetPasswordView from "../views/ResetPasswordView.vue";
import SuperAdminDashboard from "../views/SuperAdminDashboard.vue";
import BusinessOwnerDashboard from "../views/BusinessOwnerDashboard.vue";

const routes = [
  { path: "/", redirect: "/login" },
  { path: "/login", name: "login", component: LoginView },
  { path: "/register", name: "register", component: RegisterView },
  { path: "/forgot-password", name: "forgot-password", component: ForgotPasswordView },
  { path: "/reset-password", name: "reset-password", component: ResetPasswordView },
  {
    path: "/superadmin",
    name: "superadmin",
    component: SuperAdminDashboard,
    meta: { requiresRole: "super_admin" },
  },
  {
    path: "/dashboard",
    name: "dashboard",
    component: BusinessOwnerDashboard,
    meta: { requiresRole: "business_owner" },
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

// Route guard: bounces to /login if not authenticated, or to the correct
// dashboard if a role tries to visit the wrong one - mirrors the old
// admin.html's routeToDashboard()/showLogin() logic.
router.beforeEach((to) => {
  const auth = useAuthStore();

  if (to.meta.requiresRole && !auth.isAuthenticated) {
    return { name: "login" };
  }
  if (to.meta.requiresRole && to.meta.requiresRole !== auth.role) {
    return auth.role === "super_admin" ? { name: "superadmin" } : { name: "dashboard" };
  }
  if ((to.name === "login" || to.name === "register") && auth.isAuthenticated) {
    return auth.role === "super_admin" ? { name: "superadmin" } : { name: "dashboard" };
  }
});

export default router;