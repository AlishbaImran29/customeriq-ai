/** Fills {name} placeholders in a message: fmt("Showing {a} of {b}", { a: 1, b: 5 }) -> "Showing 1 of 5". A name with no value is left as written. */
export function fmt(template: string, params: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) => (key in params ? String(params[key]) : match));
}
