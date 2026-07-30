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
