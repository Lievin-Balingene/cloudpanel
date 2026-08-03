/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        cp: {
          orange: "#34d399",
          "orange-dark": "#10b981",
          "orange-soft": "rgba(52, 211, 153, 0.12)",
          navy: "#0b1622",
          "navy-soft": "#122033",
          sidebar: "#0b1622",
          header: "#0b1622",
          border: "rgba(255,255,255,0.1)",
          canvas: "#071018",
          panel: "#0c1622",
          text: "#f4f7fb",
          muted: "rgba(255,255,255,0.5)",
          link: "#ffffff",
          success: "#34d399",
          danger: "#fb7185",
        },
        ink: {
          50: "#f4f7fb",
          100: "#e8eef6",
          200: "rgba(255,255,255,0.7)",
          300: "rgba(255,255,255,0.55)",
          400: "rgba(255,255,255,0.4)",
          500: "rgba(255,255,255,0.3)",
          600: "#3f618c",
          700: "rgba(255,255,255,0.12)",
          800: "rgba(255,255,255,0.1)",
          900: "#122033",
          950: "#0b1622",
        },
        accent: {
          DEFAULT: "#34d399",
          soft: "#6ee7b7",
          deep: "#10b981",
        },
        surface: {
          light: "#0b1622",
          dark: "#071018",
        },
      },
      fontFamily: {
        display: ['"Syne"', "Georgia", "serif"],
        sans: ['"Manrope"', "system-ui", "sans-serif"],
        mono: ['Consolas', '"Courier New"', "monospace"],
      },
      boxShadow: {
        panel: "0 12px 40px rgba(0, 0, 0, 0.28)",
        tool: "0 1px 2px rgba(0,0,0,0.2)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "login-reveal": {
          "0%": { opacity: "0", transform: "translateY(18px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "aurora-drift": {
          "0%, 100%": { transform: "translate3d(0,0,0) scale(1)" },
          "50%": { transform: "translate3d(2%, -1.5%, 0) scale(1.04)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.25s ease-out both",
        "login-reveal": "login-reveal 0.55s cubic-bezier(0.22, 1, 0.36, 1) both",
        "aurora-drift": "aurora-drift 18s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
