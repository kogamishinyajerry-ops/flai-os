// 按 Agent input_schema（JSON Schema）驱动创建表单的解析/初始化/收集/校验工具。
//
// 边界（P0-1）：只覆盖平台各 Agent input_schema 真实用到的类型
// （string / integer|number / boolean / enum / array<string> / array<object>）。
// 任何超出（$ref/oneOf/anyOf/allOf、嵌套非数组 object、数组套数组等）→ renderable:false，
// 调用方降级回 JSON 手填,绝不因 schema 复杂而阻断建任务。前端校验只是 UX 兜前，
// 真正的合法性判定仍由后端 jsonschema + Tool Registry fail-closed 负责。

const SIMPLE_KINDS = ["text", "textarea", "number", "boolean", "enum"];
const COMPLEX_KEYS = ["$ref", "oneOf", "anyOf", "allOf", "not", "if"];

function parseField(key, prop, required) {
  if (!prop || typeof prop !== "object") return null;
  if (COMPLEX_KEYS.some((k) => k in prop)) return null;
  const base = {
    key,
    label: prop.title || key,
    description: prop.description || "",
    required,
  };
  const t = prop.type;
  if (t === "string") {
    if (Array.isArray(prop.enum)) {
      return { ...base, kind: "enum", enum: prop.enum };
    }
    // 仅明显长文本（maxLength > 500）用多行 textarea；顶事件/系统名等短字段用单行输入。
    const long = typeof prop.maxLength === "number" && prop.maxLength > 500;
    return { ...base, kind: long ? "textarea" : "text", maxLength: prop.maxLength, minLength: prop.minLength };
  }
  if (t === "integer" || t === "number") {
    return { ...base, kind: "number", min: prop.minimum, max: prop.maximum, integer: t === "integer" };
  }
  if (t === "boolean") {
    return { ...base, kind: "boolean" };
  }
  if (t === "array") {
    const items = prop.items || {};
    if (COMPLEX_KEYS.some((k) => k in items)) return null;
    if (items.type === "string") {
      return {
        ...base,
        kind: "string-list",
        minItems: prop.minItems,
        maxItems: prop.maxItems,
        itemMaxLength: items.maxLength,
        itemPlaceholder: items.description || "",
      };
    }
    if (items.type === "object" && items.properties) {
      const subReq = Array.isArray(items.required) ? items.required : [];
      const subFields = [];
      for (const [k, p] of Object.entries(items.properties)) {
        const sf = parseField(k, p, subReq.includes(k));
        if (!sf || !SIMPLE_KINDS.includes(sf.kind)) return null; // 子字段只支持标量,否则整表降级
        subFields.push(sf);
      }
      return { ...base, kind: "object-list", subFields, minItems: prop.minItems, maxItems: prop.maxItems };
    }
    return null;
  }
  return null;
}

// 解析 schema → { renderable, fields }。renderable=false 时 fields 为空。
export function parseSchema(schema) {
  if (!schema || typeof schema !== "object" || schema.type !== "object" || !schema.properties) {
    return { renderable: false, fields: [] };
  }
  if (COMPLEX_KEYS.some((k) => k in schema)) return { renderable: false, fields: [] };
  const required = Array.isArray(schema.required) ? schema.required : [];
  const fields = [];
  for (const [key, prop] of Object.entries(schema.properties)) {
    const f = parseField(key, prop, required.includes(key));
    if (!f) return { renderable: false, fields: [] };
    fields.push(f);
  }
  return { renderable: true, fields };
}

function blankValue(field) {
  switch (field.kind) {
    case "boolean":
      return false;
    case "number":
      return null;
    case "string-list":
    case "object-list":
      return [];
    default:
      return "";
  }
}

export function blankObjectRow(subFields) {
  const row = {};
  for (const sf of subFields) row[sf.key] = blankValue(sf);
  return row;
}

// 为一份 schema 建一个空白 values 对象（各字段按类型初始化）,可用 seed 预填覆盖。
export function blankInputs(schema, seed) {
  const { renderable, fields } = parseSchema(schema);
  if (!renderable) return {};
  const out = {};
  const src = seed && typeof seed === "object" ? seed : {};
  for (const f of fields) {
    if (f.key in src && src[f.key] !== undefined && src[f.key] !== null) {
      out[f.key] = coerceSeed(f, src[f.key]);
      continue;
    }
    // 必填/带 minItems 的列表预置若干空行——用户一眼看到要填什么，不必先点「添加」。
    if (f.kind === "string-list") {
      const n = f.minItems || (f.required ? 1 : 0);
      out[f.key] = Array.from({ length: n }, () => "");
    } else if (f.kind === "object-list") {
      const n = f.minItems || (f.required ? 1 : 0);
      out[f.key] = Array.from({ length: n }, () => blankObjectRow(f.subFields));
    } else {
      out[f.key] = blankValue(f);
    }
  }
  return out;
}

function coerceSeed(field, val) {
  if (field.kind === "string-list") return Array.isArray(val) ? val.map((v) => (v == null ? "" : String(v))) : [];
  if (field.kind === "object-list") {
    if (!Array.isArray(val)) return [];
    return val.map((obj) => {
      const row = blankObjectRow(field.subFields);
      if (obj && typeof obj === "object") {
        for (const sf of field.subFields) if (sf.key in obj && obj[sf.key] != null) row[sf.key] = obj[sf.key];
      }
      return row;
    });
  }
  if (field.kind === "number") return typeof val === "number" ? val : val === "" ? null : Number(val);
  if (field.kind === "boolean") return Boolean(val);
  return val == null ? "" : String(val);
}

// 把 values 收集成提交用 inputs：裁掉空的可选字段、过滤 string-list 空项、数字转型。
export function collectInputs(schema, values) {
  const { fields } = parseSchema(schema);
  const out = {};
  for (const f of fields) {
    const v = values[f.key];
    if (f.kind === "text" || f.kind === "textarea" || f.kind === "enum") {
      const s = typeof v === "string" ? v.trim() : v;
      if (s !== "" && s != null) out[f.key] = s;
    } else if (f.kind === "number") {
      if (v !== null && v !== undefined && v !== "") out[f.key] = Number(v);
    } else if (f.kind === "boolean") {
      out[f.key] = Boolean(v);
    } else if (f.kind === "string-list") {
      const arr = (Array.isArray(v) ? v : []).map((x) => (typeof x === "string" ? x.trim() : x)).filter((x) => x !== "" && x != null);
      if (arr.length) out[f.key] = arr;
    } else if (f.kind === "object-list") {
      const arr = (Array.isArray(v) ? v : [])
        .map((row) => collectRow(f.subFields, row))
        .filter((row) => Object.keys(row).length > 0);
      if (arr.length) out[f.key] = arr;
    }
  }
  return out;
}

function collectRow(subFields, row) {
  const out = {};
  for (const sf of subFields) {
    const v = row ? row[sf.key] : undefined;
    if (sf.kind === "number") {
      if (v !== null && v !== undefined && v !== "") out[sf.key] = Number(v);
    } else if (sf.kind === "boolean") {
      out[sf.key] = Boolean(v);
    } else {
      const s = typeof v === "string" ? v.trim() : v;
      if (s !== "" && s != null) out[sf.key] = s;
    }
  }
  return out;
}

// 轻量前端校验（UX 兜前，非安全边界）：返回错误串数组,空=通过。
export function validateInputs(schema, values) {
  const { fields } = parseSchema(schema);
  const errors = [];
  for (const f of fields) {
    const v = values[f.key];
    if (f.kind === "text" || f.kind === "textarea" || f.kind === "enum") {
      const empty = typeof v !== "string" || v.trim() === "";
      if (f.required && empty) errors.push(`「${f.label}」不能为空`);
    } else if (f.kind === "number") {
      const unset = v === null || v === undefined || v === "";
      if (f.required && unset) errors.push(`「${f.label}」不能为空`);
      if (!unset) {
        const n = Number(v);
        if (Number.isNaN(n)) errors.push(`「${f.label}」必须是数字`);
        else {
          if (typeof f.min === "number" && n < f.min) errors.push(`「${f.label}」不能小于 ${f.min}`);
          if (typeof f.max === "number" && n > f.max) errors.push(`「${f.label}」不能大于 ${f.max}`);
        }
      }
    } else if (f.kind === "string-list") {
      const arr = (Array.isArray(v) ? v : []).filter((x) => typeof x === "string" && x.trim() !== "");
      if (f.required && arr.length === 0) errors.push(`「${f.label}」至少需要一项`);
      if (typeof f.minItems === "number" && arr.length > 0 && arr.length < f.minItems)
        errors.push(`「${f.label}」至少需要 ${f.minItems} 项`);
    } else if (f.kind === "object-list") {
      const rows = Array.isArray(v) ? v : [];
      const nonEmpty = rows.filter((r) => Object.keys(collectRow(f.subFields, r)).length > 0);
      if (f.required && nonEmpty.length === 0) errors.push(`「${f.label}」至少需要一项`);
      nonEmpty.forEach((row, i) => {
        for (const sf of f.subFields) {
          const cell = row ? row[sf.key] : undefined;
          const empty = cell === null || cell === undefined || (typeof cell === "string" && cell.trim() === "");
          if (sf.required && empty) errors.push(`「${f.label}」第 ${i + 1} 项的「${sf.label}」不能为空`);
        }
      });
    }
  }
  return errors;
}
