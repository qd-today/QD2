<template>
  <div class="template-editor">
    <!-- Template Basic Info -->
    <el-card shadow="never" style="margin-bottom: 16px">
      <template #header><span>模板信息</span></template>
      <el-form :model="template" label-width="80px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="名称" required>
              <el-input v-model="template.name" placeholder="模板名称" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="标签">
              <el-tag v-for="tag in template.tags" :key="tag" closable style="margin-right: 4px" @close="removeTag(tag)">{{ tag }}</el-tag>
              <el-input v-if="tagInputVisible" ref="tagInputRef" v-model="tagInputValue" size="small" style="width: 100px" @keyup.enter="addTag" @blur="addTag" />
              <el-button v-else size="small" @click="showTagInput">+ 添加</el-button>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="描述">
          <el-input v-model="template.description" type="textarea" :rows="2" placeholder="模板描述" />
        </el-form-item>
        <el-form-item label="公开"><el-switch v-model="template.is_public" /></el-form-item>
      </el-form>
    </el-card>

    <!-- Variables -->
    <el-card shadow="never" style="margin-bottom: 16px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>模板变量</span>
          <el-button size="small" @click="addVariable">+ 添加变量</el-button>
        </div>
      </template>
      <el-table :data="variableList" size="small" empty-text="暂无变量">
        <el-table-column label="变量名" min-width="150">
          <template #default="{ row }"><el-input v-model="row.key" size="small" placeholder="variable_name" /></template>
        </el-table-column>
        <el-table-column label="默认值" min-width="200">
          <template #default="{ row }"><el-input v-model="row.value" size="small" placeholder="default value" /></template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ $index }"><el-button size="small" type="danger" link @click="removeVariable($index)">删除</el-button></template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Request List -->
    <el-card shadow="never">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <div style="display: flex; align-items: center; gap: 12px">
            <span>请求列表</span>
            <el-tag size="small">{{ template.requests.length }}</el-tag>
            <el-checkbox v-model="selectAll" @change="toggleSelectAll">全选</el-checkbox>
            <el-button v-if="selectedRows.length > 0" size="small" type="danger" link @click="deleteSelected">删除选中 ({{ selectedRows.length }})</el-button>
          </div>
          <div style="display: flex; gap: 8px">
            <el-upload :show-file-list="false" accept=".har,.json" :before-upload="handleHarUpload">
              <el-button size="small">📥 追加HAR</el-button>
            </el-upload>
            <el-button size="small" @click="showCurlDialog = true">📋 追加cURL</el-button>
            <el-button size="small" type="primary" @click="addRequest">+ 添加请求</el-button>
          </div>
        </div>
      </template>

      <div v-if="template.requests.length === 0" style="text-align: center; padding: 40px; color: #999">暂无请求</div>

      <el-table :data="template.requests" size="small" stripe empty-text="暂无请求" @row-click="(row: any) => openDetail(row)">
        <el-table-column width="40" @click.stop>
          <template #default="{ row }"><el-checkbox v-model="row._selected" @click.stop @change="updateSelectedRows" /></template>
        </el-table-column>
        <el-table-column label="序号" width="50" type="index" :index="(i: number) => i + 1" />
        <el-table-column label="方法" width="80">
          <template #default="{ row }"><el-tag :type="getMethodType(row.method)" size="small" style="font-weight: bold">{{ row.method }}</el-tag></template>
        </el-table-column>
        <el-table-column label="URL" min-width="300" show-overflow-tooltip>
          <template #default="{ row }"><span style="font-family: monospace; font-size: 12px">{{ row.url || '(未设置)' }}</span></template>
        </el-table-column>
        <el-table-column label="备注" width="150" show-overflow-tooltip>
          <template #default="{ row }"><span style="color: #999; font-size: 12px">{{ row._comment || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <template v-if="row._lastResponse">
              <el-tag :type="row._lastResponse.error ? 'danger' : (row._lastResponse.status_code >= 200 && row._lastResponse.status_code < 300 ? 'success' : 'warning')" size="small">
                {{ row._lastResponse.error ? 'ERR' : row._lastResponse.status_code }}
              </el-tag>
              <span style="font-size: 11px; color: #999; margin-left: 4px">{{ row._lastResponse.elapsed_ms.toFixed(0) }}ms</span>
            </template>
            <span v-else style="color: #ccc; font-size: 11px">未测试</span>
          </template>
        </el-table-column>
        <el-table-column label="条件" width="70">
          <template #default="{ row }">
            <template v-if="row._conditionResults && row._conditionResults.length > 0">
              <span v-if="row._conditionResults.every((c: any) => c.isPass)" style="color: #67c23a">✅</span>
              <span v-else style="color: #f56c6c">❌</span>
            </template>
            <span v-else style="color: #ccc">-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right" @click.stop>
          <template #default="{ row, $index }">
            <el-button size="small" type="primary" link :loading="row._testing" @click.stop="testRequest($index)">▶ 测试</el-button>
            <el-button size="small" type="danger" link @click.stop="removeRequest($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Detail Dialog (大窗口) -->
    <el-dialog
      v-model="showDetail"
      :title="detailRequest ? `#${(template.requests.indexOf(detailRequest) || 0) + 1} ${detailRequest.method} ${detailRequest.url}` : ''"
      width="90%"
      top="3vh"
      destroy-on-close
    >
      <div v-if="detailRequest" class="detail-dialog">
        <!-- Comment -->
        <div style="margin-bottom: 12px; display: flex; align-items: center; gap: 8px">
          <span style="font-size: 13px; color: #606266; white-space: nowrap">备注:</span>
          <el-input v-model="detailRequest._comment" size="small" placeholder="请求备注" style="flex: 1; max-width: 400px" />
        </div>

        <el-tabs v-model="detailActiveTab" type="border-card">
          <!-- 请求 / Request -->
          <el-tab-pane label="请求 / Request" name="request">
            <el-form label-width="120px" size="small">
              <el-form-item label="Request URL">
                <el-input v-model="detailRequest.url" placeholder="https://example.com/api" />
              </el-form-item>
              <el-form-item label="Request Method">
                <el-select v-model="detailRequest.method" style="width: 120px">
                  <el-option label="GET" value="GET" /><el-option label="POST" value="POST" />
                  <el-option label="PUT" value="PUT" /><el-option label="DELETE" value="DELETE" />
                  <el-option label="PATCH" value="PATCH" />
                </el-select>
              </el-form-item>
            </el-form>
            <div>
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px">
                <span style="font-weight: bold; font-size: 13px">Request Headers</span>
                <el-button size="small" @click="addHeader(detailRequest!)">+ Add</el-button>
              </div>
              <el-table :data="detailRequest.headers || []" size="small" border>
                <el-table-column label="" width="40"><template #default><el-checkbox :model-value="true" disabled size="small" /></template></el-table-column>
                <el-table-column label="Name" min-width="180"><template #default="{ row }"><el-input v-model="row.name" size="small" placeholder="Header-Name" /></template></el-table-column>
                <el-table-column label="Value" min-width="300"><template #default="{ row }"><el-input v-model="row.value" size="small" placeholder="value (支持 {{var}})" /></template></el-table-column>
                <el-table-column label="" width="40"><template #default="{ $index: idx }"><el-button size="small" type="danger" link @click="removeHeader(detailRequest!, idx)">✕</el-button></template></el-table-column>
              </el-table>
            </div>
            <div style="margin-top: 12px">
              <span style="font-weight: bold; font-size: 13px">Request Body</span>
              <el-select v-model="detailRequest._bodyType" size="small" style="margin-left: 8px">
                <el-option label="无 Body" value="none" /><el-option label="JSON" value="json" />
                <el-option label="Form" value="form" /><el-option label="Raw" value="text" />
              </el-select>
              <el-input v-if="detailRequest._bodyType !== 'none'" v-model="detailRequest._bodyContent" type="textarea" :rows="6" placeholder='{"key": "value"}' style="margin-top: 8px; font-family: monospace" />
            </div>
          </el-tab-pane>

          <!-- 响应 / Response -->
          <el-tab-pane label="响应 / Response" name="response">
            <div v-if="!detailRequest._lastResponse" style="text-align: center; padding: 40px; color: #999">点击「测试」查看响应</div>
            <div v-else>
              <div style="margin-bottom: 16px; display: flex; align-items: center; gap: 8px">
                <span style="font-weight: bold">Status Code</span>
                <el-tag :type="detailRequest._lastResponse.status_code >= 200 && detailRequest._lastResponse.status_code < 300 ? 'success' : 'danger'" size="small">
                  {{ detailRequest._lastResponse.status_code }}
                </el-tag>
              </div>
              <div style="margin-bottom: 16px">
                <span style="font-weight: bold; font-size: 13px; margin-bottom: 8px; display: block">Response Headers</span>
                <el-table :data="Object.entries(detailRequest._lastResponse.headers || {})" size="small" border>
                  <el-table-column label="" width="40"><template #default><el-checkbox :model-value="true" disabled size="small" /></template></el-table-column>
                  <el-table-column label="Name" min-width="200">
                    <template #default="{ row }"><span style="font-weight: bold; font-family: monospace; font-size: 12px">{{ row[0] }}</span></template>
                  </el-table-column>
                  <el-table-column label="Value" min-width="400">
                    <template #default="{ row }"><span style="font-family: monospace; font-size: 12px; word-break: break-all">{{ row[1] }}</span></template>
                  </el-table-column>
                </el-table>
              </div>
              <div>
                <span style="font-weight: bold; font-size: 13px; margin-bottom: 8px; display: block">Cookies</span>
                <el-table :data="cookieList" size="small" border empty-text="无 Cookie">
                  <el-table-column label="" width="40"><template #default><el-checkbox :model-value="true" disabled size="small" /></template></el-table-column>
                  <el-table-column label="Name" min-width="200">
                    <template #default="{ row }"><span style="font-weight: bold; font-family: monospace; font-size: 12px">{{ row.name }}</span></template>
                  </el-table-column>
                  <el-table-column label="Value" min-width="400">
                    <template #default="{ row }"><span style="font-family: monospace; font-size: 12px">{{ row.value }}</span></template>
                  </el-table-column>
                </el-table>
              </div>
            </div>
          </el-tab-pane>

          <!-- 测试 / Test -->
          <el-tab-pane label="测试 / Test" name="test">
            <div style="margin-bottom: 16px">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px">
                <span style="font-weight: bold; font-size: 13px">Variables</span>
                <el-button size="small" type="primary" link @click="addVariable()">ADD</el-button>
              </div>
              <el-table :data="variableList" size="small" border empty-text="无变量">
                <el-table-column label="" width="40"><template #default><el-checkbox :model-value="true" disabled size="small" /></template></el-table-column>
                <el-table-column label="变量名" min-width="150">
                  <template #default="{ row }"><span style="font-weight: bold; font-family: monospace; font-size: 12px">{{ row.key }}</span></template>
                </el-table-column>
                <el-table-column label="=" width="30"><template #default>=</template></el-table-column>
                <el-table-column label="值" min-width="400">
                  <template #default="{ row }"><span style="font-family: monospace; font-size: 12px; word-break: break-all">{{ row.value }}</span></template>
                </el-table-column>
                <el-table-column label="" width="40"><template #default="{ $index: idx }"><el-button size="small" type="danger" link @click="removeVariable(idx)">✕</el-button></template></el-table-column>
              </el-table>
            </div>
            <div>
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px">
                <span style="font-weight: bold; font-size: 13px">Cookies</span>
                <el-button size="small" type="info" link @click="detailRequest._cookies = ''">CLEAR</el-button>
              </div>
              <el-input v-model="detailRequest._cookies" type="textarea" :rows="3" placeholder="Cookie 字符串" size="small" style="font-family: monospace; font-size: 12px" />
            </div>
          </el-tab-pane>

          <!-- 预览 / Preview -->
          <el-tab-pane label="预览 / Preview" name="preview">
            <div v-if="!detailRequest._lastResponse" style="text-align: center; padding: 40px; color: #999">先测试请求再预览</div>
            <div v-else>
              <!-- Status Code -->
              <div style="margin-bottom: 16px; display: flex; align-items: center; gap: 8px">
                <span style="font-weight: bold">Status Code:</span>
                <el-tag :type="detailRequest._lastResponse.status_code >= 200 && detailRequest._lastResponse.status_code < 300 ? 'success' : 'danger'" size="small">
                  {{ detailRequest._lastResponse.status_code }}
                </el-tag>
                <span v-if="!detailRequest._lastResponse.error" style="color: #67c23a; font-size: 16px">✓</span>
              </div>

              <!-- Success Conditions -->
              <div style="margin-bottom: 12px">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px">
                  <span style="font-size: 13px">请求成功条件断言 支持正则，任意条件满足即为请求成功（没有失败条件命中时）</span>
                  <el-button size="small" type="primary" link @click="addSuccessCondition">ADD</el-button>
                </div>
                <div v-for="(c, cIdx) in successConditionIdxs" :key="'s'+cIdx" class="condition-row success-row">
                  <el-select v-model="detailRequest._conditions[c.idx].type" size="small" style="width: 110px">
                    <el-option label="status" value="status_code" /><el-option label="content" value="body_contains" />
                    <el-option label="header" value="header_contains" />
                  </el-select>
                  <el-input v-model="detailRequest._conditions[c.idx].value" size="small" placeholder="200" style="width: 200px" />
                  <span style="font-size: 12px; color: #909399">=</span>
                  <span style="font-size: 13px; font-weight: bold">{{ detailRequest._conditions[c.idx].value }}</span>
                  <span v-if="detailRequest._conditionResults?.[c.idx]?.isPass" class="match-icon match-pass">✓</span>
                  <span v-else-if="detailRequest._conditionResults?.[c.idx]" class="match-icon match-fail">✗</span>
                  <span v-else class="match-icon match-none">-</span>
                  <button class="delete-btn" @click="removeCondition(template.requests.indexOf(detailRequest), c.idx)">✕</button>
                </div>
              </div>

              <!-- Failed Conditions -->
              <div style="margin-bottom: 16px">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px">
                  <span style="font-size: 13px">请求失败条件断言 支持正则，任意条件满足即为请求失败</span>
                  <el-button size="small" type="danger" link @click="addFailCondition">ADD</el-button>
                </div>
                <div v-for="(c, cIdx) in failConditionIdxs" :key="'f'+cIdx" class="condition-row fail-row">
                  <el-select v-model="detailRequest._conditions[c.idx].type" size="small" style="width: 110px">
                    <el-option label="status" value="status_code" /><el-option label="content" value="body_contains" />
                    <el-option label="header" value="header_contains" />
                  </el-select>
                  <el-input v-model="detailRequest._conditions[c.idx].value" size="small" placeholder="403" style="width: 200px" />
                  <span style="font-size: 12px; color: #909399">=</span>
                  <span style="font-size: 13px; font-weight: bold">{{ detailRequest._conditions[c.idx].value }}</span>
                  <span v-if="detailRequest._conditionResults?.[c.idx]?.matched" class="match-icon match-fail">✗</span>
                  <span v-else-if="detailRequest._conditionResults?.[c.idx]" class="match-icon match-none-pass">-</span>
                  <span v-else class="match-icon match-none">-</span>
                  <button class="delete-btn" @click="removeCondition(template.requests.indexOf(detailRequest), c.idx)">✕</button>
                </div>
              </div>

              <!-- Variable Extraction -->
              <div>
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px">
                  <span style="font-size: 13px">变量提取 支持正则，支持括号表达式</span>
                  <el-button size="small" type="primary" link @click="addExtractor(template.requests.indexOf(detailRequest))">ADD</el-button>
                </div>
                <div v-for="(ext, eIdx) in getExtractorList(template.requests.indexOf(detailRequest))" :key="eIdx" class="condition-row extractor-row-preview">
                  <el-select v-model="ext.source" size="small" style="width: 110px">
                    <el-option label="content" value="content" />
                    <el-option label="status" value="status" />
                    <el-option label="header-location" value="header-location" />
                    <el-option label="header" value="header" />
                  </el-select>
                  <el-input v-model="ext.key" size="small" placeholder="变量名" style="width: 120px" />
                  <el-input v-model="ext.value" size="small" placeholder='(.+)' style="width: 200px" />
                  <span style="font-size: 12px; color: #909399; line-height: 32px; white-space: nowrap">Re:</span>
                  <span style="font-size: 12px; color: #303133; font-family: monospace; max-width: 300px; word-break: break-all; line-height: 32px">
                    {{ detailRequest._lastResponse ? (extractValue(detailRequest._lastResponse, ext.value, ext.source) || '-') : '-' }}
                  </span>
                  <button class="delete-btn" @click="removeExtractor(template.requests.indexOf(detailRequest), eIdx)">✕</button>
                </div>
              </div>

              <!-- Response Preview -->
              <div style="margin-top: 16px; border-top: 1px solid #ebeef5; padding-top: 16px">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px">
                  <span style="font-weight: bold; font-size: 13px">响应内容</span>
                  <el-button-group size="small">
                    <el-button :type="responseViewMode === 'render' ? 'primary' : ''" @click="responseViewMode = 'render'">网页预览</el-button>
                    <el-button :type="responseViewMode === 'source' ? 'primary' : ''" @click="responseViewMode = 'source'">源码</el-button>
                  </el-button-group>
                  <span style="font-size: 11px; color: #999">{{ responseContentType }}</span>
                </div>
                <!-- Webpage render mode -->
                <div v-if="responseViewMode === 'render' && isHtmlResponse" style="border: 1px solid #ebeef5; border-radius: 4px; overflow: hidden">
                  <iframe :srcdoc="detailRequest._lastResponse.body" style="width: 100%; height: 400px; border: none; background: #fff"></iframe>
                </div>
                <!-- JSON pretty print -->
                <div v-else-if="responseViewMode === 'render' && isJsonResponse" style="border: 1px solid #ebeef5; border-radius: 4px; padding: 12px; background: #fafafa; max-height: 400px; overflow: auto">
                  <pre style="margin: 0; font-family: monospace; font-size: 12px; white-space: pre-wrap; word-break: break-all">{{ formatResponseBody(detailRequest._lastResponse.body) }}</pre>
                </div>
                <!-- Other / source mode -->
                <pre v-else class="response-body" style="max-height: 400px">{{ detailRequest._lastResponse.body }}</pre>
              </div>
            </div>
          </el-tab-pane>

          <!-- 结果 / Headers -->
          <el-tab-pane label="结果 / Headers" name="headers">
            <div v-if="!detailRequest._lastResponse" style="text-align: center; padding: 40px; color: #999">先测试请求</div>
            <div v-else>
              <el-table :data="Object.entries(detailRequest._lastResponse.headers || {})" size="small" border>
                <el-table-column label="" width="40"><template #default><el-checkbox :model-value="true" disabled size="small" /></template></el-table-column>
                <el-table-column label="Name" min-width="200">
                  <template #default="{ row }"><span style="font-weight: bold; font-family: monospace; font-size: 12px">{{ row[0] }}</span></template>
                </el-table-column>
                <el-table-column label="Value" min-width="400">
                  <template #default="{ row }"><span style="font-family: monospace; font-size: 12px; word-break: break-all">{{ row[1] }}</span></template>
                </el-table-column>
              </el-table>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>

      <template #footer>
        <el-button @click="showDetail = false">关闭</el-button>
        <el-button type="primary" :loading="detailRequest?._testing" @click="detailRequest && testRequest(template.requests.indexOf(detailRequest))">▶ 测试</el-button>
        <el-button type="success" @click="showDetail = false">保存</el-button>
      </template>
    </el-dialog>

    <!-- cURL Import Dialog -->
    <el-dialog v-model="showCurlDialog" title="追加 cURL 命令" width="700px">
      <el-input v-model="curlInput" type="textarea" :rows="10" placeholder='curl -X POST https://api.example.com/data -H "Content-Type: application/json" -d &#123;"key": "value"&#125;' style="font-family: monospace" />
      <template #footer>
        <el-button @click="showCurlDialog = false">取消</el-button>
        <el-button type="primary" :loading="curlParsing" @click="importCurl">解析并追加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, nextTick, computed } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

interface HARHeader { name: string; value: string }
interface RequestCondition { type: string; operator: string; value: string; outcome: string }
interface HARRequestData {
  method: string; url: string; headers: HARHeader[]; extractors: Record<string, string>
  _activeTab: string; _bodyType: string; _bodyContent: string; _conditions: RequestCondition[]
  _testing: boolean; _lastResponse: any; _comment: string; _selected: boolean; _cookies: string; _conditionResults: any[]
}

const props = defineProps<{ initialData?: any }>()

const initialRequests = props.initialData?.requests || props.initialData?.template_data?.requests || []
const template = reactive({
  name: props.initialData?.name || '', description: props.initialData?.description || '',
  tags: props.initialData?.tags || [], is_public: props.initialData?.is_public || false,
  variables: props.initialData?.variables || {},
  requests: initialRequests.map((r: any) => parseRequestData(r)),
})

function parseRequestData(r: any): HARRequestData {
  return {
    method: r.method || 'GET', url: r.url || '', headers: r.headers || [], extractors: r.extractors || {},
    _activeTab: 'request', _bodyType: r.postData ? 'json' : 'none', _bodyContent: r.postData?.text || '',
    _conditions: r._conditions || [], _testing: false, _lastResponse: null,
    _comment: r._comment || r.comment || '', _selected: false, _cookies: '', _conditionResults: [],
  }
}

// --- Tag ---
const tagInputVisible = ref(false); const tagInputValue = ref(''); const tagInputRef = ref()
function showTagInput() { tagInputVisible.value = true; nextTick(() => tagInputRef.value?.focus()) }
function addTag() { if (tagInputValue.value) template.tags.push(tagInputValue.value); tagInputVisible.value = false; tagInputValue.value = '' }
function removeTag(tag: string) { template.tags = template.tags.filter((t: string) => t !== tag) }

// --- Variables ---
const variableList = ref(Object.entries(template.variables).map(([key, value]) => ({ key, value: String(value) })))
function addVariable() { variableList.value.push({ key: '', value: '' }) }
function removeVariable(i: number) { variableList.value.splice(i, 1) }

// --- Requests ---
const selectAll = ref(false); const selectedRows = ref<HARRequestData[]>([])
function toggleSelectAll(val: any) { template.requests.forEach((r: HARRequestData) => { r._selected = val }); updateSelectedRows() }
function updateSelectedRows() { selectedRows.value = template.requests.filter((r: HARRequestData) => r._selected) }
function getMethodType(method: string) { const m: Record<string, string> = { GET: 'success', POST: 'warning', PUT: 'info', DELETE: 'danger', PATCH: 'warning' }; return (m[method] || 'info') as any }

function addRequest() {
  const req: HARRequestData = { method: 'GET', url: '', headers: [], extractors: {}, _activeTab: 'request', _bodyType: 'none', _bodyContent: '', _conditions: [], _testing: false, _lastResponse: null, _comment: '', _selected: false, _cookies: '', _conditionResults: [] }
  template.requests.push(req); openDetail(req)
}

function addRequestsFromParsed(parsedList: any[]) {
  for (const p of parsedList) {
    const headers = Object.entries(p.headers || {}).map(([name, value]) => ({ name, value: String(value) }))
    const extractors: Record<string, string> = {}
    if (p.extract_variables) { for (const ext of p.extract_variables) { if (ext.name && ext.re) extractors[ext.name] = `regex:${ext.re}` } }
    const conditions: any[] = []
    if (p.success_asserts) { for (const a of p.success_asserts) { conditions.push({ type: a.from === 'status' ? 'status_code' : 'body_contains', operator: 'matches', value: a.re || '', outcome: 'success' }) } }
    if (p.failed_asserts) { for (const a of p.failed_asserts) { conditions.push({ type: a.from === 'status' ? 'status_code' : 'body_contains', operator: 'matches', value: a.re || '', outcome: 'failure' }) } }
    template.requests.push({ method: p.method || 'GET', url: p.url || '', headers, extractors, _activeTab: 'request', _bodyType: p.body_type || 'none', _bodyContent: p.body || '', _conditions: conditions, _testing: false, _lastResponse: null, _comment: p.name || '', _selected: false, _cookies: '', _conditionResults: [] })
  }
}

function removeRequest(index: number) { template.requests.splice(index, 1); updateSelectedRows() }
function deleteSelected() { template.requests = template.requests.filter((r: HARRequestData) => !r._selected); updateSelectedRows() }

// --- Detail Dialog ---
const showDetail = ref(false); const detailRequest = ref<HARRequestData | null>(null); const detailActiveTab = ref('request')
const responseViewMode = ref<'render' | 'source'>('render')
function openDetail(row: HARRequestData) { detailRequest.value = row; detailActiveTab.value = 'request'; responseViewMode.value = 'render'; showDetail.value = true }

// --- Response content type detection ---
const responseContentType = computed(() => {
  if (!detailRequest.value?._lastResponse) return ''
  const ct = detailRequest.value._lastResponse.headers?.['content-type'] || ''
  if (ct.includes('json')) return 'JSON'
  if (ct.includes('html')) return 'HTML'
  return ct.split(';')[0] || 'Text'
})
const isHtmlResponse = computed(() => responseContentType.value === 'HTML')
const isJsonResponse = computed(() => responseContentType.value === 'JSON')

// --- Headers ---
function addHeader(req: HARRequestData) { req.headers.push({ name: '', value: '' }) }
function removeHeader(req: HARRequestData, idx: number) { req.headers.splice(idx, 1) }

// --- Cookie list from response ---
const cookieList = computed(() => {
  if (!detailRequest.value?._lastResponse) return []
  const setCookies = detailRequest.value._lastResponse.headers?.['set-cookie']
  if (!setCookies) return []
  return setCookies.split(',').map((c: string) => {
    const parts = c.trim().split('=')
    return { name: parts[0]?.trim() || '', value: parts.slice(1).join('=').split(';')[0]?.trim() || '' }
  }).filter((c: any) => c.name)
})

// --- Preview conditions (return indices into original array) ---
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

function addSuccessCondition() {
  if (!detailRequest.value) return
  addCondition(template.requests.indexOf(detailRequest.value))
  const conds = detailRequest.value._conditions
  conds[conds.length - 1].outcome = 'success'
}

function addFailCondition() {
  if (!detailRequest.value) return
  addCondition(template.requests.indexOf(detailRequest.value))
  const conds = detailRequest.value._conditions
  conds[conds.length - 1].outcome = 'failure'
}

// --- Extractors ---
function getExtractorList(reqIndex: number) {
  const req = template.requests[reqIndex]
  if (!(req as any)._extractorList) {
    (req as any)._extractorList = Object.entries(req.extractors || {}).map(([key, value]) => {
      // Parse source from expression: "regex:pattern" -> source=content, "header:xxx" -> source=header
      let source = 'content'
      let pattern = String(value)
      if (pattern.startsWith('regex:')) { source = 'content'; pattern = pattern.slice(6) }
      else if (pattern.startsWith('header:')) { source = 'header'; pattern = pattern.slice(7) }
      else if (pattern === 'status') { source = 'status' }
      return { key, value: pattern, source, _index: '111' }
    })
  }
  return (req as any)._extractorList
}
function addExtractor(reqIndex: number) { getExtractorList(reqIndex).push({ key: '', value: '', source: 'content', _index: '111' }) }
function removeExtractor(reqIndex: number, idx: number) { getExtractorList(reqIndex).splice(idx, 1) }

function extractValue(response: any, expression: string, source?: string): any {
  if (!response || !expression) return null
  try {
    const body = response.body

    // Determine the text to search based on source
    let searchText = body
    if (source === 'status') return response.status_code
    if (source === 'header') {
      // Search in all headers
      searchText = Object.entries(response.headers || {}).map(([k, v]) => `${k}: ${v}`).join('\n')
    }
    // default source is 'content' (body)

    if (expression.startsWith('response.json()')) { const data = JSON.parse(body); const path = expression.replace('response.json()', ''); const segments = [...path.matchAll(/\["([^"]+)"\]|\[(\d+)\]/g)]; let current = data; for (const m of segments) { if (m[1]) current = current[m[1]]; else if (m[2]) current = current[parseInt(m[2])] }; return current }
    if (expression.startsWith('header:')) return response.headers[expression.slice(7).toLowerCase()]
    if (expression === 'status') return response.status_code
    if (expression.startsWith('regex:')) { const match = searchText.match(new RegExp(expression.slice(6))); return match ? (match[1] || match[0]) : null }
    const match = searchText.match(new RegExp(expression)); return match ? (match[1] || match[0]) : null
  } catch { return null }
}

// --- Conditions ---
function addCondition(reqIndex: number) { if (!template.requests[reqIndex]._conditions) template.requests[reqIndex]._conditions = []; template.requests[reqIndex]._conditions.push({ type: 'status_code', operator: 'eq', value: '200', outcome: 'success' }) }
function removeCondition(reqIndex: number, idx: number) { template.requests[reqIndex]._conditions.splice(idx, 1) }

function evaluateCondition(condition: any, response: any): boolean {
  if (!response || response.error) return false; let actual: any = null
  switch (condition.type) {
    case 'status_code': actual = response.status_code; break
    case 'body_contains': actual = response.body; break
    case 'body_regex': { const m = response.body.match(new RegExp(condition.value)); actual = m ? (m[1] || m[0]) : null; break }
    case 'header_contains': actual = Object.entries(response.headers || {}).map(([k, v]) => `${k}: ${v}`).join('\n'); break
    case 'json_field': try { const d = JSON.parse(response.body); const p = condition.value.split('.'); let c = d; for (const k of p) c = c?.[k]; actual = c } catch { actual = null }; break
  }
  switch (condition.operator) {
    case 'eq': return String(actual) === String(condition.value); case 'ne': return String(actual) !== String(condition.value)
    case 'gt': return Number(actual) > Number(condition.value); case 'lt': return Number(actual) < Number(condition.value)
    case 'contains': return String(actual).includes(String(condition.value)); case 'matches': return new RegExp(condition.value).test(String(actual))
    default: return false
  }
}

function evaluateConditions(reqIndex: number) {
  const req = template.requests[reqIndex]; const response = req._lastResponse; if (!response) return
  req._conditionResults = (req._conditions || []).map((c: any) => { const matched = evaluateCondition(c, response); return { ...c, matched, isPass: (c.outcome === 'success' && matched) || (c.outcome === 'failure' && !matched) } })
}

// --- Test ---
async function testRequest(index: number) {
  const req = template.requests[index]; if (!req.url) { ElMessage.warning('请输入请求 URL'); return }
  req._testing = true; req._lastResponse = null
  try {
    const headers: Record<string, string> = {}; for (const h of req.headers) { if (h.name) headers[h.name] = h.value }
    const res = await api.post('/api/test/test', { method: req.method, url: req.url, headers, body: req._bodyType !== 'none' ? req._bodyContent : null, body_type: req._bodyType, timeout: 30 })
    req._lastResponse = res.data; evaluateConditions(index)
    if (detailRequest.value === req) detailActiveTab.value = 'preview'
    ElMessage.success(`${res.data.status_code} - ${res.data.elapsed_ms.toFixed(0)}ms`)
  } catch (err: any) { ElMessage.error('请求测试失败: ' + (err.response?.data?.detail || err.message)) } finally { req._testing = false }
}

function formatResponseBody(body: string) { try { return JSON.stringify(JSON.parse(body), null, 2) } catch { return body } }

// --- HAR Import ---
function handleHarUpload(file: File) {
  const reader = new FileReader()
  reader.onload = async (e) => { try { const res = await api.post('/api/test/parse-har', { har_content: e.target?.result as string }); if (res.data.length === 0) { ElMessage.warning('HAR 文件中没有找到请求'); return }; addRequestsFromParsed(res.data); ElMessage.success(`已追加 ${res.data.length} 个请求`) } catch (err: any) { ElMessage.error('HAR 解析失败: ' + (err.response?.data?.detail || err.message)) } }
  reader.readAsText(file); return false
}

// --- cURL ---
const showCurlDialog = ref(false); const curlInput = ref(''); const curlParsing = ref(false)
async function importCurl() { if (!curlInput.value.trim()) { ElMessage.warning('请输入 cURL 命令'); return }; curlParsing.value = true; try { const res = await api.post('/api/test/parse-curl', { curl_command: curlInput.value }); addRequestsFromParsed([res.data]); showCurlDialog.value = false; curlInput.value = ''; ElMessage.success('cURL 已追加') } catch (err: any) { ElMessage.error('cURL 解析失败: ' + (err.response?.data?.detail || err.message)) } finally { curlParsing.value = false } }

// --- getData ---
function getData(): any {
  const vars: Record<string, string> = {}; for (const v of variableList.value) { if (v.key) vars[v.key] = v.value }
  return { name: template.name, description: template.description, tags: template.tags, is_public: template.is_public, variables: vars,
    template_data: { name: template.name, description: template.description,
      requests: template.requests.map((r: any) => ({ method: r.method, url: r.url, _comment: r._comment,
        headers: r.headers.filter((h: HARHeader) => h.name),
        postData: r._bodyType !== 'none' ? { mimeType: 'application/json', text: r._bodyContent } : undefined,
        extractors: ((r as any)._extractorList || []).reduce((acc: any, e: any) => { if (e.key) acc[e.key] = e.value; return acc }, {}) || r.extractors,
        _conditions: r._conditions || [],
      })),
    },
  }
}
defineExpose({ getData })
</script>

<style scoped>
.detail-dialog { min-height: 400px; }
.extractor-row { display: flex; align-items: center; gap: 4px; margin-bottom: 8px; flex-wrap: wrap; }
.regex-preview { display: flex; align-items: center; gap: 4px; margin-top: 4px; width: 100%; }
.preview-value { font-size: 12px; color: #67c23a; font-family: monospace; background: #f0f9eb; padding: 2px 6px; border-radius: 3px; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.response-body { max-height: 400px; overflow: auto; font-size: 12px; font-family: monospace; white-space: pre-wrap; word-break: break-all; margin: 0; padding: 8px; background: #fff; border-radius: 4px; }

/* Condition and extractor rows */
.condition-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  padding: 6px 8px;
  border-radius: 4px;
}
.success-row { background: #f5f7fa; }
.fail-row { background: #fef0f0; }
.extractor-row-preview { background: #f0f9eb; }

/* Match indicators */
.match-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  font-size: 13px;
  font-weight: bold;
  border-radius: 50%;
  flex-shrink: 0;
}
.match-pass {
  color: #fff;
  background: #67c23a;
}
.match-fail {
  color: #fff;
  background: #f56c6c;
}
.match-none {
  color: #c0c4cc;
  background: #f5f7fa;
  border: 1px solid #dcdfe6;
}
.match-none-pass {
  color: #409eff;
  background: #ecf5ff;
  border: 1px solid #b3d8ff;
}

/* Delete button with border */
.delete-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  font-size: 12px;
  color: #f56c6c;
  background: #fff;
  border: 1px solid #f56c6c;
  border-radius: 4px;
  cursor: pointer;
  padding: 0;
  flex-shrink: 0;
  transition: all 0.2s;
}
.delete-btn:hover {
  color: #fff;
  background: #f56c6c;
}
</style>
