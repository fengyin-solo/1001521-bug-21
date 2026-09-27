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
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无数据质控数据，可先登记质控任务</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条数据质控记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/quality'
const columns = ["质控编号", "质控时段", "涉及站点", "质控规则", "检出疑误数", "当前轮次", "质控人员", "质控日期", "质控状态"]
const actions = ["启动质控", "确认完成", "退回重做", "详情"]

const router = useRouter()

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<Array<{ label: string; value: number }>>([
  { label: '待执行质控', value: 0 },
  { label: '本月质控轮次', value: 0 },
  { label: '检出疑误数', value: 0 },
])
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function openCreate() {
  errorMessage.value = ''
  noticeMessage.value = ''
  const values: Record<string, string> = {}
  for (const field of ['质控编号', '质控时段', '涉及站点']) {
    const input = window.prompt(`请输入${field}（必填）`)
    if (input === null) {
      return
    }
    values[field] = input.trim()
  }
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '质控任务登记未生效，请检查后重试')
    }
    noticeMessage.value = payload.message || '质控任务已登记'
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '质控任务登记失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  if (action === '详情') {
    await router.push(`/quality/${row.id}`)
    return
  }
  const values: Record<string, string> = { action }
  if (action === '退回重做') {
    const reason = window.prompt('请输入退回原因（必填）')
    if (reason === null) {
      return
    }
    if (!reason.trim()) {
      errorMessage.value = '退回原因不能为空'
      return
    }
    values['退回原因'] = reason.trim()
  }
  if (action === '确认完成') {
    const count = window.prompt('请输入本轮检出疑误数', '0')
    if (count === null) {
      return
    }
    if (!/^\d+$/.test(count.trim())) {
      errorMessage.value = '检出疑误数必须是非负整数'
      return
    }
    values['检出疑误数'] = count.trim()
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '数据质控动作未生效，请稍后重试')
    }
    noticeMessage.value = payload.message || `质控任务已${action}`
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '数据质控操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const [listResponse, statsResponse] = await Promise.all([
      request(`${ENDPOINT}?${query}`),
      request(`${ENDPOINT}/stats`),
    ])
    if (!listResponse.ok) {
      throw new Error('质控任务列表读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (statsResponse.ok) {
      const statsPayload = await statsResponse.json()
      stats.value = statsPayload.items ?? stats.value
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '数据质控列表读取失败'
  }
}

onMounted(reload)
</script>
