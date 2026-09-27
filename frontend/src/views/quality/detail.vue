<template>
  <section class="page" data-module="quality">
    <header class="page-head">
      <div>
        <h2>质控任务详情</h2>
        <p class="page-desc">查看单条质控任务的当前状态与每一轮质控记录，退回原因随轮次保留。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goBack">返回列表</button>
      </div>
    </header>

    <template v-if="entry">
      <table class="data-table detail-table">
        <tbody>
          <tr v-for="field in detailFields" :key="field">
            <th>{{ field }}</th>
            <td>
              <span v-if="field === '退回原因' && entry[field]" class="error-text">{{ entry[field] }}</span>
              <template v-else>{{ entry[field] ?? '—' }}</template>
            </td>
          </tr>
        </tbody>
      </table>

      <h3 class="section-title">质控轮次记录</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in roundColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="round in rounds" :key="String(round['轮次'])">
            <td v-for="column in roundColumns" :key="column">
              <span v-if="column === '退回原因' && round[column]" class="error-text">{{ round[column] }}</span>
              <template v-else>{{ round[column] ?? '—' }}</template>
            </td>
          </tr>
          <tr v-if="!rounds.length">
            <td :colspan="roundColumns.length" class="empty-state">尚未启动质控，启动后每一轮结果都会记录在这里</td>
          </tr>
        </tbody>
      </table>
    </template>

    <footer class="page-foot">
      <span v-if="entry">质控编号 {{ entry['质控编号'] }} · 当前第 {{ entry['当前轮次'] ?? 0 }} 轮</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/quality'
const detailFields = ["质控编号", "质控时段", "涉及站点", "质控规则", "质控状态", "当前轮次", "检出疑误数", "退回原因", "质控人员", "质控日期"]
const roundColumns = ["轮次", "状态", "检出疑误数", "退回原因", "质控人员", "启动时间", "完成时间"]

const route = useRoute()
const router = useRouter()

const entry = ref<Row | null>(null)
const rounds = ref<Row[]>([])
const errorMessage = ref('')

async function goBack() {
  await router.push('/quality')
}

async function loadDetail() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${route.params.id}`)
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload.detail || '质控任务详情读取失败')
    }
    entry.value = payload
    rounds.value = Array.isArray(payload.rounds) ? payload.rounds : []
  } catch (error) {
    entry.value = null
    errorMessage.value = error instanceof Error ? error.message : '质控任务详情读取失败'
  }
}

onMounted(loadDetail)
</script>

<style scoped>
.detail-table {
  margin-bottom: 16px;
}
.detail-table th {
  width: 140px;
  background: #f8fafc;
}
.section-title {
  font-size: 14px;
  margin: 0 0 8px;
}
</style>
