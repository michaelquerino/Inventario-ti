export type ThresholdSettings = {
  cpuWarn: number;
  cpuCritical: number;
  ramWarn: number;
  ramCritical: number;
  diskWarn: number;
  diskCritical: number;
  staleHours: number;
};

export type ModulePermissions = {
  dashboard: boolean;
  assets: boolean;
  monitoring: boolean;
  reports: boolean;
  tickets: boolean;
  settings: boolean;
};

export type PermissionsSettings = {
  admin: ModulePermissions;
  manager: ModulePermissions;
  viewer: ModulePermissions;
};

export type UiSettings = {
  thresholds: ThresholdSettings;
  permissions: PermissionsSettings;
};

export const defaultUiSettings: UiSettings = {
  thresholds: {
    cpuWarn: 50,
    cpuCritical: 80,
    ramWarn: 50,
    ramCritical: 80,
    diskWarn: 50,
    diskCritical: 80,
    staleHours: 24,
  },
  permissions: {
    admin: { dashboard: true, assets: true, monitoring: true, reports: true, tickets: true, settings: true },
    manager: { dashboard: true, assets: true, monitoring: true, reports: true, tickets: true, settings: true },
    viewer: { dashboard: true, assets: true, monitoring: true, reports: true, tickets: true, settings: false },
  },
};

const STORAGE_KEY = "inventario_ui_settings_v1";

export function loadUiSettings(): UiSettings {
  if (typeof window === "undefined") return defaultUiSettings;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultUiSettings;
    const parsed = JSON.parse(raw) as UiSettings;
    return {
      thresholds: { ...defaultUiSettings.thresholds, ...(parsed.thresholds || {}) },
      permissions: {
        admin: { ...defaultUiSettings.permissions.admin, ...(parsed.permissions?.admin || {}) },
        manager: { ...defaultUiSettings.permissions.manager, ...(parsed.permissions?.manager || {}) },
        viewer: { ...defaultUiSettings.permissions.viewer, ...(parsed.permissions?.viewer || {}) },
      },
    };
  } catch {
    return defaultUiSettings;
  }
}

export function saveUiSettings(settings: UiSettings): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}
