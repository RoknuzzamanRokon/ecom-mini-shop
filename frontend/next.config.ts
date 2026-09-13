import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    unoptimized: true,
    remotePatterns: [
      {
        protocol: "http",
        hostname: "127.0.0.1",
        port: "8000",
        pathname: "/media/**",
      },
      {
        protocol: "http",
        hostname: "localhost",
        port: "8000",
        pathname: "/media/**",
      },
      {
        protocol: "http",
        hostname: "127.0.0.1",
        port: "8001",
        pathname: "/media/**",
      },
      {
        protocol: "http",
        hostname: "localhost",
        port: "8001",
        pathname: "/media/**",
      },
      {
        protocol: "https",
        hostname: "lh3.googleusercontent.com",
      },
    ],
  },
  async rewrites() {
    const backendUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001";
    return [
      {
        source: "/media/:path*",
        destination: `${backendUrl}/media/:path*`,
      },
    ];
  },
  async redirects() {
    return [
      {
        source: "/account",
        destination: "/profile",
        permanent: false,
      },
      {
        source: "/account/orders",
        destination: "/profile/orders",
        permanent: false,
      },
      {
        source: "/account/addresses",
        destination: "/profile/addresses",
        permanent: false,
      },
      {
        source: "/account/profile",
        destination: "/profile/settings",
        permanent: false,
      },
      {
        source: "/account/orders/:orderNumber",
        destination: "/profile/orders/:orderNumber",
        permanent: false,
      },
      {
        source: "/account/:path*",
        destination: "/profile/:path*",
        permanent: false,
      },
    ];
  },
};

export default nextConfig;
