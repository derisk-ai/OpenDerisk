import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  async redirects() {
    return [
      {
        source: '/',
        destination: '/chat',
        permanent: true, // This will redirect the root path to the chat page
      },
    ]
  },
  output: 'export',  
  trailingSlash: true,       
  distDir: 'out',  
  images: {
    unoptimized: true, // 关闭优化，直接输出原图
  },    
  turbopack: {
    rules: {
      '*.less': {
        loaders: ['less-loader', 'css-loader'],
        as: '*.js',
      },
    },
  }, 
};

export default nextConfig;
