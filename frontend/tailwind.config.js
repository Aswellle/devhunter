/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Semantic tokens (DESIGN.md) — these utility names were referenced
        // all over the UI (bg-surface, text-muted, border-subtle, ...) but
        // never defined, so Tailwind silently emitted nothing: modal panels
        // had no background (transparent, page content bled through) and
        // borders/text colors were missing.
        primary: {
          DEFAULT: '#1A1A1A',   // semantic "primary text" (--text-primary)
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
        },
        secondary: '#6B7280',   // --text-secondary
        muted: '#9CA3AF',       // --text-muted
        subtle: '#E5E7EB',      // --border-subtle
        default: '#D1D5DB',     // --border-default
        strong: '#9CA3AF',      // --border-strong
        surface: {
          DEFAULT: '#FFFFFF',   // --surface
          hover: '#F5F5F5',     // --surface-hover
          active: '#EFF6FF',    // --surface-active
          elevated: '#FFFFFF',  // --surface-elevated
        },
        hover: '#F5F5F5',       // bg-hover alias of --surface-hover
        accent: {
          DEFAULT: '#2563EB',   // --accent
          hover: '#1D4ED8',     // --accent-hover
          light: '#EFF6FF',     // --accent-light
        },
        danger: {
          DEFAULT: '#DC2626',   // --danger
          light: '#FEF2F2',     // --danger-light
        },
        success: {
          DEFAULT: '#16A34A',   // --success
          light: '#F0FDF4',     // --success-light
        },
        warning: {
          DEFAULT: '#D97706',   // --warning
          light: '#FFFBEB',     // --warning-light
        },
      },
    },
  },
  plugins: [],
}
