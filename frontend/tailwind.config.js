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
        atlas: {
          violet:  '#8b5cf6',
          indigo:  '#6366f1',
          success: '#34d399',
          warning: '#fbbf24',
          danger:  '#fb7185',
        },
      },
      backdropBlur: {
        dax: '12px',
      },
      fontFamily: {
        sans: ['IBM Plex Sans', 'system-ui', 'sans-serif'],
        serif: ['IBM Plex Serif', 'Georgia', 'serif'],
        mono: ['IBM Plex Mono', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
}
