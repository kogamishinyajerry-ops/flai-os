// Workspace Shell V1 原型入口。仅挂载合成夹具驱动的原型，
// 不连接真实后端，不发任何网络请求。
import { createApp } from "vue";
import WorkspaceShellPrototype from "./WorkspaceShellPrototype.vue";
import "./workspace-shell.css";

createApp(WorkspaceShellPrototype).mount("#app");
