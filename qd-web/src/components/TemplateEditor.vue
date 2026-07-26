<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useMessage } from 'naive-ui'
import api from '@/api'

interface HARHeader {
  name: string
  value: string
}
interface RequestCondition {
  type: string
  operator: string
  value: string
  outcome: string
}
interface HARRequestData {
  method: string
  url: string
  headers: HARHeader[]
  extractors: Record<string, string>
  _bodyType: string
  _bodyContent: string
  _conditions: RequestCondition[]
  _testing: boolean
  _lastResponse: any
  _comment: string
  _selected: boolean
  _cookies: string
  _conditionResults: any[]
}

const message = useMessage()
const props = defineProps<{ initialData?: any }>()

const rawTplData = props.initialData?.template_data
const initialRequests =
  props.initialData?.requests ||
  (Array.isArray(rawTplData)
    ? rawTplData.map((e: any) => ({ ...(e.request || {}), ...ruleToLegacy(e.rule) }))
    : rawTplData?.requests) ||
  []

function ruleToLegacy(rule: any) {
  if (!rule) return {}
  return {
    success_asserts: rule.success_asserts,
    failed_asserts: rule.failed_asserts,
    extract_variables: rule.extract_variables,
  }
}

const template = reactive({
  name: props.initialData?.name || '',
  description: props.initialData?.description || '',
  tags: props.initialData?.tags || [],
  is_public: props.initialData?.is_public || false,
  variables: props.initialData?.variables || {},
  requests: initialRequests.map((r: any) => parseRequestData(r)),
})

function parseRequestData(r: any): HARRequestData {
  const req: HARRequestData = {
    method: r.method || 'GET',
    url: r.url || '',
    headers: r.headers || [],
    extractors: r.extractors || {},
    _bodyType: r.postData ? 'json' : 'none',
    _bodyContent: r.postData?.text || r.data || '',
    _conditions: r._conditions || [],
    _testing: false,
    _lastResponse: null,
    _comment: r._comment || r.comment || '',
    _selected: false,
    _cookies: '',
    _conditionResults: [],
  }
  // QD v1 rule → conditions
  if (r.success_asserts) {
    for (const a of r.success_asserts) {
      req._conditions.push({
        type: a.from === 'status' ? 'status_code' : 'body_contains',
        operator: 'matches',
        value: a.re || '',
        outcome: 'success',
      })
    }
  }
  if (r.failed_asserts) {
    for (const a of r.failed_asserts) {
      req._conditions.push({
        type: a.from === 'status' ? 'status_code' : 'body_contains',
        operator: 'matches',
        value: a.re || '',
        outcome: 'failure',
      })
    }
  }
  if (r.extract_variables) {
    for (const ext of r.extract_variables) {
      if (ext.name && ext.re) req.extractors[ext.name] = `regex:${ext.re}`
    }
  }
  return req
}

// --- Variables ---
const variableList = ref(
  Object.entries(template.variables).map(([key, value]) => ({ key, value: String(value) }))
)
function addVariable() {
  variableList.value.push({ key: '', value: '' })
}
function removeVariable(i: number) {
  variableList.value.splice(i, 1)
}

// --- Requests list ---
const selectedCount = computed(() => template.requests.filter((r: HARRequestData) => r._selected).length)

function methodType(method: string): any {
  const m: Record<string, string> = {
    GET: 'success',
    POST: 'warning',
    PUT: 'info',
    DELETE: 'error',
    PATCH: 'warning',
  }
  return m[method] || 'default'
}

function addRequest() {
  const req: HARRequestData = {
    method: 'GET',
    url: '',
    headers: [],
    extractors: {},
    _bodyType: 'none',
    _bodyContent: '',
    _conditions: [],
    _testing: false,
    _lastResponse: null,
    _comment: '',
    _selected: false,
    _cookies: '',
    _conditionResults: [],
  }
  template.requests.push(req)
  openDetail(req)
}

function addRequestsFromParsed(parsedList: any[]) {
  for (const p of parsedList) {
    const headers = Object.entries(p.headers || {}).map(([name, value]) => ({
      name,
      value: String(value),
    }))
    const extractors: Record<string, string> = {}
    if (p.extract_variables) {
      for (const ext of p.extract_variables) {
        if (ext.name && ext.re) extractors[ext.name] = `regex:${ext.re}`
      }
    }
    const conditions: any[] = []
    if (p.success_asserts) {
      for (const a of p.success_asserts) {
        conditions.push({
          type: a.from === 'status' ? 'status_code' : 'body_contains',
          operator: 'matches',
          value: a.re || '',
          outcome: 'success',
        })
      }
    }
    if (p.failed_asserts) {
      for (const a of p.failed_asserts) {
        conditions.push({
          type: a.from === 'status' ? 'status_code' : 'body_contains',
          operator: 'matches',
          value: a.re || '',
          outcome: 'failure',
        })
      }
    }
    template.requests.push({
      method: p.method || 'GET',
      url: p.url || '',
      headers,
      extractors,
      _bodyType: p.body_type || 'none',
      _bodyContent: p.body || '',
      _conditions: conditions,
      _testing: false,
      _lastResponse: null,
      _comment: p.name || '',
      _selected: false,
      _cookies: '',
      _conditionResults: [],
    })
  }
}

function removeRequest(index: number) {
  template.requests.splice(index, 1)
}
function deleteSelected() {
  template.requests = template.requests.filter((r: HARRequestData) => !r._selected)
}

// --- Detail ---
const showDetail = ref(false)
const detailRequest = ref<HARRequestData | null>(null)
const detailTab = ref('request')
const responseViewMode = ref<'render' | 'source'>('render')

function openDetail(row: HARRequestData) {
  detailRequest.value = row
  detailTab.value = 'request'
  responseViewMode.value = 'render'
  showDetail.value = true
}

const responseContentType = computed(() => {
  if (!detailRequest.value?._lastResponse) return ''
  const ct = detailRequest.value._lastResponse.headers?.['content-type'] || ''
  if (ct.includes('json')) return 'JSON'
  if (ct.includes('html')) return 'HTML'
  return ct.split(';')[0] || 'Text'
})
const isHtmlResponse = computed(() => responseContentType.value === 'HTML')
const isJsonResponse = computed(() => responseContentType.value === 'JSON')

function addHeader(req: HARRequestData) {
  req.headers.push({ name: '', value: '' })
}
function removeHeader(req: HARRequestData, idx: number) {
  req.headers.splice(idx, 1)
}

// --- Conditions ---
const successConditionIdxs = computed(() => {
  if (!detailRequest.value) return []
  return (detailRequest.value._conditions || [])
    .map((c: any, i: number) => ({ idx: i, outcome: c.outcome }))
    .filter((c) => c.outcome === 'success')
})
const failConditionIdxs = computed(() => {
  if (!detailRequest.value) return []
  return (detailRequest.value._conditions || [])
    .map((c: any, i: number) => ({ idx: i, outcome: c.outcome }))
    .filter((c) => c.outcome === 'failure')
})

function addCondition(outcome: string) {
  if (!detailRequest.value) return
  if (!detailRequest.value._conditions) detailRequest.value._conditions = []
  detailRequest.value._conditions.push({
    type: outcome === 'success' ? 'status_code' : 'body_contains',
    operator: 'matches',
    value: outcome === 'success' ? '200' : '',
    outcome,
  })
}
function removeCondition(idx: number) {
  detailRequest.value?._conditions.splice(idx, 1)
}

function evaluateCondition(condition: any, response: any): boolean {
  if (!response || response.error) return false
  let actual: any = null
  switch (condition.type) {
    case 'status_code':
      actual = response.status_code
      break
    case 'body_contains':
      actual = response.body
      break
    case 'header_contains':
      actual = Object.entries(response.headers || {})
        .map(([k, v]) => `${k}: ${v}`)
        .join('\n')
      break
  }
  try {
    return new RegExp(condition.value).test(String(actual))
  } catch {
    return String(actual).includes(String(condition.value))
  }
}

function evaluateConditions(req: HARRequestData) {
  const response = req._lastResponse
  if (!response) return
  req._conditionResults = (req._conditions || []).map((c: any) => {
    const matched = evaluateCondition(c, response)
    return { ...c, matched, isPass: (c.outcome === 'success' && matched) || (c.outcome === 'failure' && !matched) }
  })
}

// --- Extractors ---
function getExtractorList(req: HARRequestData) {
  if (!(req as any)._extractorList) {
    ;(req as any)._extractorList = Object.entries(req.extractors || {}).map(([key, value]) => {
      let source = 'content'
      let pattern = String(value)
      if (pattern.startsWith('regex:')) {
        source = 'content'
        pattern = pattern.slice(6)
      } else if (pattern.startsWith('header:')) {
        source = 'header'
        pattern = pattern.slice(7)
      } else if (pattern === 'status') {
        source = 'status'
      }
      return { key, value: pattern, source }
    })
  }
  return (req as any)._extractorList
}
function addExtractor(req: HARRequestData) {
  getExtractorList(req).push({ key: '', value: '', source: 'content' })
}
function removeExtractor(req: HARRequestData, idx: number) {
  getExtractorList(req).splice(idx, 1)
}

function extractValue(response: any, expression: string, source?: string): any {
  if (!response || !expression) return null
  try {
    let searchText = response.body
    if (source === 'status') return response.status_code
    if (source === 'header' || source === 'header-location') {
      searchText = Object.entries(response.headers || {})
        .map(([k, v]) => `${k}: ${v}`)
        .join('\n')
    }
    const match = searchText.match(new RegExp(expression))
    return match ? match[1] || match[0] : null
  } catch {
    return null
  }
}

// --- Test ---
async function testRequest(req: HARRequestData) {
  if (!req.url) {
    message.warning('请输入请求 URL')
    return
  }
  req._testing = true
  req._lastResponse = null
  try {
    const headers: Record<string, string> = {}
    for (const h of req.headers) {
      if (h.name) headers[h.name] = h.value
    }
    const res = await api.post('/api/test/test', {
      method: req.method,
      url: req.url,
      headers,
      body: req._bodyType !== 'none' ? req._bodyContent : null,
      body_type: req._bodyType,
      timeout: 30,
    })
    req._lastResponse = res.data
    evaluateConditions(req)
    if (detailRequest.value === req) detailTab.value = 'preview'
    message.success(`${res.data.status_code} - ${res.data.elapsed_ms.toFixed(0)}ms`)
  } catch (err: any) {
    message.error('请求测试失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    req._testing = false
  }
}

function formatResponseBody(body: string) {
  try {
    return JSON.stringify(JSON.parse(body), null, 2)
  } catch {
    return body
  }
}

// --- HAR import ---
async function handleHarUpload(options: any) {
  const file = options.file.file as File
  const reader = new FileReader()
  reader.onload = async (e) => {
    try {
      const res = await api.post('/api/test/parse-har', { har_content: e.target?.result as string })
      if (res.data.length === 0) {
        message.warning('HAR 文件中没有找到请求')
        return
      }
      addRequestsFromParsed(res.data)
      message.success(`已追加 ${res.data.length} 个请求`)
    } catch (err: any) {
      message.error('HAR 解析失败: ' + (err.response?.data?.detail || err.message))
    }
  }
  reader.readAsText(file)
}

// --- cURL ---
const showCurlDialog = ref(false)
const curlInput = ref('')
const curlParsing = ref(false)
async function importCurl() {
  if (!curlInput.value.trim()) {
    message.warning('请输入 cURL 命令')
    return
  }
  curlParsing.value = true
  try {
    const res = await api.post('/api/test/parse-curl', { curl_command: curlInput.value })
    addRequestsFromParsed([res.data])
    showCurlDialog.value = false
    curlInput.value = ''
    message.success('cURL 已追加')
  } catch (err: any) {
    message.error('cURL 解析失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    curlParsing.value = false
  }
}

// --- getData ---
function getData(): any {
  const vars: Record<string, string> = {}
  for (const v of variableList.value) {
    if (v.key) vars[v.key] = v.value
  }
  return {
    name: template.name,
    description: template.description,
    tags: template.tags,
    is_public: template.is_public,
    variables: vars,
    template_data: {
      name: template.name,
      description: template.description,
      requests: template.requests.map((r: any) => ({
        method: r.method,
        url: r.url,
        _comment: r._comment,
        headers: r.headers.filter((h: HARHeader) => h.name),
        postData:
          r._bodyType !== 'none' ? { mimeType: 'application/json', text: r._bodyContent } : undefined,
        extractors:
          ((r as any)._extractorList || []).reduce((acc: any, e: any) => {
            if (e.key) acc[e.key] = e.source === 'header' ? `header:${e.value}` : e.source === 'status' ? 'status' : `regex:${e.value}`
            return acc
          }, {}) || r.extractors,
        _conditions: r._conditions || [],
        // QD v1 compatible rule block
        rule: {
          success_asserts: (r._conditions || [])
            .filter((c: any) => c.outcome === 'success')
            .map((c: any) => ({ re: c.value, from: c.type === 'status_code' ? 'status' : 'content' })),
          failed_asserts: (r._conditions || [])
            .filter((c: any) => c.outcome === 'failure')
            .map((c: any) => ({ re: c.value, from: c.type === 'status_code' ? 'status' : 'content' })),
          extract_variables: ((r as any)._extractorList || [])
            .filter((e: any) => e.key && e.source !== 'status')
            .map((e: any) => ({
              name: e.key,
              re: e.value,
              from: e.source === 'header' ? 'header' : 'content',
            })),
        },
      })),
    },
  }
}
defineExpose({ getData })

const methodOptions = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'].map((m) => ({ label: m, value: m }))
const condTypeOptions = [
  { label: 'status', value: 'status_code' },
  { label: 'content', value: 'body_contains' },
  { label: 'header', value: 'header_contains' },
]
const extractorSourceOptions = [
  { label: 'content', value: 'content' },
  { label: 'status', value: 'status' },
  { label: 'header', value: 'header' },
]
</script>

<template>
  <div>
    <!-- Basic info -->
    <n-card size="small" title="模板信息" class="rounded-lg mb-3">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        <n-form-item label="名称" :show-feedback="false" label-placement="left">
          <n-input v-model:value="template.name" placeholder="模板名称" />
        </n-form-item>
        <n-form-item label="标签" :show-feedback="false" label-placement="left">
          <n-dynamic-tags v-model:value="template.tags" />
        </n-form-item>
      </div>
      <n-form-item label="描述" :show-feedback="false" label-placement="left" class="mt-2">
        <n-input v-model:value="template.description" type="textarea" :rows="2" />
      </n-form-item>
      <n-form-item label="公开" :show-feedback="false" label-placement="left" class="mt-2">
        <n-switch v-model:value="template.is_public" />
      </n-form-item>
    </n-card>

    <!-- Variables -->
    <n-card size="small" class="rounded-lg mb-3">
      <template #header>
        <div class="flex justify-between items-center">
          <span>模板变量</span>
          <n-button size="tiny" @click="addVariable">+ 添加变量</n-button>
        </div>
      </template>
      <n-empty v-if="variableList.length === 0" description="暂无变量" size="small" />
      <div v-for="(v, i) in variableList" :key="i" class="flex gap-2 mb-2 items-center">
        <n-input v-model:value="v.key" size="small" placeholder="variable_name" class="w-48" />
        <span class="text-gray-400">=</span>
        <n-input v-model:value="v.value" size="small" placeholder="默认值" class="flex-1" />
        <n-button size="tiny" quaternary type="error" @click="removeVariable(i)">✕</n-button>
      </div>
    </n-card>

    <!-- Requests -->
    <n-card size="small" class="rounded-lg">
      <template #header>
        <div class="flex justify-between items-center flex-wrap gap-2">
          <div class="flex items-center gap-2">
            <span>请求列表</span>
            <n-tag size="small" round>{{ template.requests.length }}</n-tag>
            <n-button v-if="selectedCount > 0" size="tiny" quaternary type="error" @click="deleteSelected">
              删除选中 ({{ selectedCount }})
            </n-button>
          </div>
          <div class="flex gap-2">
            <n-upload :show-file-list="false" accept=".har,.json" :custom-request="handleHarUpload">
              <n-button size="tiny">📥 追加HAR</n-button>
            </n-upload>
            <n-button size="tiny" @click="showCurlDialog = true">📋 追加cURL</n-button>
            <n-button size="tiny" type="primary" @click="addRequest">+ 添加请求</n-button>
          </div>
        </div>
      </template>

      <n-empty v-if="template.requests.length === 0" description="暂无请求" size="small" />
      <n-table v-else size="small" :bordered="false">
        <thead>
          <tr>
            <th class="w-8"></th>
            <th class="w-10">#</th>
            <th class="w-20">方法</th>
            <th>URL</th>
            <th class="w-28">备注</th>
            <th class="w-24">状态</th>
            <th class="w-32 !text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in template.requests" :key="i" class="cursor-pointer" @click="openDetail(row)">
            <td @click.stop>
              <n-checkbox v-model:checked="row._selected" />
            </td>
            <td>{{ i + 1 }}</td>
            <td>
              <n-tag :type="methodType(row.method)" size="tiny" round>{{ row.method }}</n-tag>
            </td>
            <td class="font-mono text-xs max-w-96 truncate" :title="row.url">{{ row.url || '(未设置)' }}</td>
            <td class="text-xs text-gray-400 truncate">{{ row._comment || '-' }}</td>
            <td>
              <template v-if="row._lastResponse">
                <n-tag
                  :type="row._lastResponse.error ? 'error' : row._lastResponse.status_code < 300 ? 'success' : 'warning'"
                  size="tiny"
                >
                  {{ row._lastResponse.error ? 'ERR' : row._lastResponse.status_code }}
                </n-tag>
              </template>
              <span v-else class="text-gray-300 text-xs">未测试</span>
            </td>
            <td class="!text-right" @click.stop>
              <n-button size="tiny" quaternary type="primary" :loading="row._testing" @click="testRequest(row)">
                测试
              </n-button>
              <n-button size="tiny" quaternary type="error" @click="removeRequest(i)">删除</n-button>
            </td>
          </tr>
        </tbody>
      </n-table>
    </n-card>

    <!-- Detail modal -->
    <n-modal
      v-model:show="showDetail"
      preset="card"
      :title="detailRequest ? `${detailRequest.method} ${detailRequest.url || '(新请求)'}` : ''"
      class="max-w-5xl"
      :style="{ width: '94vw' }"
    >
      <div v-if="detailRequest">
        <div class="flex items-center gap-2 mb-3">
          <span class="text-sm text-gray-400 whitespace-nowrap">备注:</span>
          <n-input v-model:value="detailRequest._comment" size="small" placeholder="请求备注" class="max-w-md" />
          <div class="flex-1" />
          <n-button size="small" type="primary" :loading="detailRequest._testing" @click="testRequest(detailRequest)">
            ▶ 测试
          </n-button>
        </div>

        <n-tabs v-model:value="detailTab" type="line" size="small">
          <!-- Request -->
          <n-tab-pane name="request" tab="请求">
            <div class="flex gap-2 mb-3">
              <n-select v-model:value="detailRequest.method" :options="methodOptions" class="w-28" size="small" />
              <n-input v-model:value="detailRequest.url" size="small" placeholder="https://example.com/api（支持 {{var}}）" />
            </div>
            <div class="flex justify-between items-center mb-1">
              <span class="text-sm font-medium">Request Headers</span>
              <n-button size="tiny" @click="addHeader(detailRequest!)">+ Add</n-button>
            </div>
            <div v-for="(h, idx) in detailRequest.headers" :key="idx" class="flex gap-2 mb-1">
              <n-input v-model:value="h.name" size="small" placeholder="Header-Name" class="w-56" />
              <n-input v-model:value="h.value" size="small" placeholder="value (支持 {{var}})" />
              <n-button size="tiny" quaternary type="error" @click="removeHeader(detailRequest!, idx)">✕</n-button>
            </div>
            <div class="mt-3">
              <span class="text-sm font-medium mr-2">Request Body</span>
              <n-select
                v-model:value="detailRequest._bodyType"
                size="small"
                class="w-28 inline-block"
                :options="[
                  { label: '无 Body', value: 'none' },
                  { label: 'JSON', value: 'json' },
                  { label: 'Form', value: 'form' },
                  { label: 'Raw', value: 'text' },
                ]"
              />
              <n-input
                v-if="detailRequest._bodyType !== 'none'"
                v-model:value="detailRequest._bodyContent"
                type="textarea"
                :rows="6"
                class="mt-2 font-mono"
                placeholder='{"key": "value"}'
              />
            </div>
          </n-tab-pane>

          <!-- Preview: asserts + extraction + response -->
          <n-tab-pane name="preview" tab="断言与提取">
            <div class="mb-3">
              <div class="flex items-center gap-2 mb-1">
                <span class="text-sm">成功断言（正则，任一命中且无失败断言命中 = 成功）</span>
                <n-button size="tiny" type="primary" quaternary @click="addCondition('success')">ADD</n-button>
              </div>
              <div
                v-for="c in successConditionIdxs"
                :key="'s' + c.idx"
                class="flex items-center gap-2 mb-1 p-2 rounded bg-green-50 dark:bg-green-950"
              >
                <n-select
                  v-model:value="detailRequest._conditions[c.idx].type"
                  size="small"
                  class="w-28"
                  :options="condTypeOptions"
                />
                <n-input v-model:value="detailRequest._conditions[c.idx].value" size="small" placeholder="200 或正则" class="w-64" />
                <span v-if="detailRequest._conditionResults?.[c.idx]?.isPass" class="text-green-500 font-bold">✓</span>
                <span v-else-if="detailRequest._conditionResults?.[c.idx]" class="text-red-500 font-bold">✗</span>
                <div class="flex-1" />
                <n-button size="tiny" quaternary type="error" @click="removeCondition(c.idx)">✕</n-button>
              </div>
            </div>

            <div class="mb-3">
              <div class="flex items-center gap-2 mb-1">
                <span class="text-sm">失败断言（正则，任一命中 = 失败）</span>
                <n-button size="tiny" type="error" quaternary @click="addCondition('failure')">ADD</n-button>
              </div>
              <div
                v-for="c in failConditionIdxs"
                :key="'f' + c.idx"
                class="flex items-center gap-2 mb-1 p-2 rounded bg-red-50 dark:bg-red-950"
              >
                <n-select
                  v-model:value="detailRequest._conditions[c.idx].type"
                  size="small"
                  class="w-28"
                  :options="condTypeOptions"
                />
                <n-input v-model:value="detailRequest._conditions[c.idx].value" size="small" placeholder="正则" class="w-64" />
                <span v-if="detailRequest._conditionResults?.[c.idx]?.matched" class="text-red-500 font-bold">✗ 命中</span>
                <div class="flex-1" />
                <n-button size="tiny" quaternary type="error" @click="removeCondition(c.idx)">✕</n-button>
              </div>
            </div>

            <div class="mb-3">
              <div class="flex items-center gap-2 mb-1">
                <span class="text-sm">变量提取（正则捕获组）</span>
                <n-button size="tiny" type="primary" quaternary @click="addExtractor(detailRequest!)">ADD</n-button>
              </div>
              <div
                v-for="(ext, eIdx) in getExtractorList(detailRequest!)"
                :key="eIdx"
                class="flex items-center gap-2 mb-1 p-2 rounded bg-blue-50 dark:bg-blue-950"
              >
                <n-select v-model:value="ext.source" size="small" class="w-28" :options="extractorSourceOptions" />
                <n-input v-model:value="ext.key" size="small" placeholder="变量名" class="w-36" />
                <n-input v-model:value="ext.value" size="small" placeholder="(.+)" class="w-64 font-mono" />
                <span class="text-xs text-gray-400 font-mono truncate max-w-48">
                  → {{ detailRequest._lastResponse ? extractValue(detailRequest._lastResponse, ext.value, ext.source) ?? '-' : '-' }}
                </span>
                <div class="flex-1" />
                <n-button size="tiny" quaternary type="error" @click="removeExtractor(detailRequest!, eIdx)">✕</n-button>
              </div>
            </div>

            <div v-if="detailRequest._lastResponse" class="border-t pt-3 mt-3">
              <div class="flex items-center gap-2 mb-2">
                <span class="text-sm font-medium">响应内容</span>
                <n-tag
                  :type="detailRequest._lastResponse.status_code < 300 ? 'success' : 'error'"
                  size="tiny"
                >
                  {{ detailRequest._lastResponse.status_code }}
                </n-tag>
                <n-button-group size="tiny">
                  <n-button :type="responseViewMode === 'render' ? 'primary' : 'default'" @click="responseViewMode = 'render'">
                    预览
                  </n-button>
                  <n-button :type="responseViewMode === 'source' ? 'primary' : 'default'" @click="responseViewMode = 'source'">
                    源码
                  </n-button>
                </n-button-group>
                <span class="text-xs text-gray-400">{{ responseContentType }}</span>
              </div>
              <iframe
                v-if="responseViewMode === 'render' && isHtmlResponse"
                :srcdoc="detailRequest._lastResponse.body"
                class="w-full h-96 border rounded bg-white"
              />
              <pre
                v-else-if="responseViewMode === 'render' && isJsonResponse"
                class="text-xs font-mono whitespace-pre-wrap break-all max-h-96 overflow-auto p-3 rounded bg-gray-50 dark:bg-gray-800"
                >{{ formatResponseBody(detailRequest._lastResponse.body) }}</pre
              >
              <pre
                v-else
                class="text-xs font-mono whitespace-pre-wrap break-all max-h-96 overflow-auto p-3 rounded bg-gray-50 dark:bg-gray-800"
                >{{ detailRequest._lastResponse.body }}</pre
              >
            </div>
            <n-empty v-else description="点击右上角「测试」后可查看响应和断言结果" size="small" class="mt-4" />
          </n-tab-pane>

          <!-- Response headers -->
          <n-tab-pane name="headers" tab="响应 Headers">
            <n-empty v-if="!detailRequest._lastResponse" description="先测试请求" size="small" />
            <n-table v-else size="small" :bordered="false">
              <thead>
                <tr><th class="w-64">Name</th><th>Value</th></tr>
              </thead>
              <tbody>
                <tr v-for="[k, v] in Object.entries(detailRequest._lastResponse.headers || {})" :key="k">
                  <td class="font-mono text-xs font-bold">{{ k }}</td>
                  <td class="font-mono text-xs break-all">{{ v }}</td>
                </tr>
              </tbody>
            </n-table>
          </n-tab-pane>
        </n-tabs>
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button size="small" @click="showDetail = false">完成</n-button>
        </div>
      </template>
    </n-modal>

    <!-- cURL modal -->
    <n-modal v-model:show="showCurlDialog" preset="card" title="追加 cURL 命令" class="max-w-2xl" :style="{ width: '92vw' }">
      <n-input
        v-model:value="curlInput"
        type="textarea"
        :rows="10"
        class="font-mono"
        placeholder='curl -X POST https://api.example.com/data -H "Content-Type: application/json" -d ...'
      />
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="showCurlDialog = false">取消</n-button>
          <n-button type="primary" :loading="curlParsing" @click="importCurl">解析并追加</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>
