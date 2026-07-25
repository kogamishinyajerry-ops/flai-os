import { createApp } from "vue";
import ElementPlus from "element-plus";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import "element-plus/dist/index.css";
// 设计 token + 全局层（SSOT）：必须在 Element Plus 样式之后 import，其内 --el-*
// 变量覆盖才生效（原内联于 App.vue <style>，打磨批抽离为独立可审计文件）。
import "./styles/tokens.css";

import App from "./App.vue";
import router from "./router";

// V0.1 全量引入 Element Plus（页面简洁优先，不引入按需加载的构建复杂度——
// 内网静态托管场景 bundle 体积不是瓶颈，构建确定性是）。
createApp(App).use(router).use(ElementPlus, { locale: zhCn }).mount("#app");
