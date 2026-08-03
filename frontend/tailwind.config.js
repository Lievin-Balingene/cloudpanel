/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Palette type panneau d'hébergement classique (inspirée WHM/cPanel, sans marque)
        cp: {
          orange: "#ff6c2c",
          "orange-dark": "#e55a1b",
          "orange-soft": "#fff1ea",
          navy: "#1a2b3c",
          "navy-soft": "#243447",
          sidebar: "#2b3d4f",
          header: "#1f2d3d",
          border: "#d5dde5",
          canvas: "#eef2f6",
          panel: "#ffffff",
          text: "#2c3e50",
          muted: "#6b7c8f",
          link: "#1a5fb4",
          success: "#2e7d32",
          danger: "#c62828",
        },
        ink: {
          50: "#f4f7fb",
          100: "#e8eef6",
          200: "#cddbec",
          300: "#a3bdd9",
          400: "#7399c1",
          500: "#527aa8",
          600: "#3f618c",
          700: "#344e72",
          800: "#2e435f",
          900: "#2a3a50",
          950: "#1a2433",
        },
        accent: {
          DEFAULT: "#ff6c2c",
          soft: "#ff8f5c",
          deep: "#e55a1b",
        },
        surface: {
          light: "#eef2f6",
          dark: "#121a24",
        },
      },
      fontFamily: {
        display: ['"Segoe UI"', "Tahoma", "Geneva", "Verdana", "sans-serif"],
        sans: ['"Segoe UI"', "Tahoma", "Geneva", "Verdana", "sans-serif"],
        mono: ['Consolas', '"Courier New"', "monospace"],
      },
      boxShadow: {
        panel: "0 1px 3px rgba(26, 43, 60, 0.12)",
        tool: "0 1px 2px rgba(0,0,0,0.08)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.25s ease-out both",
      },
    },
  },
  plugins: [],
};
