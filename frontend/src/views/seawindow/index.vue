<template>
  <section class="page" data-module="seawindow">
    <header class="page-head">
      <div>
        <h2>出海窗口与船舶调度台账</h2>
        <p class="page-desc">按出海窗口登记海况等级、预计离岸时段、随船人员与作业船舶；海况升级时标记窗口顺延并写明原因，取消窗口自动释放占用船舶。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记出海窗口</button>
        <button class="btn" type="button" @click="exportRows">导出台账</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>窗口编号</span>
        <input v-model="filters.keyword" placeholder="按窗口编号检索" />
      </label>
      <label class="filter-item">
        <span>窗口状态</span>
        <select v-model="filters.status">
          <option value="">全部</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <h3 class="block-title">窗口台账</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>窗口状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td><span :class="['status-tag', statusClass(String(row.status))]">{{ row.status }}</span></td>
          <td class="row-actions">
            <template v-if="row.status !== '已取消'">
              <button class="link" type="button" @click="openCrew(row)">更新人员</button>
              <button class="link" type="button" @click="openPostpone(row)">海况升级顺延</button>
              <button class="link" type="button" @click="openAssign(row)">更换船舶</button>
              <button class="link danger" type="button" @click="cancelWindow(row)">取消窗口</button>
            </template>
            <span v-else class="muted-text">已关闭</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无出海窗口记录，可先登记一个出海窗口</td>
        </tr>
      </tbody>
    </table>

    <h3 class="block-title">船舶可用池</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in vesselColumns" :key="column">{{ column }}</th>
          <th>调度状态</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="vessel in vessels" :key="String(vessel.id)">
          <td v-for="column in vesselColumns" :key="column">{{ vessel[column] ?? '—' }}</td>
          <td>
            <span :class="['status-tag', vessel.status === '可用' ? 'tag-ok' : 'tag-busy']">
              {{ vessel.status }}<template v-if="vessel.占用窗口">（{{ vessel.占用窗口 }}）</template>
            </span>
          </td>
        </tr>
        <tr v-if="!vessels.length">
          <td :colspan="vesselColumns.length + 1" class="empty-state">船舶池暂无数据</td>
        </tr>
      </tbody>
    </table>

    <h3 class="block-title">占用历史（按当时口径保留）</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in occColumns" :key="column">{{ column }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="occ in occupancies" :key="String(occ.id)">
          <td v-for="column in occColumns" :key="column">
            <span :class="column === 'record_status' ? ['status-tag', occ.record_status === '占用中' ? 'tag-busy' : 'tag-idle'] : ''">
              {{ occ[column] ?? '—' }}
            </span>
          </td>
        </tr>
        <tr v-if="!occupancies.length">
          <td :colspan="occColumns.length" class="empty-state">暂无占用记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条出海窗口记录 · 所有操作直接落库，刷新后以服务端名单与船态为准</span>
      <span v-if="message" :class="messageOk ? 'ok-text' : 'error-text'">{{ message }}</span>
    </footer>

    <div v-if="modal !== ''" class="modal-mask" @click.self="closeModal">
      <div class="modal-box">
        <h3 class="modal-title">{{ modalTitle }}</h3>

        <template v-if="modal === 'create'">
          <label class="form-item"><span>窗口编号 *</span><input v-model="form.窗口编号" placeholder="如 SW-20261001-05" /></label>
          <label class="form-item"><span>海况等级 *（1-9 级）</span><input v-model.number="form.海况等级" type="number" min="1" max="9" placeholder="如 3" /></label>
          <label class="form-item"><span>预计离岸时段 *</span><input v-model="form.预计离岸时段" placeholder="如 2026-10-02 06:00-10:00" /></label>
          <label class="form-item"><span>随船人员 *（顿号/逗号分隔）</span><input v-model="form.随船人员" placeholder="如 张伟、李娜" /></label>
          <label class="form-item">
            <span>作业船舶 *</span>
            <select v-model="form.船舶编号">
              <option value="" disabled>请选择可用船舶</option>
              <option v-for="v in availableVessels" :key="String(v.id)" :value="v.船舶编号">
                {{ v.船舶编号 }} {{ v.船舶名称 }}（{{ v.船舶类型 }}）
              </option>
            </select>
          </label>
        </template>

        <template v-else-if="modal === 'crew'">
          <p class="modal-hint">窗口 {{ activeRow?.['窗口编号'] }} 当前名单：{{ activeRow?.['随船人员'] }}</p>
          <label class="form-item"><span>最新随船人员名单 *</span><input v-model="form.随船人员" placeholder="顿号/逗号分隔" /></label>
        </template>

        <template v-else-if="modal === 'postpone'">
          <p class="modal-hint">窗口 {{ activeRow?.['窗口编号'] }} 当前海况 {{ activeRow?.['海况等级'] }} 级，升级后标记为「窗口顺延」，船舶继续占用。</p>
          <label class="form-item"><span>升级后海况等级 *（高于当前）</span><input v-model.number="form.海况等级" type="number" min="1" max="9" /></label>
          <label class="form-item"><span>顺延原因 *</span><textarea v-model="form.顺延原因" rows="3" placeholder="如 东北涌浪增强，超过交通艇作业限值"></textarea></label>
        </template>

        <template v-else-if="modal === 'assign'">
          <p class="modal-hint">为窗口 {{ activeRow?.['窗口编号'] }} 登记/更换作业船舶；同船重复提交只保留一条占用记录。</p>
          <label class="form-item">
            <span>作业船舶 *</span>
            <select v-model="form.船舶编号">
              <option value="" disabled>请选择船舶</option>
              <option v-for="v in assignableVessels" :key="String(v.id)" :value="v.船舶编号">
                {{ v.船舶编号 }} {{ v.船舶名称 }}（{{ v.status }}<template v-if="v.占用窗口"> · {{ v.占用窗口 }}</template>）
              </option>
            </select>
          </label>
        </template>

        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeModal">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitModal">
            {{ submitting ? '提交中…' : '确认提交' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type Vessel = Row & { status?: string, 占用窗口?: string }
type Summary = Record<string, number>

const ENDPOINT = '/api/seawindow'
const columns = ['窗口编号', '海况等级', '预计离岸时段', '随船人员', '作业船舶', '顺延原因']
const vesselColumns = ['船舶编号', '船舶名称', '船舶类型', '核定载客', '所属单位']
const occColumns = ['窗口编号', '船舶编号', '船舶名称', '随船人员快照', '海况等级快照', '占用时间', '释放时间', 'record_status']
const statuses = ['计划中', '窗口顺延', '已取消']

const rows = ref<Row[]>([])
const vessels = ref<Vessel[]>([])
const occupancies = ref<Row[]>([])
const total = ref(0)
const summary = ref<Summary>({})
const message = ref('')
const messageOk = ref(true)
const submitting = ref(false)
const filters = reactive({ keyword: '', status: '' })

const modal = ref('')
const activeRow = ref<Row | null>(null)
const form = reactive<Record<string, string | number>>({})

const statCards = computed(() => [
  { label: '船舶总数', value: summary.value['船舶总数'] ?? 0 },
  { label: '可用船舶', value: summary.value['可用船舶'] ?? 0 },
  { label: '占用船舶', value: summary.value['占用船舶'] ?? 0 },
  { label: '窗口总数', value: summary.value['窗口总数'] ?? 0 },
  { label: '计划中', value: summary.value['计划中'] ?? 0 },
  { label: '窗口顺延', value: summary.value['窗口顺延'] ?? 0 },
  { label: '已取消', value: summary.value['已取消'] ?? 0 },
])

const availableVessels = computed(() => vessels.value.filter((v) => v.status === '可用'))
// 换船时允许选本窗口已占用的船（幂等）与可用船；被别的窗口占用的船不出现，避免冲突提交。
const assignableVessels = computed(() =>
  vessels.value.filter(
    (v) => v.status === '可用' || v.占用窗口 === String(activeRow.value?.['窗口编号'] ?? ''),
  ),
)

const modalTitle = computed(() => ({
  create: '登记出海窗口',
  crew: '更新随船人员',
  postpone: '海况升级 · 窗口顺延',
  assign: '登记/更换作业船舶',
}[modal.value] ?? ''))

function statusClass(status: string) {
  if (status === '已取消') return 'tag-idle'
  if (status === '窗口顺延') return 'tag-warn'
  return 'tag-ok'
}

function notify(text: string, ok = true) {
  message.value = text
  messageOk.value = ok
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

// 每次打开/提交后都整体从服务端拉取：页面不保留本地状态副本，重开或刷新读到的就是落库数据。
async function reload() {
  message.value = ''
  const query = new URLSearchParams()
  if (filters.keyword) query.set('keyword', filters.keyword)
  if (filters.status) query.set('status', filters.status)
  query.set('size', '200')
  try {
    const [winRes, vesselRes, occRes, sumRes] = await Promise.all([
      request(`${ENDPOINT}?${query.toString()}`),
      request(`${ENDPOINT}/vessels`),
      request(`${ENDPOINT}/occupancies`),
      request(`${ENDPOINT}/summary`),
    ])
    if (!winRes.ok || !vesselRes.ok || !occRes.ok || !sumRes.ok) {
      throw new Error('台账数据读取失败')
    }
    const [winPayload, vesselPayload, occPayload, sumPayload] = await Promise.all([
      winRes.json(), vesselRes.json(), occRes.json(), sumRes.json(),
    ])
    rows.value = winPayload.items ?? []
    total.value = winPayload.total ?? rows.value.length
    vessels.value = vesselPayload.items ?? []
    occupancies.value = occPayload.items ?? []
    summary.value = sumPayload
  } catch (error) {
    notify(error instanceof Error ? error.message : '出海窗口台账读取失败', false)
  }
}

function openCreate() {
  modal.value = 'create'
  activeRow.value = null
  Object.assign(form, { 窗口编号: '', 海况等级: 3, 预计离岸时段: '', 随船人员: '', 船舶编号: '' })
}

function openCrew(row: Row) {
  modal.value = 'crew'
  activeRow.value = row
  Object.assign(form, { 随船人员: String(row['随船人员'] ?? '') })
}

function openPostpone(row: Row) {
  modal.value = 'postpone'
  activeRow.value = row
  Object.assign(form, { 海况等级: Number(row['海况等级']) + 1, 顺延原因: '' })
}

function openAssign(row: Row) {
  modal.value = 'assign'
  activeRow.value = row
  Object.assign(form, { 船舶编号: String(row['船舶编号'] ?? '') })
}

function closeModal() {
  modal.value = ''
  activeRow.value = null
}

async function submitModal() {
  if (!activeRow.value && modal.value !== 'create') return
  submitting.value = true
  try {
    if (modal.value === 'create') {
      await postJson(ENDPOINT, {
        values: {
          窗口编号: form.窗口编号,
          海况等级: form.海况等级,
          预计离岸时段: form.预计离岸时段,
          随船人员: form.随船人员,
          船舶编号: form.船舶编号,
        },
      }, true)
    } else {
      const id = activeRow.value?.id
      const values: Record<string, unknown> = {}
      if (modal.value === 'crew') {
        values.action = '更新人员'
        values.随船人员 = form.随船人员
      } else if (modal.value === 'postpone') {
        values.action = '海况升级顺延'
        values.海况等级 = form.海况等级
        values.顺延原因 = form.顺延原因
      } else if (modal.value === 'assign') {
        values.action = '登记船舶占用'
        values.船舶编号 = form.船舶编号
      }
      await postJson(`${ENDPOINT}/${id}/actions`, { values }, true)
    }
    closeModal()
    await reload()
  } catch (error) {
    notify(error instanceof Error ? error.message : '操作失败', false)
  } finally {
    submitting.value = false
  }
}

async function cancelWindow(row: Row) {
  if (!window.confirm(`确认取消窗口 ${String(row['窗口编号'])}？取消后其占用的船舶将立即释放回可用池。`)) {
    return
  }
  try {
    await postJson(`${ENDPOINT}/${row.id}/actions`, { values: { action: '取消窗口' } })
    await reload()
  } catch (error) {
    notify(error instanceof Error ? error.message : '取消窗口失败', false)
  }
}

async function postJson(path: string, body: unknown, throwOnFail = false) {
  const response = await request(path, { method: 'POST', body: JSON.stringify(body) })
  const payload = await response.json().catch(() => null)
  if (!response.ok || payload?.ok === false) {
    const text = payload?.message ?? '操作未生效，请稍后重试'
    notify(text, false)
    if (throwOnFail) throw new Error(text)
    return null
  }
  notify(payload?.message ?? '操作已生效', true)
  return payload
}

onMounted(reload)
</script>
