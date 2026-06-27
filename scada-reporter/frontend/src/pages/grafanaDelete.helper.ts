// Only admins may delete dashboards (destructive; backend also enforces admin).
export function canDeleteDashboard(role: string | undefined): boolean {
  return role === 'admin'
}
