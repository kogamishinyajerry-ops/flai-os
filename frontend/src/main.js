import { createApp } from "vue";
import { provideGlobalConfig } from "element-plus";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import "element-plus/es/components/message/style/css";
import "element-plus/es/components/message-box/style/css";

import App from "./App.vue";
import router from "./router";

// Element Plus 由 Vite resolver 按模板实际使用量导入；全局配置仍明确注入，
// 保持表单、分页和服务型组件（ElMessage/ElMessageBox）的中文 locale。
const app = createApp(App);
provideGlobalConfig({ locale: zhCn }, app, true);
app.use(router).mount("#app");
