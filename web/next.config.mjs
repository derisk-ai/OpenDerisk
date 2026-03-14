import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ['@antv/gpt-vis'],
  images: {
    unoptimized: true,
    dangerouslyAllowSVG: true,
    remotePatterns: [
      {
        protocol: 'https',
        hostname: '**',
      },
    ],
  },
  webpack: config => {
    config.module.rules.push({
      test: /\.svg$/,
      use: ['@svgr/webpack'],
    });
    // Alias @antv/l7-component less to empty CSS to avoid needing less-loader
    const emptyCssPath = path.resolve(__dirname, 'src/styles/empty.css');
    config.resolve.alias = {
      ...config.resolve.alias,
      '@antv/l7-component/es/css/index.less': emptyCssPath,
      [path.resolve(
        __dirname,
        'node_modules/@antv/l7-component/es/css/index.less'
      )]: emptyCssPath,
    };
    return config;
  },
  // Ignore typescript and eslint errors during build
  typescript: {
    ignoreBuildErrors: true,
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
  output: 'export',
  trailingSlash: true,
};

export default nextConfig;
