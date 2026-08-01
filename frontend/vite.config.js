import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import Components from "unplugin-vue-components/vite";
import { ElementPlusResolver } from "unplugin-vue-components/resolvers";

// 后端默认端口 8620（backend/app/config.py BACKEND_PORT）；
// dev 用 proxy 免 CORS 配置漂移，生产走 FastAPI 静态托管 dist/ 同源直连。
export default defineConfig({
  plugins: [
    vue(),
    Components({
      dts: false,
      dirs: [],
      resolvers: [
        ElementPlusResolver({
          importStyle: "css",
          directives: true,
        }),
      ],
    }),
  ],
  server: {
    port: 8621,
    // UI 验收 iframe 刻意不授予 allow-same-origin，浏览器会以 Origin:null
    // 加载开发模块；只在 Vite 开发服务器放行该 opaque origin。生产构建不含
    // ui-lab.html，也不会继承这条 CORS 配置。
    cors: { origin: "null" },
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8620",
        changeOrigin: true,
      },
    },
  },
  // 标准构建始终产出可审计 manifest；体积预算门不依赖手工参数或旧 dist。
  build: {
    manifest: true,
  },
});
