const formatter = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

export function formatCents(cents: number): string {
  return formatter.format(cents / 100)
}

/** Percentage discount in whole cents, rounded half up. */
export function percentOf(cents: number, percent: number): number {
  return Math.round((cents * percent) / 100)
}
