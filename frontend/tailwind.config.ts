import type { Config } from 'tailwindcss'

// Design direction (PRD §6): academic/professional, light canvas,
// deep navy navigation, teal success accent, amber warnings, red failures.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          50: '#f6f7f9',
          100: '#eceef2',
          200: '#d5dae2',
          300: '#b0b9c6',
          400: '#8593a6',
          500: '#66758a',
          600: '#515e71',
          700: '#424d5c',
          800: '#39424e',
          900: '#1f2937',
          950: '#121826',
        },
        accent: {
          50: '#eefbf6',
          100: '#d5f5e8',
          200: '#aeead4',
          300: '#79d8b9',
          400: '#43be99',
          500: '#1fa380',
          600: '#128368',
          700: '#106955',
          800: '#105445',
          900: '#0e453a',
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
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
      },
      boxShadow: {
        card: '0 1px 2px rgba(18, 24, 38, 0.06), 0 8px 24px -12px rgba(18, 24, 38, 0.18)',
      },
    },
  },
  plugins: [],
} satisfies Config
