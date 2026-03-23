/**
 * Format a number of cents as a USD currency string.
 * amount_usd in the DB is always stored in cents.
 * Pass `fromCents: false` only if the value is already in dollars.
 */
export function formatMoney(
  amount: number | null | undefined,
  options?: { fromCents?: boolean }
): string {
  if (amount == null) return '$0';
  const fromCents = options?.fromCents ?? true;
  const dollars = fromCents ? amount / 100 : amount;
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(dollars);
}

/**
 * Format a date string into a human-readable format.
 */
export function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return 'N/A';
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

/**
 * Get initials from a name (up to 2 characters).
 */
export function getInitials(name: string): string {
  return name
    .split(' ')
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase();
}

/**
 * Get the display color class for a party affiliation.
 */
export function getPartyColor(party: string | undefined): string {
  if (!party) return 'text-zinc-400';
  const lower = party.toLowerCase();
  if (lower.includes('democrat')) return 'text-money-democrat';
  if (lower.includes('republican')) return 'text-money-republican';
  if (lower.includes('independent')) return 'text-money-independent';
  return 'text-zinc-400';
}

/**
 * Get the background color class for a party affiliation.
 */
export function getPartyBgColor(party: string | undefined): string {
  if (!party) return 'bg-zinc-600';
  const lower = party.toLowerCase();
  if (lower.includes('democrat')) return 'bg-money-democrat';
  if (lower.includes('republican')) return 'bg-money-republican';
  if (lower.includes('independent')) return 'bg-money-independent';
  return 'bg-zinc-600';
}

/**
 * Get a slug-friendly entity type for URL paths.
 */
export function entityTypePath(entityType: string): string {
  return entityType.toLowerCase();
}

/**
 * Truncate text to a given length.
 */
export function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength).trimEnd() + '...';
}

/**
 * Capitalize the first letter of a string.
 */
export function capitalize(text: string): string {
  if (!text) return '';
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * Format a relationship type string for display.
 */
export function formatRelationshipType(type: string): string {
  return type
    .split('_')
    .map((word) => capitalize(word))
    .join(' ');
}
