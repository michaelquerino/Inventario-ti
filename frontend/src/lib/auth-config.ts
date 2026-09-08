export function isSelfRegisterEnabled(): boolean {
  const raw = process.env.NEXT_PUBLIC_ENABLE_SELF_REGISTER?.trim().toLowerCase();
  return raw === "1" || raw === "true" || raw === "yes";
}

export function isSingleAdminMode(): boolean {
  const raw = process.env.NEXT_PUBLIC_SINGLE_ADMIN_MODE?.trim().toLowerCase();
  if (!raw) return true;
  return raw === "1" || raw === "true" || raw === "yes";
}
