import type { Config } from 'tailwindcss';
// "Meridian" skin — warm off-white canvas, dark navy rail, terracotta accent,
// Manrope + IBM Plex Mono. Palette ported from the CFC Meridian design (oklch → hex
// so Tailwind /alpha opacity modifiers keep working). Operator labels stay neutralized.
export default {
  content: ['./src/**/*.{html,svelte,ts}'],
  theme: {
    extend: {
      colors: {
        bg: '#FBFAF7', surface: '#FFFFFF', ink: '#2A2F3A', muted: '#737A88',
        accent: '#BE6B41', sage: '#2E8B68', warn: '#9A7420', line: '#E9E7E1',
        // dark navy rail (brand device — constant regardless of content)
        rail: '#232834', rail2: '#2E3442', railline: '#363D4C',
        railink: '#E5E7EC', railink2: '#8B93A3'
      },
      fontFamily: {
        display: ['Manrope', 'ui-sans-serif', 'system-ui', '-apple-system', 'sans-serif'],
        sans: ['Manrope', 'ui-sans-serif', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SF Mono', 'Menlo', 'monospace']
      },
      borderRadius: { lg: '9px', xl: '14px', '2xl': '14px' },
      boxShadow: { soft: '0 1px 2px rgba(30,35,45,.04), 0 4px 16px rgba(30,35,45,.05)' }
    }
  },
  plugins: []
} satisfies Config;
