import type { Config } from 'tailwindcss'

// Design direction: a field-lab dashboard — warm paper canvas, deep pine
// navigation, emerald diagnostics, amber warnings and red failures. Headings
// use a self-hosted serif; body copy uses Manrope.
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          50: '#f6f8f5',
          100: '#eaefea',
          200: '#d3dcd5',
          300: '#aebdb2',
          400: '#839889',
          500: '#647b6b',
          600: '#4e6254',
          700: '#3f5045',
          800: '#34423a',
          900: '#1d2a24',
          950: '#0a0f16',
        },
        accent: {
          50: '#ecfdf5',
          100: '#d1fae5',
          200: '#a7f3d0',
          300: '#6ee7b7',
          400: '#34d399',
          500: '#10b981',
          600: '#059669',
          700: '#047857',
          800: '#065f46',
          900: '#064e3b',
        },
        warn: {
          50: '#fffbeb',
          100: '#fef3c7',
          200: '#fde68a',
          300: '#fcd34d',
          400: '#fbbf24',
          500: '#f59e0b',
          600: '#d97706',
          700: '#b45309',
        },
      },
      fontFamily: {
        sans: [
          'Manrope Variable',
          'Manrope',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
        display: [
          'Newsreader Variable',
          'Newsreader',
          'Iowan Old Style',
          'Georgia',
          'Cambria',
          'Times New Roman',
          'serif',
        ],
      },
      boxShadow: {
        card: '0 1px 2px rgba(10, 24, 18, 0.04), 0 18px 36px -26px rgba(10, 24, 18, 0.35)',
        float: '0 24px 60px -28px rgba(6, 24, 18, 0.45)',
      },
    },
  },
  plugins: [],
} satisfies Config
