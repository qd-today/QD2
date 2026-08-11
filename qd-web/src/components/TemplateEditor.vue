<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useMessage } from 'naive-ui'
import {
  AddOutline,
  ArrowDownOutline,
  ArrowUpOutline,
  ClipboardOutline,
  CopyOutline,
} from '@vicons/ionicons5'
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
interface ExtractorRow {
  key: string
  value: string
  source: 'content' | 'status' | 'header'
  headerName?: string
}
interface ApiRulePreset {
  re: string
  from: 'content' | 'status'
}
interface ApiExtractorPreset extends ApiRulePreset {
  name: string
}
interface ApiPreset {
  label: string
  method: 'GET' | 'POST'
  url: string
  comment: string
  body?: string
  successAsserts: ApiRulePreset[]
  extractVariables?: ApiExtractorPreset[]
}
interface HARRequestData {
  method: string
  url: string
  checked: boolean
  headers: HARHeader[]
  extractors: Record<string, string>
  _bodyType: string
  _bodyContent: string
  _conditions: RequestCondition[]
  _testing: boolean
  _lastResponse: any
  _comment: string
  _cookies: string
  _conditionResults: any[]
  _extractorList: ExtractorRow[]
  _legacyExtractors: Record<string, string>
}

const message = useMessage()
const props = defineProps<{ initialData?: any }>()

const rawTplData = props.initialData?.template_data
const initialRequests =
  props.initialData?.requests ||
  (Array.isArray(rawTplData)
    ? rawTplData.map((e: any) => ({
        ...(e.request || {}),
        checked: e.checked ?? e.request?.checked ?? true,
        ...ruleToLegacy(e.rule),
      }))
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

function inferBodyType(request: any): string {
  if (request._bodyType) return request._bodyType
  const mimeType = String(request.postData?.mimeType || request.mimeType || '').toLowerCase()
  if (mimeType.includes('application/json')) return 'json'
  if (mimeType.includes('application/x-www-form-urlencoded')) return 'form'
  if (request.postData || Object.prototype.hasOwnProperty.call(request, 'data')) return 'text'
  return 'none'
}

function bodyMimeType(bodyType: string): string {
  if (bodyType === 'json') return 'application/json'
  if (bodyType === 'form') return 'application/x-www-form-urlencoded'
  return 'text/plain'
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
  const rule = r.rule || r
  const conditions: RequestCondition[] = []
  for (const assertion of rule.success_asserts || []) {
    conditions.push({
      type: assertion.from === 'status' ? 'status_code' : 'body_contains',
      operator: 'matches',
      value: assertion.re || '',
      outcome: 'success',
    })
  }
  for (const assertion of rule.failed_asserts || []) {
    conditions.push({
      type: assertion.from === 'status' ? 'status_code' : 'body_contains',
      operator: 'matches',
      value: assertion.re || '',
      outcome: 'failure',
    })
  }
  if (conditions.length === 0) conditions.push(...(r._conditions || []))

  const extractorList: ExtractorRow[] = []
  const declaredNames = new Set<string>()
  for (const extractor of rule.extract_variables || []) {
    const name = extractor.name || ''
    const from = extractor.from || 'content'
    extractorList.push({
      key: name,
      value: extractor.re || '',
      source: from.startsWith('header') ? 'header' : from === 'status' ? 'status' : 'content',
      headerName: from.startsWith('header-') ? from.slice(7) : undefined,
    })
    if (name) declaredNames.add(name)
  }

  const legacyExtractors: Record<string, string> = {}
  for (const [key, rawExpression] of Object.entries(r.extractors || {})) {
    if (declaredNames.has(key)) continue
    const expression = String(rawExpression)
    if (expression.startsWith('regex:')) {
      extractorList.push({ key, value: expression.slice(6), source: 'content' })
    } else if (expression.startsWith('header:')) {
      extractorList.push({ key, value: '(.+)', source: 'header', headerName: expression.slice(7) })
    } else if (expression === 'status') {
      extractorList.push({ key, value: '(.+)', source: 'status' })
    } else {
      legacyExtractors[key] = expression
      continue
    }
    declaredNames.add(key)
  }

  const req: HARRequestData = {
    method: r.method || 'GET',
    url: r.url || '',
    checked: r.checked !== false,
    headers: r.headers || [],
    extractors: { ...legacyExtractors },
    _bodyType: inferBodyType(r),
    _bodyContent: r.postData?.text ?? r.data ?? '',
    _conditions: conditions,
    _testing: false,
    _lastResponse: null,
    _comment: r._comment || r.comment || '',
    _cookies: '',
    _conditionResults: [],
    _extractorList: extractorList,
    _legacyExtractors: legacyExtractors,
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
const enabledRequestCount = computed(
  () => template.requests.filter((request: HARRequestData) => request.checked).length,
)
const allRequestsChecked = computed(
  () => template.requests.length > 0 && enabledRequestCount.value === template.requests.length,
)
const requestClipboard = ref<HARRequestData | null>(null)
const activeRequestIndex = ref<number | null>(null)

const status200: ApiRulePreset = { re: '200', from: 'status' }
const jsonStatus200: ApiRulePreset = { re: '"状态": "200"', from: 'content' }
const jsonStatusOk: ApiRulePreset = { re: '"状态": "OK"', from: 'content' }

const apiCatalog: Record<string, ApiPreset> = {
  delay: {
    label: '延时',
    method: 'GET',
    url: 'api://util/delay/3',
    comment: '延时3秒',
    successAsserts: [status200],
  },
  timestamp: {
    label: '时间戳',
    method: 'POST',
    url: 'api://util/timestamp',
    comment: '返回对应时间戳和时间',
    body: 'ts=&form=&dt=',
    successAsserts: [status200],
  },
  unicode: {
    label: 'Unicode 转中文',
    method: 'POST',
    url: 'api://util/unicode',
    comment: 'Unicode转换',
    body: 'html_unescape=false&content=%5Cu4f60%5Cu597d',
    successAsserts: [status200, jsonStatus200],
    extractVariables: [{ name: '', re: '"转换后": "(.*)"', from: 'content' }],
  },
  gb2312: {
    label: 'GB2312 编码',
    method: 'POST',
    url: 'api://util/gb2312',
    comment: 'GB2312编码',
    body: 'content=%E4%B8%AD%E6%96%87',
    successAsserts: [status200, jsonStatus200],
    extractVariables: [{ name: '', re: '"转换后": "(.*)"', from: 'content' }],
  },
  urldecode: {
    label: 'URL 解码',
    method: 'POST',
    url: 'api://util/urldecode',
    comment: 'URL解码',
    body: 'unquote_plus=false&encoding=utf-8&content=%25E4%25BD%25A0%25E5%25A5%25BD',
    successAsserts: [status200, jsonStatus200],
    extractVariables: [{ name: '', re: '"转换后": "(.*)"', from: 'content' }],
  },
  regex: {
    label: '正则表达式',
    method: 'POST',
    url: 'api://util/regex',
    comment: '正则提取',
    body: 'p=(%5Cd%2B)&data=code%3D123',
    successAsserts: [status200, jsonStatusOk],
    extractVariables: [{ name: '', re: '"1": "(.*)"', from: 'content' }],
  },
  replace: {
    label: '字符串替换',
    method: 'POST',
    url: 'api://util/string/replace',
    comment: '字符串替换',
    body: 'r=json&p=%5Cd&s=a-1&t=x',
    successAsserts: [status200, jsonStatusOk],
    extractVariables: [{ name: '', re: '"处理后字符串": "(.*)"', from: 'content' }],
  },
  rsaEncrypt: {
    label: 'RSA 加密',
    method: 'POST',
    url: 'api://util/rsa',
    comment: 'RSA加密',
    body: 'f=encode&key=&data=',
    successAsserts: [status200],
    extractVariables: [{ name: '', re: '(.*)', from: 'content' }],
  },
  rsaDecrypt: {
    label: 'RSA 解密',
    method: 'POST',
    url: 'api://util/rsa',
    comment: 'RSA解密',
    body: 'f=decode&key=&data=',
    successAsserts: [status200],
    extractVariables: [{ name: '', re: '(.*)', from: 'content' }],
  },
}

const apiRequestOptions = [
  { label: '请求控制', key: 'control', children: [{ label: apiCatalog.delay.label, key: 'delay' }] },
  { label: '时间处理', key: 'time', children: [{ label: apiCatalog.timestamp.label, key: 'timestamp' }] },
  {
    label: '编码解码',
    key: 'encoding',
    children: ['unicode', 'gb2312', 'urldecode'].map((key) => ({ label: apiCatalog[key].label, key })),
  },
  {
    label: '字符串处理',
    key: 'string',
    children: ['regex', 'replace'].map((key) => ({ label: apiCatalog[key].label, key })),
  },
  {
    label: '加密解密',
    key: 'crypto',
    children: ['rsaEncrypt', 'rsaDecrypt'].map((key) => ({ label: apiCatalog[key].label, key })),
  },
]

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
    checked: true,
    headers: [],
    extractors: {},
    _bodyType: 'none',
    _bodyContent: '',
    _conditions: [],
    _testing: false,
    _lastResponse: null,
    _comment: '',
    _cookies: '',
    _conditionResults: [],
    _extractorList: [],
    _legacyExtractors: {},
  }
  template.requests.push(req)
  openDetail(req, template.requests.length - 1)
}

function cloneRequest(request: HARRequestData): HARRequestData {
  const cloned = JSON.parse(JSON.stringify(request)) as HARRequestData
  cloned._testing = false
  cloned._lastResponse = null
  cloned._conditionResults = []
  return cloned
}

function copyRequest(request: HARRequestData) {
  requestClipboard.value = cloneRequest(request)
  message.success('请求已复制')
}

function pasteRequest(afterIndex?: number) {
  if (!requestClipboard.value) return
  const fallbackIndex = activeRequestIndex.value ?? template.requests.length - 1
  const targetIndex = Math.min((afterIndex ?? fallbackIndex) + 1, template.requests.length)
  template.requests.splice(targetIndex, 0, cloneRequest(requestClipboard.value))
  activeRequestIndex.value = targetIndex
  message.success('请求已粘贴')
}

function moveRequest(index: number, offset: -1 | 1) {
  const targetIndex = index + offset
  if (targetIndex < 0 || targetIndex >= template.requests.length) return
  const [request] = template.requests.splice(index, 1)
  template.requests.splice(targetIndex, 0, request)
  if (detailRequest.value === request) activeRequestIndex.value = targetIndex
}

function toggleAllRequests(checked: boolean) {
  for (const request of template.requests) request.checked = checked
}

function splitRequestUrl(url: string) {
  const hashIndex = url.indexOf('#')
  const hash = hashIndex >= 0 ? url.slice(hashIndex) : ''
  const withoutHash = hashIndex >= 0 ? url.slice(0, hashIndex) : url
  const queryIndex = withoutHash.indexOf('?')
  return {
    base: queryIndex >= 0 ? withoutHash.slice(0, queryIndex) : withoutHash,
    query: queryIndex >= 0 ? withoutHash.slice(queryIndex + 1) : '',
    hash,
  }
}

function handleMethodChange(request: HARRequestData, method: string) {
  const previousMethod = request.method
  request.method = method
  request._lastResponse = null
  request._conditionResults = []

  if (previousMethod === method || !request.url.toLowerCase().startsWith('api://util/')) return

  const { base, query, hash } = splitRequestUrl(request.url)
  if (method === 'GET' && request._bodyType === 'form') {
    const bodyQuery = request._bodyContent.replace(/^\?/, '')
    const mergedQuery = [query, bodyQuery].filter(Boolean).join('&')
    request.url = `${base}${mergedQuery ? `?${mergedQuery}` : ''}${hash}`
    request._bodyType = 'none'
    request._bodyContent = ''
  } else if (method === 'POST') {
    request.url = `${base}${hash}`
    request._bodyType = 'form'
    request._bodyContent = query
  }
}

function insertApiRequest(key: string) {
  const preset = apiCatalog[key]
  if (!preset) return
  const request = parseRequestData({
    method: preset.method,
    url: preset.url,
    checked: true,
    headers: [],
    postData:
      preset.body === undefined
        ? undefined
        : { mimeType: 'application/x-www-form-urlencoded', text: preset.body },
    success_asserts: preset.successAsserts,
    extract_variables: preset.extractVariables || [],
    _comment: preset.comment,
  })
  const insertAt = Math.min((activeRequestIndex.value ?? template.requests.length - 1) + 1, template.requests.length)
  template.requests.splice(insertAt, 0, request)
  openDetail(request, insertAt)
}

function addRequestsFromParsed(parsedList: any[]) {
  for (const p of parsedList) {
    const headers = Object.entries(p.headers || {}).map(([name, value]) => ({
      name,
      value: String(value),
    }))
    template.requests.push(parseRequestData({
      method: p.method || 'GET',
      url: p.url || '',
      headers,
      extractors: p.extractors || {},
      postData: p.body_type && p.body_type !== 'none' ? { text: p.body || '' } : undefined,
      _bodyType: p.body_type || 'none',
      success_asserts: p.success_asserts || [],
      failed_asserts: p.failed_asserts || [],
      extract_variables: p.extract_variables || [],
      _comment: p.name || '',
      checked: p.checked !== false,
    }))
  }
}

function removeRequest(index: number) {
  template.requests.splice(index, 1)
  if (activeRequestIndex.value === index) activeRequestIndex.value = null
}

// --- Detail ---
const showDetail = ref(false)
const detailRequest = ref<HARRequestData | null>(null)
const detailTab = ref('request')
const responseViewMode = ref<'render' | 'source'>('render')

function openDetail(row: HARRequestData, index = template.requests.indexOf(row)) {
  detailRequest.value = row
  activeRequestIndex.value = index >= 0 ? index : null
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
  return req._extractorList
}
function addExtractor(req: HARRequestData) {
  getExtractorList(req).push({ key: '', value: '', source: 'content' })
}
function removeExtractor(req: HARRequestData, idx: number) {
  getExtractorList(req).splice(idx, 1)
}

function extractValue(response: any, expression: string, source?: string, headerName?: string): any {
  if (!response || !expression) return null
  try {
    let searchText = response.body
    if (source === 'status') searchText = String(response.status_code)
    if (source === 'header') {
      if (headerName) {
        const entry = Object.entries(response.headers || {}).find(
          ([key]) => key.toLowerCase() === headerName.toLowerCase()
        )
        searchText = entry ? String(entry[1]) : ''
      } else {
        searchText = Object.entries(response.headers || {})
          .map(([k, v]) => `${k}: ${v}`)
          .join('\n')
      }
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
    const assertionFailed = req._conditionResults.some((result) => !result.isPass)
    if (res.data.error || res.data.status_code <= 0) {
      message.error(`请求测试失败: ${res.data.error || '未知错误'}`)
    } else if (res.data.status_code >= 400) {
      message.error(`${res.data.status_code} - ${res.data.elapsed_ms.toFixed(0)}ms`)
    } else if (assertionFailed) {
      message.error(`断言失败 - ${res.data.elapsed_ms.toFixed(0)}ms`)
    } else {
      message.success(`${res.data.status_code} - ${res.data.elapsed_ms.toFixed(0)}ms`)
    }
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
        checked: r.checked,
        _comment: r._comment,
        headers: r.headers.filter((h: HARHeader) => h.name),
        postData:
          r._bodyType !== 'none'
            ? { mimeType: bodyMimeType(r._bodyType), text: r._bodyContent }
            : undefined,
        extractors: r._legacyExtractors || {},
        // QD v1 compatible rule block
        rule: {
          success_asserts: (r._conditions || [])
            .filter((c: any) => c.outcome === 'success')
            .map((c: any) => ({ re: c.value, from: c.type === 'status_code' ? 'status' : 'content' })),
          failed_asserts: (r._conditions || [])
            .filter((c: any) => c.outcome === 'failure')
            .map((c: any) => ({ re: c.value, from: c.type === 'status_code' ? 'status' : 'content' })),
          extract_variables: r._extractorList
            .filter((e: ExtractorRow) => e.value)
            .map((e: any) => ({
              name: e.key,
              re: e.value,
              from: e.source === 'header' && e.headerName ? `header-${e.headerName}` : e.source,
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
      <div
        v-for="(v, i) in variableList"
        :key="i"
        class="grid grid-cols-1 sm:grid-cols-[minmax(12rem,2fr)_auto_minmax(16rem,3fr)_auto] gap-2 mb-2 items-center"
      >
        <n-input v-model:value="v.key" size="small" placeholder="variable_name" class="w-full" />
        <span class="hidden sm:inline text-gray-400">=</span>
        <n-input v-model:value="v.value" size="small" placeholder="默认值" class="w-full" />
        <n-button size="tiny" quaternary type="error" @click="removeVariable(i)">✕</n-button>
      </div>
    </n-card>

    <!-- Requests -->
    <n-card size="small" class="rounded-lg">
      <template #header>
        <div class="flex justify-between items-center flex-wrap gap-2">
          <div class="flex items-center gap-2">
            <span>请求列表</span>
            <n-tag size="small" round>{{ enabledRequestCount }}/{{ template.requests.length }} 已启用</n-tag>
          </div>
          <div class="flex flex-wrap gap-2">
            <n-upload :show-file-list="false" accept=".har,.json" :custom-request="handleHarUpload">
              <n-button size="tiny">📥 追加HAR</n-button>
            </n-upload>
            <n-button size="tiny" @click="showCurlDialog = true">📋 追加cURL</n-button>
            <n-button size="tiny" :disabled="!requestClipboard" title="在当前请求后粘贴" @click="pasteRequest()">
              <template #icon><n-icon><ClipboardOutline /></n-icon></template>
              粘贴
            </n-button>
            <n-dropdown trigger="click" :options="apiRequestOptions" @select="insertApiRequest">
              <n-button size="tiny">插入 API</n-button>
            </n-dropdown>
            <n-button size="tiny" type="primary" @click="addRequest">
              <template #icon><n-icon><AddOutline /></n-icon></template>
              添加请求
            </n-button>
          </div>
        </div>
      </template>

      <n-empty v-if="template.requests.length === 0" description="暂无请求" size="small" />
      <n-table v-else size="small" :bordered="false">
        <thead>
          <tr>
            <th class="w-8">
              <n-checkbox
                :checked="allRequestsChecked"
                :indeterminate="enabledRequestCount > 0 && !allRequestsChecked"
                aria-label="启用全部请求"
                @update:checked="toggleAllRequests"
              />
            </th>
            <th class="w-10">#</th>
            <th class="w-20">方法</th>
            <th>URL</th>
            <th class="w-28">备注</th>
            <th class="w-24">状态</th>
            <th class="w-64 !text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, i) in template.requests"
            :key="i"
            class="cursor-pointer"
            :class="{ 'opacity-55': !row.checked }"
            @click="openDetail(row, i)"
          >
            <td @click.stop>
              <n-checkbox v-model:checked="row.checked" :aria-label="`执行请求 ${i + 1}`" />
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
              <n-button size="tiny" quaternary circle title="上移" :disabled="i === 0" @click="moveRequest(i, -1)">
                <template #icon><n-icon><ArrowUpOutline /></n-icon></template>
              </n-button>
              <n-button
                size="tiny"
                quaternary
                circle
                title="下移"
                :disabled="i === template.requests.length - 1"
                @click="moveRequest(i, 1)"
              >
                <template #icon><n-icon><ArrowDownOutline /></n-icon></template>
              </n-button>
              <n-button size="tiny" quaternary circle title="复制" @click="copyRequest(row)">
                <template #icon><n-icon><CopyOutline /></n-icon></template>
              </n-button>
              <n-button
                size="tiny"
                quaternary
                circle
                title="粘贴到后面"
                :disabled="!requestClipboard"
                @click="pasteRequest(i)"
              >
                <template #icon><n-icon><ClipboardOutline /></n-icon></template>
              </n-button>
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
              <n-select
                :value="detailRequest.method"
                :options="methodOptions"
                class="w-28"
                size="small"
                @update:value="handleMethodChange(detailRequest!, $event)"
              />
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
                class="grid grid-cols-1 md:grid-cols-[8rem_minmax(10rem,0.7fr)_minmax(16rem,1.3fr)_auto] items-start gap-2 mb-1 p-2 rounded bg-blue-50 dark:bg-blue-950"
              >
                <n-select v-model:value="ext.source" size="small" class="w-full" :options="extractorSourceOptions" />
                <n-input v-model:value="ext.key" size="small" placeholder="变量名" class="w-full" />
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <n-input
                    v-if="ext.source === 'header'"
                    v-model:value="ext.headerName"
                    size="small"
                    placeholder="Header 名称（可选）"
                    class="w-full"
                  />
                  <n-input
                    v-model:value="ext.value"
                    size="small"
                    placeholder="正则，例如 (.+)"
                    class="w-full font-mono"
                    :class="ext.source === 'header' ? '' : 'sm:col-span-2'"
                  />
                </div>
                <n-button size="tiny" quaternary type="error" @click="removeExtractor(detailRequest!, eIdx)">✕</n-button>
                <span
                  class="md:col-span-4 text-xs text-gray-600 dark:text-gray-300 font-mono whitespace-pre-wrap break-all max-h-32 overflow-auto border-t border-blue-100 dark:border-blue-900 pt-2"
                  :title="String(detailRequest._lastResponse ? extractValue(detailRequest._lastResponse, ext.value, ext.source, ext.headerName) ?? '-' : '-')"
                >
                  → {{ detailRequest._lastResponse ? extractValue(detailRequest._lastResponse, ext.value, ext.source, ext.headerName) ?? '-' : '-' }}
                </span>
              </div>
            </div>

            <div v-if="detailRequest._lastResponse" class="border-t pt-3 mt-3">
              <div class="flex items-center gap-2 mb-2">
                <span class="text-sm font-medium">响应内容</span>
                <n-tag
                  :type="detailRequest._lastResponse.error || detailRequest._lastResponse.status_code >= 400 ? 'error' : 'success'"
                  size="tiny"
                >
                  {{ detailRequest._lastResponse.error ? 'ERR' : detailRequest._lastResponse.status_code }}
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
              <n-alert v-if="detailRequest._lastResponse.error" type="error" class="mb-2">
                {{ detailRequest._lastResponse.error }}
              </n-alert>
              <iframe
                v-if="responseViewMode === 'render' && isHtmlResponse"
                :srcdoc="detailRequest._lastResponse.body"
                class="w-full h-96 border rounded bg-white"
              />
              <pre
                v-else-if="responseViewMode === 'render' && isJsonResponse"
                class="text-xs text-gray-800 dark:text-gray-100 font-mono whitespace-pre-wrap break-all max-h-96 overflow-auto p-3 rounded bg-gray-50 dark:bg-gray-800"
                >{{ formatResponseBody(detailRequest._lastResponse.body) }}</pre
              >
              <pre
                v-else
                class="text-xs text-gray-800 dark:text-gray-100 font-mono whitespace-pre-wrap break-all max-h-96 overflow-auto p-3 rounded bg-gray-50 dark:bg-gray-800"
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
