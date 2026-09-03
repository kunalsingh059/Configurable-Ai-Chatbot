/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,js}"],
  theme: {
    extend: {
      colors: {
        navy: {
          950: "#0b1224",
          900: "#111a33",
          800: "#1a2647",
        },
        amber: {
          500: "#e0a527",
          600: "#c8901c",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};