export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        slate: { 400: "#afc1cc", 500: "#91a8b7" },
        petrol: {
          950: "#081820",
          900: "#102630",
          800: "#16323c",
          700: "#264651",
          600: "#1b6176",
          500: "#238098",
        },
      },
    },
  },
  plugins: [],
};
