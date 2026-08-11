import type { RouteRecordRaw } from 'vue-router'
import { useAuthStore } from './stores/auth'

export const productionRoutes: RouteRecordRaw[] = [
  { path: '', name: 'chat', component: () => import('./views/ChatView.vue'), meta: { capabilityId: 'chat' } },
  { path: 'insight', name: 'insight', component: () => import('./views/InsightView.vue'), meta: { capabilityId: 'insight' } },
  { path: 'schedule', name: 'schedule', component: () => import('./views/ScheduleView.vue'), meta: { capabilityId: 'schedule' } },
  { path: 'media', name: 'media', component: () => import('./views/MediaView.vue'), meta: { capabilityId: 'media' } },
  { path: 'health', name: 'health', component: () => import('./views/HealthView.vue'), meta: { capabilityId: 'health' } },
  { path: 'dashboard', name: 'dashboard', component: () => import('./views/DashboardView.vue'), meta: { capabilityId: 'dashboard' } },
  { path: 'settings/agents', name: 'agents', component: () => import('./views/AgentsView.vue'), meta: { capabilityId: 'agents' } },
  { path: 'settings/models', name: 'models', component: () => import('./views/ModelsView.vue'), meta: { capabilityId: 'models' } },
  { path: 'settings/tools', name: 'tools', component: () => import('./views/ToolsView.vue'), meta: { capabilityId: 'tools' } },
  { path: 'settings/mcp', name: 'mcp', component: () => import('./views/McpView.vue'), meta: { capabilityId: 'mcp' } },
  { path: 'settings/plugins', name: 'plugins', component: () => import('./views/PluginsView.vue'), meta: { capabilityId: 'plugins' } },
  { path: 'settings/mail', name: 'mail', component: () => import('./views/MailView.vue'), meta: { capabilityId: 'mail' } },
  { path: 'settings/system', name: 'settings', component: () => import('./views/SettingsView.vue'), meta: { capabilityId: 'settings' } },
  { path: 'workflows', name: 'workflows', component: () => import('./views/WorkflowView.vue'), meta: { capabilityId: 'workflows' } },
  { path: 'disclaimer', name: 'disclaimer', component: () => import('./views/DisclaimerView.vue'), meta: { capabilityId: 'disclaimer' } },
  { path: 'sponsor', name: 'sponsor', component: () => import('./views/SponsorView.vue'), meta: { capabilityId: 'sponsor' } },
]

export const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('./views/LoginView.vue'),
  },
  {
    path: '/setup',
    name: 'setup',
    component: () => import('./views/SetupWizardView.vue'),
  },
  {
    path: '/setup/profile',
    name: 'setup-profile',
    component: () => import('./views/UserProfileSetupView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/',
    component: () => import('./components/layout/AppLayout.vue'),
    meta: { requiresAuth: true },
    children: productionRoutes,
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('./views/NotFoundView.vue'),
  },
]
