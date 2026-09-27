<template>
  <section class="page" data-module="quality-detail">
    <header class="page-head">
      <div>
        <h2>质控任务详情</h2>
        <p class="page-desc">查看单次质控任务的字段明细与逐轮执行台账，未跑完的任务可定位到具体轮次。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goBack">返回列表</button>
      </div>
    </header>

    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>

    <template v-if="entry">
      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">质控状态</span>
          <strong class="stat-value">{{ entry['质控状态'] ?? entry.status }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">当前轮次</span>
          <strong class="stat-value">第 {{ entry['当前轮次'] ?? 0 }} 轮</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">检出疑误数</span>
          <strong class="stat-value">{{ entry['检出疑误数'] ?? 0 }}</strong>
        </article>
      </div>

      <table class="data-table detail-table">
        <tbody>
          <tr v-for="field in detailFields" :key="field">
            <th>{{ field }}</th>
            <td>{{ displayValue(entry[field]) }}</td>
          </tr>
        </tbody>
      </table>

      <h3 class="section-title">质控轮次台账</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in roundColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="round in rounds" :key="String(round['轮次'])">
            <td v-for="column in roundColumns" :key="column">
              {{ column === '轮次' ? `第 ${round['轮次']} 轮` : displayValue(round[column]) }}
            </td>
          </tr>
          <tr v-if="!rounds.length">
            <td :colspan="roundColumns.length" class="empty-state">尚未启动质控，暂无轮次记录</td>
          </tr>
        </tbody>
      </table>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Entry = Record<string, string | number | null> & { rounds?: Array<Record<string, string | number | null>> }

const ENDPOINT = '/api/quality'
const detailFields = ['质控编号', '质控时段', '涉及站点', '质控规则', '质控人员', '质控日期', '退回原因']
const roundColumns = ['轮次', '状态', '启动时间', '完成时间', '检出疑误数', '退回原因', '质控人员']

const route = useRoute()
const router = useRouter()
const entry = ref<Entry | null>(null)
const errorMessage = ref('')

const rounds = computed(() => entry.value?.rounds ?? [])

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  return value
}

function goBack() {
  router.push('/quality')
}

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${route.params.id}`)
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload.detail ?? '质控任务明细读取失败')
    }
    entry.value = payload
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '质控任务明细读取失败'
  }
}

onMounted(reload)
</script>
