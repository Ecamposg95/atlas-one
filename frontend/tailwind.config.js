const EMBER = {
  50: '#FFF4EA', 100: '#FFE6D2', 200: '#FFD3A8', 300: '#FFBD85', 400: '#FFA14A',
  500: '#FF6A1F', 600: '#EA580C', 700: '#C2410C', 800: '#9A3412', 900: '#7A240A', 950: '#2A0E05',
}

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        dax: {
          bg:           'var(--dax-bg)',
          surface:      'var(--dax-surface)',
          card:         'var(--dax-card)',
          border:       'var(--dax-border)',
          'border-dim': 'var(--dax-border-dim)',
          accent:       'var(--dax-accent)',
          'accent-text': 'var(--dax-accent-text)',
          'accent-soft': 'var(--dax-accent-soft)',
          'on-accent':  'var(--dax-on-accent)',
          text:         'var(--dax-text)',
          muted:        'var(--dax-text-muted)',
          faint:        'var(--dax-text-faint)',
          elevated:     'var(--dax-elevated)',
          success:      'var(--dax-success)',
          warning:      'var(--dax-warning)',
          danger:       'var(--dax-danger)',
          'success-soft': 'var(--dax-success-soft)',
          'warning-soft': 'var(--dax-warning-soft)',
          'danger-soft':  'var(--dax-danger-soft)',
        },
        sb: {
          bg:     'var(--sb-bg)',
          text:   'var(--sb-text)',
          active: 'var(--sb-active-text)',
        },
        /* Atlas Horizon: las familias que el código viejo usa a mano se
           reasignan aquí para no editar cientos de clases. `slate` pasa a un
           neutro cálido (sin tinte azul) e `indigo`/`violet`/`purple` a la
           escala ámbar de la marca. Código nuevo: usa los tokens `dax-*`. */
        slate: {
          50: '#F6F3EF', 100: '#EFEAE4', 200: '#DDD6CE', 300: '#C9C1B8', 400: '#A8A29A',
          500: '#7A726B', 600: '#4A4541', 700: '#2B2724', 800: '#171514', 900: '#0E0D0C', 950: '#050505',
        },
        indigo: EMBER,
        violet: EMBER,
        purple: EMBER,
        atlas: {
          violet:  '#FFA14A',
          indigo:  '#FF6A1F',
          success: '#34d399',
          warning: '#fbbf24',
          danger:  '#fb7185',
        },
      },
      backdropBlur: {
        dax: '12px',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Arial', 'sans-serif'],
        serif: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'Menlo', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}
