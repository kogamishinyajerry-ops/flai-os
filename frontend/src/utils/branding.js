/** 品牌命名 SSOT（票 #62 B1，map #46 批 2；owner 2026-08-06 裁⑥⑦）。
 *
 * 双名制明文化：
 * - PLATFORM_NAME「FLAi-OS」= 平台名（侧栏/登录门/title/文档等产品面）
 * - ASSISTANT_NAME「FLAi」= 助手人格名（会话气泡名/口播等人格面）
 * 两者是**两个名字、两条用途轴**，不互推不缩写互替。
 *
 * - PLATFORM_SUBTITLE「二所工程智能体运行底座」= 平台副标（保留「二所」，owner 裁⑥）。
 *
 * 全站命名散点只许引本模块，不再各写字面。例外与边界（如实留痕）：
 * - 静态 HTML（frontend/index.html `<title>`）无法 import——其字面与本常量
 *   保持同字面，改动必须两侧同批（node 锚 branding.test.mjs 锁这条）。
 * - 后端 FastAPI title 走 backend/app/config.py APP_NAME（跨语言无法共享
 *   模块，字面相映同源，同批纪律同上）。
 * - ui-lab 验收台（DEV ONLY）另有独立 title 写入，同样引本模块。
 */
export const PLATFORM_NAME = "FLAi-OS";
export const ASSISTANT_NAME = "FLAi";
export const PLATFORM_SUBTITLE = "二所工程智能体运行底座";
