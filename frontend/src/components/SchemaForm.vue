<template>
  <div class="schema-form">
    <el-form-item
      v-for="f in fields"
      :key="f.key"
      :label="f.label"
      :required="f.required"
      class="sf-item"
    >
      <!-- 长文本 -->
      <el-input
        v-if="f.kind === 'textarea'"
        v-model="model[f.key]"
        type="textarea"
        :rows="4"
        :maxlength="f.maxLength"
        :show-word-limit="!!f.maxLength"
        :placeholder="`请填写${f.label}`"
      />
      <!-- 单行文本 -->
      <el-input
        v-else-if="f.kind === 'text'"
        v-model="model[f.key]"
        :maxlength="f.maxLength"
        :placeholder="`请填写${f.label}`"
      />
      <!-- 数字 -->
      <el-input-number
        v-else-if="f.kind === 'number'"
        v-model="model[f.key]"
        :min="f.min"
        :max="f.max"
        :step="1"
        :step-strictly="f.integer"
        controls-position="right"
        class="sf-control"
      />
      <!-- 布尔 -->
      <el-switch v-else-if="f.kind === 'boolean'" v-model="model[f.key]" />
      <!-- 枚举 -->
      <el-select
        v-else-if="f.kind === 'enum'"
        v-model="model[f.key]"
        :placeholder="`请选择${f.label}`"
        class="sf-control"
      >
        <el-option v-for="opt in f.enum" :key="opt" :label="opt" :value="opt" />
      </el-select>
      <!-- 字符串列表：动态增删行 -->
      <div v-else-if="f.kind === 'string-list'" class="sf-list">
        <div v-for="(item, i) in model[f.key]" :key="i" class="sf-row">
          <el-input
            v-model="model[f.key][i]"
            :maxlength="f.itemMaxLength"
            :placeholder="f.itemPlaceholder || `${f.label} 第 ${i + 1} 项`"
          />
          <el-button text :disabled="disabled" class="sf-remove" @click="removeAt(f.key, i)">移除</el-button>
        </div>
        <el-button size="small" :disabled="disabled || atMax(f)" @click="addString(f.key)">
          ＋ 添加{{ f.label }}
        </el-button>
      </div>
      <!-- 对象列表：动态增删子表单 -->
      <div v-else-if="f.kind === 'object-list'" class="sf-objlist">
        <div v-for="(row, i) in model[f.key]" :key="i" class="sf-objcard">
          <div class="sf-objhead">
            <span class="sf-objtitle">{{ f.label }} {{ i + 1 }}</span>
            <el-button text :disabled="disabled" class="sf-remove" @click="removeAt(f.key, i)">移除</el-button>
          </div>
          <el-form-item
            v-for="sub in f.subFields"
            :key="sub.key"
            :label="sub.label"
            :required="sub.required"
            class="sf-subitem"
          >
            <el-input-number
              v-if="sub.kind === 'number'"
              v-model="model[f.key][i][sub.key]"
              :min="sub.min"
              :max="sub.max"
              :step-strictly="sub.integer"
              controls-position="right"
              class="sf-control"
            />
            <el-switch v-else-if="sub.kind === 'boolean'" v-model="model[f.key][i][sub.key]" />
            <el-select
              v-else-if="sub.kind === 'enum'"
              v-model="model[f.key][i][sub.key]"
              :placeholder="`请选择${sub.label}`"
              class="sf-control"
            >
              <el-option v-for="opt in sub.enum" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <el-input
              v-else
              v-model="model[f.key][i][sub.key]"
              :placeholder="`请填写${sub.label}`"
            />
          </el-form-item>
        </div>
        <el-button size="small" :disabled="disabled || atMax(f)" @click="addRow(f)">
          ＋ 添加{{ f.label }}
        </el-button>
      </div>

      <div v-if="f.description" class="sf-hint">{{ f.description }}</div>
    </el-form-item>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { parseSchema, blankObjectRow } from "../utils/schemaForm";

const props = defineProps({
  schema: { type: Object, default: null },
  // 由父组件持有的响应式 values 对象；本组件就地读写其字段（数组增删/标量赋值）。
  model: { type: Object, required: true },
  disabled: { type: Boolean, default: false },
});

const fields = computed(() => parseSchema(props.schema).fields);

function ensureArray(key) {
  if (!Array.isArray(props.model[key])) props.model[key] = [];
  return props.model[key];
}
function fieldByKey(key) {
  return fields.value.find((f) => f.key === key);
}
function atMax(f) {
  return typeof f.maxItems === "number" && Array.isArray(props.model[f.key]) && props.model[f.key].length >= f.maxItems;
}
function addString(key) {
  ensureArray(key).push("");
}
function addRow(f) {
  ensureArray(f.key).push(blankObjectRow(f.subFields));
}
function removeAt(key, i) {
  const arr = ensureArray(key);
  arr.splice(i, 1);
}
</script>

<style scoped>
.schema-form {
  display: block;
}
.sf-item {
  margin-bottom: 18px;
}
.sf-control {
  width: 100%;
  max-width: 260px;
}
.sf-list,
.sf-objlist {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.sf-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sf-remove {
  flex: 0 0 auto;
  color: var(--ink-faint);
}
.sf-remove:hover {
  color: var(--trust-fail, #be3a3a);
}
.sf-objcard {
  border: 1px solid var(--hairline);
  border-radius: 10px;
  padding: 12px 14px 4px;
  background: var(--paper-rail, #f7f4ef);
}
.sf-objhead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.sf-objtitle {
  font-size: 12.5px;
  font-weight: 700;
  color: var(--clay, #c15f3c);
}
.sf-subitem {
  margin-bottom: 10px;
}
.sf-hint {
  color: var(--ink-faint);
  font-size: 12px;
  line-height: 1.5;
  margin-top: 4px;
}
</style>
