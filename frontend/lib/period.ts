// Period lengths (in days) offered for the Overview figures. Kept apart from the picker component
// because the server page needs these values and cannot read exports of a "use client" file.
export const PERIOD_OPTIONS = [30, 90, 180, 365] as const;
export const DEFAULT_PERIOD = 90;
