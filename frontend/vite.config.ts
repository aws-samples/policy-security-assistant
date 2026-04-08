import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist" },
  server: {
    proxy: {
      // For local dev: proxy /api to your deployed CloudFront URL
      // Update the target to your CloudFront domain after first deploy
      // "/api": { target: "https://d2vim2no9q7kn4.cloudfront.net", changeOrigin: true },
    },
  },
});
