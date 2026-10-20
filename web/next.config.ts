import type { NextConfig } from "next";

// Static export: the site is plain files served by Azure Static Web Apps (or the gateway
// in local mode). Pages read the match id from the query string, so no dynamic routes.
const config: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default config;
