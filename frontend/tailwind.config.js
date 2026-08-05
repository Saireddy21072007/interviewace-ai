/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#080b14',
          900: '#0d1220',
          800: '#141b2d',
          700: '#1e273d',
          600: '#2b3550',
        },
        brand: {
          400: '#7c8cff',
          500: '#5b6cff',
          600: '#4453e6',
        },
      },
      fontFamily: {
        sans: ['Inter', 'Segoe UI', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Consolas', 'monospace'],
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulseRing: {
          '0%, 100%': { transform: 'scale(1)', opacity: '0.5' },
          '50%': { transform: 'scale(1.25)', opacity: '0' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.35s ease-out',
        'pulse-ring': 'pulseRing 1.6s ease-out infinite',
      },
    },
  },
  plugins: [],
}
