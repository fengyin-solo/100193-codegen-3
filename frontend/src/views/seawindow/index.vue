<template>
  <section class="page" data-module="seawindow">
    <header class="page-head">
      <div>
        <h2>出海窗口与船舶调度台账</h2>
        <p class="page-desc">按出海窗口登记海况等级、预计离岸时段、随船人员与作业船舶；海况升级标记窗口顺延并写明原因，窗口取消后船舶释放回可用池。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="toggleCreate">登记出海窗口</button>
        <button class="btn" type="button" @click="exportRows">导出窗口台账</button>
      </div>
    </header>

    <div class="stat-row">
      <article class="stat-card">
        <span class="stat-label">可用船舶</span>
        <strong class="stat-value">{{ fleetSummary['可用'] ?? 0 }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">占用中船舶</span>
        <strong class="stat-value">{{ fleetSummary['占用中'] ?? 0 }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">维保中船舶</span>
        <strong class="stat-value">{{ fleetSummary['维保中'] ?? 0 }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">占用中记录</span>
        <strong class="stat-value">{{ activeOccupancyCount }}</strong>
      </article>
    </div>

    <section v-if="showCreate" class="panel">
      <h3>登记出海窗口</h3>
      <form class="form-grid" @submit.prevent="submitCreate">
        <label class="form-item">
          <span>窗口编号 *</span>
          <input v-model="createForm.窗口编号" placeholder="如 SEA-0005" required />
        </label>
        <label class="form-item">
          <span>作业场站 *</span>
          <input v-model="createForm.作业场站" placeholder="如 青云海上风电场" required />
        </label>
        <label class="form-item">
          <span>海况等级 *</span>
          <select v-model="createForm.海况等级" required>
            <option value="" disabled>选择海况等级</option>
            <option v-for="level in seaLevels" :key="level" :value="level">{{ level }}</option>
          </select>
        </label>
        <label class="form-item">
          <span>预计离岸时段 *</span>
          <input v-model="createForm.预计离岸时段" placeholder="如 2026-10-05 06:00-10:00" required />
        </label>
        <label class="form-item wide">
          <span>随船人员（顿号或逗号分隔）</span>
          <input v-model="createForm.随船人员" placeholder="如 张海涛、李文斌" />
        </label>
        <div class="form-item wide">
          <span>作业船舶（从可用池选择，登记后到「提交占用」才锁定）</span>
          <div class="check-grid">
            <label v-for="code in availableVessels" :key="code" class="check-item">
              <input v-model="createForm.作业船舶" type="checkbox" :value="code" />
              {{ vesselLabel(code) }}
            </label>
            <span v-if="!availableVessels.length" class="muted">当前没有可用船舶</span>
          </div>
        </div>
        <div class="form-actions">
          <button class="btn primary" type="submit">提交登记</button>
          <button class="btn ghost" type="button" @click="toggleCreate">收起</button>
        </div>
      </form>
    </section>

    <section v-if="editForm.id" class="panel">
      <h3>编辑窗口 {{ editForm.窗口编号 }}（改动落库，重新打开或刷新读到的都是这份）</h3>
      <form class="form-grid" @submit.prevent="submitEdit">
        <label class="form-item">
          <span>海况等级</span>
          <select v-model="editForm.海况等级">
            <option v-for="level in seaLevels" :key="level" :value="level">{{ level }}</option>
          </select>
        </label>
        <label class="form-item">
          <span>预计离岸时段</span>
          <input v-model="editForm.预计离岸时段" />
        </label>
        <label class="form-item wide">
          <span>随船人员（顿号或逗号分隔）</span>
          <input v-model="editForm.随船人员" />
        </label>
        <div class="form-item wide">
          <span>作业船舶（本窗口已占用的船舶保持勾选）</span>
          <div class="check-grid">
            <label v-for="code in editVesselOptions" :key="code" class="check-item">
              <input v-model="editForm.作业船舶" type="checkbox" :value="code" />
              {{ vesselLabel(code) }}
            </label>
            <span v-if="!editVesselOptions.length" class="muted">当前没有可调整的船舶</span>
          </div>
        </div>
        <div class="form-actions">
          <button class="btn primary" type="submit">保存修改</button>
          <button class="btn ghost" type="button" @click="editForm.id = 0">取消编辑</button>
        </div>
      </form>
    </section>

    <section v-if="reasonForm.id" class="panel">
      <h3>{{ reasonForm.action === '海况升级' ? '海况升级：窗口标记为顺延' : '取消窗口' }}（{{ reasonForm.窗口编号 }}）</h3>
      <form class="form-grid" @submit.prevent="submitReason">
        <template v-if="reasonForm.action === '海况升级'">
          <label class="form-item">
            <span>升级后海况等级</span>
            <select v-model="reasonForm.海况等级">
              <option v-for="level in seaLevels" :key="level" :value="level">{{ level }}</option>
            </select>
          </label>
          <label class="form-item">
            <span>顺延后的预计离岸时段（可留空不变）</span>
            <input v-model="reasonForm.预计离岸时段" placeholder="如 2026-10-06 08:00-12:00" />
          </label>
          <label class="form-item wide">
            <span>顺延原因 *</span>
            <input v-model="reasonForm.原因" placeholder="如 海况由2级升至4级，阵风超过登乘作业阈值" required />
          </label>
        </template>
        <label v-else class="form-item wide">
          <span>取消原因（取消后占用释放，船舶回到可用池）</span>
          <input v-model="reasonForm.原因" placeholder="如 业主作业计划调整" />
        </label>
        <div class="form-actions">
          <button class="btn primary" type="submit">确认{{ reasonForm.action }}</button>
          <button class="btn ghost" type="button" @click="reasonForm.id = 0">返回</button>
        </div>
      </form>
    </section>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>窗口编号</span>
        <input v-model="filters.keyword" placeholder="按窗口编号检索" />
      </label>
      <label class="filter-item">
        <span>窗口状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
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
          <td>{{ row['窗口编号'] }}</td>
          <td>{{ row['作业场站'] }}</td>
          <td>{{ row['海况等级'] }}</td>
          <td>{{ row['预计离岸时段'] }}</td>
          <td>{{ joinNames(row['随船人员']) }}</td>
          <td>{{ joinNames(row['作业船舶']) }}</td>
          <td>{{ row['顺延原因'] || '—' }}</td>
          <td><span class="tag" :class="tagClass(String(row.status))">{{ row.status }}</span></td>
          <td class="row-actions">
            <template v-if="row.status === '待出海' || row.status === '窗口顺延'">
              <button class="link" type="button" @click="runAction('提交占用', row)">提交占用</button>
              <button class="link" type="button" @click="runAction('确认出海', row)">确认出海</button>
              <button class="link" type="button" @click="openReason('海况升级', row)">海况升级</button>
              <button class="link" type="button" @click="openEdit(row)">编辑名单</button>
              <button class="link" type="button" @click="openReason('取消窗口', row)">取消窗口</button>
            </template>
            <button v-else-if="row.status === '已出海'" class="link" type="button" @click="runAction('确认回港', row)">确认回港</button>
            <span v-else class="muted">—</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无出海窗口数据，可先登记出海窗口</td>
        </tr>
      </tbody>
    </table>

    <h3 class="section-title">作业船舶池（占用状态由占用记录推导，与看板同一口径）</h3>
    <table class="data-table">
      <thead>
        <tr><th>船舶编号</th><th>船舶名称</th><th>船舶类型</th><th>载员上限</th><th>所属单位</th><th>当前状态</th><th>占用窗口</th></tr>
      </thead>
      <tbody>
        <tr v-for="vessel in fleetRows" :key="String(vessel.id)">
          <td>{{ vessel['船舶编号'] }}</td>
          <td>{{ vessel['船舶名称'] }}</td>
          <td>{{ vessel['船舶类型'] }}</td>
          <td>{{ vessel['载员上限'] }}</td>
          <td>{{ vessel['所属单位'] }}</td>
          <td><span class="tag" :class="tagClass(String(vessel['当前状态']))">{{ vessel['当前状态'] }}</span></td>
          <td>{{ vessel['占用窗口'] || '—' }}</td>
        </tr>
      </tbody>
    </table>

    <h3 class="section-title">船舶占用记录（历史记录保留提交当时的船舶与名单）</h3>
    <table class="data-table">
      <thead>
        <tr><th>占用编号</th><th>窗口编号</th><th>作业船舶</th><th>随船人员</th><th>提交时间</th><th>占用状态</th><th>释放时间</th><th>释放原因</th></tr>
      </thead>
      <tbody>
        <tr v-for="record in occupancyRows" :key="String(record.id)">
          <td>{{ record['占用编号'] }}</td>
          <td>{{ record['窗口编号'] }}</td>
          <td>{{ joinNames(record['作业船舶']) }}</td>
          <td>{{ joinNames(record['随船人员']) }}</td>
          <td>{{ record['提交时间'] }}</td>
          <td><span class="tag" :class="tagClass(String(record.status))">{{ record.status }}</span></td>
          <td>{{ record['释放时间'] || '—' }}</td>
          <td>{{ record['释放原因'] || '—' }}</td>
        </tr>
        <tr v-if="!occupancyRows.length">
          <td colspan="8" class="empty-state">暂无占用记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条出海窗口记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, unknown>

const ENDPOINT = '/api/seawindow'
const columns = ['窗口编号', '作业场站', '海况等级', '预计离岸时段', '随船人员', '作业船舶', '顺延原因', '窗口状态']
const statuses = ['待出海', '已出海', '窗口顺延', '已完成', '已取消']
const seaLevels = ['1级（平静）', '2级（轻浪）', '3级（中浪）', '4级（大浪）', '5级（巨浪）']

const rows = ref<Row[]>([])
const total = ref(0)
const fleetRows = ref<Row[]>([])
const fleetSummary = ref<Record<string, number>>({})
const occupancyRows = ref<Row[]>([])
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref({ keyword: '', status: '' })
const showCreate = ref(false)

const createForm = ref({
  窗口编号: '',
  作业场站: '',
  海况等级: '',
  预计离岸时段: '',
  随船人员: '',
  作业船舶: [] as string[],
})

const editForm = ref({
  id: 0,
  窗口编号: '',
  海况等级: '',
  预计离岸时段: '',
  随船人员: '',
  作业船舶: [] as string[],
})

const reasonForm = ref({
  id: 0,
  action: '',
  窗口编号: '',
  原因: '',
  海况等级: '',
  预计离岸时段: '',
})

const activeOccupancyCount = computed(
  () => occupancyRows.value.filter((record) => record.status === '占用中').length,
)

const availableVessels = computed(() =>
  fleetRows.value
    .filter((vessel) => vessel['当前状态'] === '可用')
    .map((vessel) => String(vessel['船舶编号'])),
)

const editVesselOptions = computed(() =>
  fleetRows.value
    .filter(
      (vessel) => vessel['当前状态'] === '可用' || vessel['占用窗口'] === editForm.value.窗口编号,
    )
    .map((vessel) => String(vessel['船舶编号'])),
)

function asList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item))
  }
  return String(value ?? '').split(/[、,，]/).map((item) => item.trim()).filter(Boolean)
}

function joinNames(value: unknown): string {
  return asList(value).join('、') || '—'
}

function vesselLabel(code: string): string {
  const vessel = fleetRows.value.find((item) => item['船舶编号'] === code)
  return vessel ? `${code} ${vessel['船舶名称']}` : code
}

function tagClass(status: string): string {
  if (['窗口顺延', '维保中'].includes(status)) return 'warn'
  if (['已取消', '已释放'].includes(status)) return 'off'
  if (['已出海', '占用中'].includes(status)) return 'busy'
  return 'ok'
}

function toggleCreate() {
  showCreate.value = !showCreate.value
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function callApi(path: string, init?: RequestInit): Promise<{ ok: boolean; message: string }> {
  const response = await request(path, init)
  const payload = (await response.json()) as { ok?: boolean; message?: string; detail?: string }
  if (!response.ok) {
    throw new Error(payload.detail ?? `接口返回 ${response.status}`)
  }
  return { ok: payload.ok ?? false, message: payload.message ?? '' }
}

async function mutate(path: string, init: RequestInit) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const result = await callApi(path, init)
    if (!result.ok) {
      errorMessage.value = result.message
      return
    }
    noticeMessage.value = result.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '操作失败'
  }
}

async function submitCreate() {
  await mutate(ENDPOINT, {
    method: 'POST',
    body: JSON.stringify({ values: { ...createForm.value } }),
  })
  if (!errorMessage.value) {
    showCreate.value = false
    createForm.value = { 窗口编号: '', 作业场站: '', 海况等级: '', 预计离岸时段: '', 随船人员: '', 作业船舶: [] }
  }
}

function openEdit(row: Row) {
  editForm.value = {
    id: Number(row.id),
    窗口编号: String(row['窗口编号']),
    海况等级: String(row['海况等级'] ?? ''),
    预计离岸时段: String(row['预计离岸时段'] ?? ''),
    随船人员: asList(row['随船人员']).join('、'),
    作业船舶: asList(row['作业船舶']),
  }
}

async function submitEdit() {
  const { id, 海况等级, 预计离岸时段, 随船人员, 作业船舶 } = editForm.value
  await mutate(`${ENDPOINT}/${id}`, {
    method: 'PUT',
    body: JSON.stringify({ values: { 海况等级, 预计离岸时段, 随船人员, 作业船舶 } }),
  })
  if (!errorMessage.value) {
    editForm.value.id = 0
  }
}

function openReason(action: string, row: Row) {
  reasonForm.value = {
    id: Number(row.id),
    action,
    窗口编号: String(row['窗口编号']),
    原因: '',
    海况等级: String(row['海况等级'] ?? ''),
    预计离岸时段: '',
  }
}

async function submitReason() {
  const { id, action, 原因, 海况等级, 预计离岸时段 } = reasonForm.value
  const values: Record<string, string> =
    action === '海况升级'
      ? { action, 顺延原因: 原因, 海况等级, 预计离岸时段 }
      : { action, 取消原因: 原因 }
  await mutate(`${ENDPOINT}/${id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  if (!errorMessage.value) {
    reasonForm.value.id = 0
  }
}

async function runAction(action: string, row: Row) {
  await mutate(`${ENDPOINT}/${row.id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ values: { action } }),
  })
}

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void reload()
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.keyword) query.set('keyword', filters.value.keyword)
  if (filters.value.status) query.set('status', filters.value.status)
  try {
    const [listResponse, fleetResponse, occupancyResponse] = await Promise.all([
      request(`${ENDPOINT}?${query.toString()}`),
      request(`${ENDPOINT}/fleet`),
      request(`${ENDPOINT}/occupancies`),
    ])
    if (!listResponse.ok || !fleetResponse.ok || !occupancyResponse.ok) {
      throw new Error('出海窗口台账读取失败')
    }
    const listPayload = (await listResponse.json()) as { items?: Row[]; total?: number }
    const fleetPayload = (await fleetResponse.json()) as { summary?: Record<string, number>; items?: Row[] }
    const occupancyPayload = (await occupancyResponse.json()) as { items?: Row[] }
    rows.value = listPayload.items ?? []
    total.value = listPayload.total ?? rows.value.length
    fleetSummary.value = fleetPayload.summary ?? {}
    fleetRows.value = fleetPayload.items ?? []
    occupancyRows.value = occupancyPayload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '出海窗口台账读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 12px;
}
.panel h3 {
  margin: 0 0 10px;
  font-size: 14px;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 16px;
}
.form-item span {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}
.form-item input,
.form-item select,
.filter-item select {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
}
.form-item.wide {
  grid-column: 1 / -1;
}
.check-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
}
.check-item {
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.form-actions {
  grid-column: 1 / -1;
  display: flex;
  gap: 8px;
}
.section-title {
  font-size: 14px;
  margin: 16px 0 8px;
}
.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  background: #e8f0fe;
  color: #1f6feb;
}
.tag.warn {
  background: #fef3e2;
  color: #b45309;
}
.tag.off {
  background: #f1f5f9;
  color: #64748b;
}
.tag.busy {
  background: #e6f6ec;
  color: #15803d;
}
.muted {
  color: var(--muted);
  font-size: 13px;
}
.notice-text {
  color: #15803d;
}
</style>
