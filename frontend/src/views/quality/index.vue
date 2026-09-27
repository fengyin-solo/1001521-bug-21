<template>
  <section class="page" data-module="quality">
    <header class="page-head">
      <div>
        <h2>数据质控管理</h2>
        <p class="page-desc">维护质控任务，围绕质控编号、质控时段、涉及站点、质控规则做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记质控任务</button>
        <button class="btn" type="button" @click="exportRows">导出数据质控清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>质控状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <RouterLink
              v-if="column === '质控编号'"
              class="link"
              :to="`/quality/${row.id}`"
            >{{ row[column] ?? '—' }}</RouterLink>
            <template v-else>{{ displayCell(row, column) }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actionsFor(row)"
              :key="action"
              class="link"
              type="button"
              :disabled="actionPending"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <RouterLink class="link" :to="`/quality/${row.id}`">详情</RouterLink>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无数据质控数据，可先登记质控任务</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条数据质控记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
    </footer>

    <div v-if="dialog" class="modal-mask" @click.self="closeDialog">
      <form class="modal-card" @submit.prevent="submitDialog">
        <h3 class="modal-title">{{ dialog.title }}</h3>
        <p v-if="dialog.hint" class="modal-hint">{{ dialog.hint }}</p>
        <label v-for="field in dialog.fields" :key="field.name" class="modal-field">
          <span>{{ field.label }}<em v-if="field.required" class="required-mark">*</em></span>
          <textarea
            v-if="field.type === 'textarea'"
            v-model="dialog.values[field.name]"
            rows="3"
            :placeholder="field.placeholder"
          ></textarea>
          <input
            v-else
            v-model="dialog.values[field.name]"
            :type="field.type ?? 'text'"
            :placeholder="field.placeholder"
          />
        </label>
        <p v-if="dialog.error" class="error-text">{{ dialog.error }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeDialog">取消</button>
          <button class="btn primary" type="submit" :disabled="actionPending">
            {{ actionPending ? '提交中…' : '确认提交' }}
          </button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null> & { id: number; status?: string }

interface DialogField {
  name: string
  label: string
  type?: string
  required?: boolean
  placeholder?: string
}

interface DialogState {
  kind: 'create' | 'action'
  title: string
  hint?: string
  fields: DialogField[]
  values: Record<string, string>
  row?: Row
  action?: string
  error: string
}

const ENDPOINT = '/api/quality'
const columns = ["质控编号", "质控时段", "涉及站点", "质控规则", "当前轮次", "检出疑误数", "退回原因", "质控状态"]
const statuses = ["待执行", "执行中", "已完成", "已退回"]
// 每个状态下允许执行的动作，与后端状态机保持一致
const ACTIONS_BY_STATUS: Record<string, string[]> = {
  "待执行": ["启动质控"],
  "执行中": ["确认完成", "退回重做"],
  "已退回": ["启动质控"],
  "已完成": ["退回重做"],
}

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref([{ label: '待执行质控', value: 0 }, { label: '本月质控轮次', value: 0 }, { label: '检出疑误数', value: 0 }])
const errorMessage = ref('')
const noticeMessage = ref('')
const actionPending = ref(false)
const dialog = ref<DialogState | null>(null)
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

function actionsFor(row: Row): string[] {
  return ACTIONS_BY_STATUS[String(row.status ?? row['质控状态'] ?? '')] ?? []
}

function displayCell(row: Row, column: string) {
  const value = row[column]
  if (value === null || value === undefined || value === '') return '—'
  return value
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  dialog.value = {
    kind: 'create',
    title: '登记质控任务',
    hint: '质控编号、质控时段、涉及站点为必填项，登记后任务进入待执行。',
    fields: [
      { name: '质控编号', label: '质控编号', required: true, placeholder: '如 QUAL-0004' },
      { name: '质控时段', label: '质控时段', required: true, placeholder: '如 2026-09-27' },
      { name: '涉及站点', label: '涉及站点', required: true },
      { name: '质控规则', label: '质控规则' },
      { name: '质控人员', label: '质控人员' },
    ],
    values: {},
    error: '',
  }
}

function runAction(action: string, row: Row) {
  if (action === '确认完成') {
    dialog.value = {
      kind: 'action',
      title: `确认完成 ${row['质控编号']}`,
      hint: `当前为第 ${row['当前轮次'] ?? 1} 轮质控，请填写本轮检出疑误数。`,
      fields: [
        { name: '检出疑误数', label: '检出疑误数', type: 'number', required: true, placeholder: '非负整数' },
        { name: '质控人员', label: '质控人员' },
      ],
      values: {},
      row,
      action,
      error: '',
    }
    return
  }
  if (action === '退回重做') {
    dialog.value = {
      kind: 'action',
      title: `退回重做 ${row['质控编号']}`,
      hint: '退回后任务停在已退回，退回原因会写入本轮台账并保留。',
      fields: [
        { name: '退回原因', label: '退回原因', type: 'textarea', required: true, placeholder: '请说明退回原因，便于重做时定位问题' },
      ],
      values: {},
      row,
      action,
      error: '',
    }
    return
  }
  void submitAction(action, row, {})
}

function closeDialog() {
  if (!actionPending.value) dialog.value = null
}

async function submitDialog() {
  const current = dialog.value
  if (!current) return
  const missing = current.fields.filter(
    (f) => f.required && !String(current.values[f.name] ?? '').trim(),
  )
  if (missing.length) {
    current.error = `请填写：${missing.map((f) => f.label).join('、')}`
    return
  }
  if (current.kind === 'create') {
    await submitCreate(current.values)
  } else if (current.row && current.action) {
    await submitAction(current.action, current.row, current.values)
  }
}

async function submitCreate(values: Record<string, string>) {
  actionPending.value = true
  errorMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message ?? payload.detail ?? '质控任务登记失败')
    }
    dialog.value = null
    noticeMessage.value = payload.message ?? '质控任务已登记'
    await reload()
  } catch (error) {
    if (dialog.value) dialog.value.error = error instanceof Error ? error.message : '质控任务登记失败'
  } finally {
    actionPending.value = false
  }
}

async function submitAction(action: string, row: Row, values: Record<string, string>) {
  if (actionPending.value) return
  actionPending.value = true
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...values, action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message ?? payload.detail ?? '数据质控动作未生效')
    }
    dialog.value = null
    noticeMessage.value = payload.message ?? `质控任务已${action}`
    await reload()
  } catch (error) {
    const message = error instanceof Error ? error.message : '数据质控操作失败'
    if (dialog.value) dialog.value.error = message
    else errorMessage.value = message
  } finally {
    actionPending.value = false
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  const filterKeyMap: Record<string, string> = { 质控编号: 'keyword', 质控时段: 'period', 涉及站点: 'site' }
  for (const [field, param] of Object.entries(filterKeyMap)) {
    const value = filters.value[field]
    if (value) query.set(param, value)
  }
  if (filters.value.status) query.set('status', filters.value.status)
  try {
    const [listResponse, statsResponse] = await Promise.all([
      request(`${ENDPOINT}?${query.toString()}`),
      request(`${ENDPOINT}/stats`),
    ])
    if (!listResponse.ok) throw new Error('质控任务列表读取失败')
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (statsResponse.ok) {
      const statPayload = await statsResponse.json()
      stats.value = stats.value.map((item) => ({
        ...item,
        value: Number(statPayload[item.label] ?? 0),
      }))
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '数据质控列表读取失败'
  }
}

onMounted(reload)
</script>
