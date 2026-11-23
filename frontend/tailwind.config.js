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
        cream: '#FAF8F4',
        ink: { 950: '#050B18', 900: '#0A1428', 800: '#101D38', 700: '#1A2A4C' },
        zra: { navy: '#1B3F8B', sky: '#1BA3E0', gold: '#C9A24A' },
        clear: { 300: '#5EEAD4', 400: '#2DD4BF', 500: '#14B8A6', 600: '#0D9488' },
      },
      boxShadow: { glow: '0 10px 30px -10px rgba(27,63,139,.35)', soft: '0 20px 50px -20px rgba(15,23,42,.25)' },
      keyframes: {
        scan: { '0%': { transform: 'translateY(-10%)' }, '100%': { transform: 'translateY(110%)' } },
        float: { '0%,100%': { transform: 'translateY(0)' }, '50%': { transform: 'translateY(-8px)' } },
        fadeup: { '0%': { opacity: 0, transform: 'translateY(12px)' }, '100%': { opacity: 1, transform: 'none' } },
        drift: { '0%,100%': { transform: 'translate(0,0) scale(1)' }, '50%': { transform: 'translate(30px,-25px) scale(1.08)' } },
        popin: { '0%': { opacity: 0, transform: 'scale(.85) translateY(10px)' }, '100%': { opacity: 1, transform: 'none' } },
        wiggle: { '0%,100%': { transform: 'rotate(-3deg)' }, '50%': { transform: 'rotate(3deg)' } },
      },
      animation: { scan: 'scan 2.8s ease-in-out infinite alternate', float: 'float 6s ease-in-out infinite',
        fadeup: 'fadeup .6s ease-out both', drift: 'drift 14s ease-in-out infinite',
        popin: 'popin .7s cubic-bezier(.2,.8,.2,1.2) both', wiggle: 'wiggle 4s ease-in-out infinite' },
    },
  },
  plugins: [],
}
