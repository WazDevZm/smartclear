/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['"Plus Jakarta Sans"', 'Inter', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        ink: { 950: '#050B18', 900: '#0A1428', 800: '#101D38', 700: '#1A2A4C' },
        zra: { navy: '#1B3F8B', sky: '#1BA3E0', gold: '#C9A24A' },
        clear: { 300: '#5EEAD4', 400: '#2DD4BF', 500: '#14B8A6', 600: '#0D9488' },
      },
      boxShadow: { glow: '0 0 0 1px rgba(45,212,191,.25), 0 10px 40px -10px rgba(45,212,191,.35)' },
      keyframes: {
        scan: { '0%': { transform: 'translateY(-10%)' }, '100%': { transform: 'translateY(110%)' } },
        float: { '0%,100%': { transform: 'translateY(0)' }, '50%': { transform: 'translateY(-8px)' } },
        fadeup: { '0%': { opacity: 0, transform: 'translateY(12px)' }, '100%': { opacity: 1, transform: 'none' } },
      },
      animation: { scan: 'scan 2.8s ease-in-out infinite alternate', float: 'float 6s ease-in-out infinite',
        fadeup: 'fadeup .6s ease-out both' },
    },
  },
  plugins: [],
}
