/** @type {import('next').NextConfig} */
const nextConfig = {
  // Minimal, self-contained runtime for the production Docker image — see
  // web/Dockerfile's "runtime" stage.
  output: "standalone",
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
}

export default nextConfig
