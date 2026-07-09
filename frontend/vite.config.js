import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// 后端默认端口 8620（backend/app/config.py BACKEND_PORT）；
// dev 用 proxy 免 CORS 配置漂移，生产走 FastAPI 静态托管 dist/ 同源直连。
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 8621,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8620",
        changeOrigin: true,
      },
    },
  },
});
