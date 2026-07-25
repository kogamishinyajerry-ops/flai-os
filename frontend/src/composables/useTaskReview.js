// 签发动作核心 SSOT（打磨批）：TaskDetail.handleReview 与 StatusCenter.doReview
// 原本是各自实现的两份签发逻辑——同一宪法路径（confirm→reviewTask→markTaskSeen
// →清 comment→success 提示→approve 才 teal 迸发→pokeTask 带外补拉→错误提示→
// 解锁）在两处维护，存在行为漂移风险（一处改漏另一处）。此处收口为 composable，
// 两处 UI 各自保留（peek 紧凑卡 / el-card 表单结构不同），只共享「动作链」。
//
// 红线承袭：人是唯一签发者（前端不发身份，服务端派生）· fail-closed ·
// approve 成功是唯一 teal burst 许可点（驳回/失败绝不动效）。
import { ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { reviewTask } from "../api/tasks";
import { pokeTask } from "../stores/liveFeed";
import { markTaskSeen } from "../utils/lastSeen";
import { burstSigned } from "../effects/burst";

/**
 * @param {object} opts
 * @param {() => string} opts.getTaskId   取当前任务 id（调用时捕获，await 期间不漂）
 * @param {() => string} opts.getComment  取意见草稿（签发落定后由 setComment 清空）
 * @param {(v: string) => void} opts.setComment
 * @param {() => (HTMLElement|null)} [opts.getApproveEl]  teal 迸发定位元素（approve 用）
 * @param {() => boolean} [opts.shouldSettle]  落定谓词：返回 false 则跳过 burst+poke
 *        （StatusCenter 续体绑定：await 期间抽屉已关/任务已切时不在旧任务上迸发刷新）。
 *        缺省恒 true（TaskDetail 语义：详情页签发即落定本任务）。
 * @param {(action: string) => Promise<void>|void} [opts.afterSuccess]
 *        签发成功且数据已 poke 落地后的钩子（如 StatusCenter 的 loadAcceptedSamples）；
 *        reviewing 解锁在此之后，防二次提交 409。
 * @param {object} [opts.text]  文案覆盖：confirmTitle/confirmOk/confirmCancel/successOf
 */
export function useTaskReview(opts) {
  const {
    getTaskId,
    getComment,
    setComment,
    getApproveEl = () => null,
    shouldSettle = () => true,
    afterSuccess = null,
    text = {},
  } = opts;

  const reviewing = ref(false);

  const labelOf = (action) => (action === "approve" ? "批准放行" : "拒绝");
  // 文案均支持「字符串 | (action, label) => 字符串」，供按动作动态生成
  // （StatusCenter confirmOk 是 `确认${label}`）。
  const resolve = (v, action, label) => (typeof v === "function" ? v(action, label) : v);
  const successOf = (action) =>
    text.successOf ? resolve(text.successOf, action, labelOf(action)) : `已${labelOf(action)}`;

  async function submitReview(action) {
    const taskId = getTaskId();
    if (!taskId) return;
    const label = labelOf(action);
    try {
      // 二次确认：内联/详情同宪法路径，操作摩擦不降低。
      // confirmOk/confirmCancel 缺省时不传——沿用 EP 默认「确定」/「取消」
      // （TaskDetail 原语义，e2e 按「确定」定位）；仅调用方显式覆盖才自定义
      // （StatusCenter 用「确认${label}」/「再看看」）。
      const boxOpts = { type: "warning" };
      const okText = resolve(text.confirmOk, action, label);
      const cancelText = resolve(text.confirmCancel, action, label);
      if (okText) boxOpts.confirmButtonText = okText;
      if (cancelText) boxOpts.cancelButtonText = cancelText;
      await ElMessageBox.confirm(`确认${label}该任务？`, text.confirmTitle || label, boxOpts);
    } catch {
      return; // 用户取消
    }
    reviewing.value = true;
    try {
      await reviewTask(taskId, { action, comment: getComment() || null });
      markTaskSeen(taskId); // 亲手签发=已看过：其后完成不得对签发者亮未读
      setComment(""); // 签发落定即清，绝不残留到下一个任务
      const notifyReviewOutcome = action === "approve" ? ElMessage.info : ElMessage.error;
      notifyReviewOutcome(successOf(action));
      // 续体绑定（shouldSettle）：await 期间视图可能已切走——只有仍落在本任务上
      // 才迸发+补拉；切走则跳过（下轮 channel 轮询自会回填，不在旧任务上加戏）。
      // 传入调用时捕获的 taskId，供调用方比较「当前任务是否仍为这个 id」。
      if (shouldSettle(taskId)) {
        // 人签放行成功是唯一 teal 许可点；驳回/失败绝不放庆祝动效。
        // 元素取不到 burstSigned 自兜 null。
        if (action === "approve") burstSigned(getApproveEl());
        // 带外补拉：不等下一轮询，动作结果立即回显。await 让 reviewing 在数据真
        // 落地后才解锁——否则用户可能在旧数据仍显示 waiting_review 时二次提交触发 409。
        await pokeTask(taskId);
      }
      if (afterSuccess) await afterSuccess(action, taskId);
    } catch (err) {
      ElMessage.error(err.detail || err.message || "签发失败");
    } finally {
      reviewing.value = false;
    }
  }

  return { reviewing, submitReview };
}
