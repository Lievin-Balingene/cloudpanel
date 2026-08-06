/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        cp: {
          // Accent cPanel/WHM classique
          orange: "#ff6c2c",
          "orange-dark": "#e55a1c",
          "orange-soft": "#fff3ec",
          navy: "#152536",
          "navy-soft": "#1e3348",
          sidebar: "#2a4a6b",
          header: "#161d26",
          border: "#c5d0dc",
          canvas: "#d8e0ea",
          panel: "#ffffff",
          text: "#2c3e50",
          muted: "#6b7c8f",
          link: "#1a5fb4",
          "link-dark": "#154a8f",
          "link-soft": "#e8f0fa",
          success: "#2e7d32",
          danger: "#c62828",
        },
        whm: {
          accent: "#ff6c2c",
          "accent-dark": "#e55a1c",
          sidebar: "#1f2a36",
          "sidebar-deep": "#161d26",
          rail: "#ff6c2c",
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
          DEFAULT: "#1a5fb4",
          soft: "#4d8fd4",
          deep: "#154a8f",
        },
        surface: {
          light: "#d8e0ea",
          dark: "#0e1520",
        },
      },
      fontFamily: {
        display: ['"Outfit"', "system-ui", "sans-serif"],
        sans: ['"Manrope"', "system-ui", "sans-serif"],
        mono: ['Consolas', '"Courier New"', "monospace"],
      },
      boxShadow: {
        panel: "0 2px 4px rgba(26, 43, 60, 0.08), 0 8px 20px rgba(26, 43, 60, 0.1)",
        tool: "0 2px 6px rgba(26, 43, 60, 0.1)",
        login: "0 24px 64px rgba(15, 28, 42, 0.28)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.45s cubic-bezier(0.22, 1, 0.36, 1) both",
        "fade-in": "fade-in 0.6s ease both",
      },
    },
  },
  plugins: [],
};
