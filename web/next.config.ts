import type { NextConfig } from "next";

// The browser calls /api/*, which Next forwards to the FastAPI service. This keeps the
// API off the browser's origin (no CORS) and lets the backend URL differ per environment.
const API_URL = process.env.API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  devIndicators: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default nextConfig;
