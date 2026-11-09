import type { NextConfig } from "next";

// 后端地址：容器部署时通过 BACKEND_URL 注入（如 http://host.docker.internal:8000），
// 本地开发与默认行为不变。rewrites 在服务器启动时求值，运行时注入即生效。
const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // 关闭 gzip：压缩缓冲会导致代理转发的 SSE 事件迟迟不到达浏览器
  compress: false,
  // 关闭左下角 Next.js dev 指示器（N 圆形），避免用户误解为功能入口
  devIndicators: false,
  // Docker 优化：产出独立可执行目录（.next/standalone），镜像无需携带完整 node_modules
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
