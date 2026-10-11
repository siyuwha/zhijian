import type { Config } from "tailwindcss"

const config = {
  darkMode: ["class"],
  content: [
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
  ],
  prefix: "",
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // 极光暗夜流光调色板 (Aurora Night Palette)
        aurora: {
          bg: "#07090E",
          app: "#070A11",
          card: "#0F1626",
          "card-subtle": "#0B111E",
          "card-hover": "#141E33",
          pill: "#162032",
          border: "#1B2A45",
          "border-subtle": "#162238",
          "border-highlight": "#2A3F66",
          purple: {
            DEFAULT: "#8B5CF6",
            light: "#A855F7",
            dim: "rgba(168, 85, 247, 0.15)",
            dark: "#3B0764",
          },
          cyan: {
            DEFAULT: "#06B6D4",
            light: "#22D3EE",
            dim: "rgba(6, 182, 212, 0.15)",
            dark: "#083344",
          },
          rose: {
            DEFAULT: "#F43F5E",
            light: "#FB7185",
            dim: "rgba(244, 63, 94, 0.15)",
            dark: "#4C0519",
          },
          red: {
            DEFAULT: "#EF4444",
            light: "#F87171",
            dim: "rgba(239, 68, 68, 0.15)",
          },
          emerald: {
            DEFAULT: "#10B981",
            light: "#34D399",
            dim: "rgba(16, 185, 129, 0.15)",
            dark: "#022C22",
          },
          amber: {
            DEFAULT: "#F59E0B",
            light: "#FBBF24",
            dim: "rgba(245, 158, 11, 0.15)",
            dark: "#451A03",
            accent: "#D97706",
          },
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        "squircle-2xl": "1.25rem",
        "squircle-3xl": "1.5rem",
      },
      boxShadow: {
        "glow-purple": "0 0 24px -4px rgba(168, 85, 247, 0.35)",
        "glow-cyan": "0 0 24px -4px rgba(6, 182, 212, 0.35)",
        "glow-rose": "0 0 24px -4px rgba(244, 63, 94, 0.35)",
        "glow-red": "0 0 24px -4px rgba(239, 68, 68, 0.35)",
        "glow-amber": "0 0 24px -4px rgba(245, 158, 11, 0.35)",
        "glow-emerald": "0 0 24px -4px rgba(16, 185, 129, 0.35)",
        "glass-card": "0 20px 50px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.1)",
        "glass-card-hover": "0 24px 60px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.18)",
        "glass-pill": "0 8px 32px 0 rgba(0, 0, 0, 0.37), inset 0 1px 0 rgba(255, 255, 255, 0.12)",
      },
      backdropBlur: {
        xs: "2px",
        "2xl": "28px",
        "3xl": "36px",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        "aurora-pulse": {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.85", transform: "scale(1.02)" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "aurora-pulse": "aurora-pulse 4s ease-in-out infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
} satisfies Config

export default config
