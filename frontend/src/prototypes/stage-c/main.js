// Stage C 工作台原型入口。仅挂载合成夹具驱动的原型，不连接真实后端。
import { createApp } from "vue";
import StageCWorkbenchPrototype from "./StageCWorkbenchPrototype.vue";
import "./stage-c.css";

createApp(StageCWorkbenchPrototype).mount("#app");
