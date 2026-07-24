import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// 后端默认端口 8620（backend/app/config.py BACKEND_PORT）；
// dev 用 proxy 免 CORS 配置漂移，生产走 FastAPI 静态托管 dist/ 同源直连。
// stage-c 多页入口（kimi-uiux-001@3，owner 指令授权）：合成原型经
// /stage-c.html 在 dev / preview / dist 静态托管中可达；页面本身只做
// SYNTHETIC 展示，不连接后端、不构成任何真实执行或签发语义。
export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL("./index.html", import.meta.url)),
        "stage-c": fileURLToPath(new URL("./stage-c.html", import.meta.url)),
      },
    },
  },
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
