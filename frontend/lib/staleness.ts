/**
 * A data point can be VERIFIED and still stale (the last successful scan
 * was 2 hours ago) or DEMO and technically "fresh" (just generated) - the
 * two concepts are independent, so this is a separate check from
 * DataStatusBadge, not a replacement for it.
 */
const STALE_THRESHOLD_MINUTES = 15;

export function isStale(timestamp: string, thresholdMinutes: number = STALE_THRESHOLD_MINUTES): boolean {
  const ageMinutes = (Date.now() - new Date(timestamp).getTime()) / 60000;
  return ageMinutes > thresholdMinutes;
}

export function ageLabel(timestamp: string): string {
  const ageMinutes = Math.round((Date.now() - new Date(timestamp).getTime()) / 60000);
  if (ageMinutes < 1) return "just now";
  if (ageMinutes < 60) return `${ageMinutes}m ago`;
  const hours = Math.round(ageMinutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}
