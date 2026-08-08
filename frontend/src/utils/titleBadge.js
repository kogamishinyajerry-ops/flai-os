// N5 标签页标题徽章：内网 http 非 secure context，Notification API 不可用——
// 用户切去别的标签页后，「待你签发」的召回只剩 document.title 一条通道。
// 本模块是全应用唯一的 title 写手（router afterEach 与状态坞徽章都经此合成），
// 防止两处 document.title = ... 互相覆盖：路由切换丢徽章，或徽章更新丢页名。
// 计数来源=状态坞的真实轮询计数（诚实地板），清零/卸载即还原纯页名。

import { PLATFORM_NAME } from "./branding";

let base = PLATFORM_NAME;
let badgeCount = 0;

function render() {
  document.title = badgeCount > 0 ? `(${badgeCount} 待签) ${base}` : base;
}

export function setTitleBase(title) {
  base = title || PLATFORM_NAME;
  render();
}

export function setTitleBadge(count) {
  badgeCount = Number.isFinite(count) && count > 0 ? Math.floor(count) : 0;
  render();
}
