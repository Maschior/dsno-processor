import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base: './' so the build loads from file:// inside the packaged app.
export default defineConfig({
  plugins: [react()],
  base: "./",
});
