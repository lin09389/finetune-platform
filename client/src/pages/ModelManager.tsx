import { useEffect, useState, useMemo } from 'react'
import { Table, Button, Space, Tag, Modal, Form, Select, Input, message, Popconfirm, Empty, Progress, Tabs } from 'antd'
import { DeleteOutlined, DownloadOutlined, FolderOpenOutlined, SearchOutlined, ReloadOutlined, ImportOutlined, DatabaseOutlined } from '@ant-design/icons'
import { useAppStore } from '../store/appStore'
import { getModelList, downloadModel, deleteModel, importModelFromModelScope } from '../services/api'
import type { ModelInfo } from '../types'
import { MotionList, MotionItem } from '../components/shared/MotionWrapper'
import styles from './ModelManager.module.css'
import glassStyles from '../components/shared/GlassCard.module.css'

const popularModels = [
  { value: 'Qwen/Qwen2.5-0.5B-Instruct', label: 'Qwen2.5-0.5B (推荐4GB)' },
  { value: 'Qwen/Qwen2.5-1.5B-Instruct', label: 'Qwen2.5-1.5B (推荐6GB)' },
  { value: 'Qwen/Qwen2.5-7B-Instruct', label: 'Qwen2.5-7B (推荐16GB)' },
  { value: 'THUDM/chatglm3-6b', label: 'ChatGLM3-6B (推荐13GB)' },
  { value: '01ai/Yi-1.5-6B-Chat', label: 'Yi-1.5-6B (推荐13GB)' },
  { value: 'damo/nlp_corom_sentence-embedding_chinese-base', label: '中文嵌入模型 (RAG用)' },
]

const quantizeOptions = [
  { value: 4, label: 'INT4 (最低显存)' },
  { value: 8, label: 'INT8 (均衡)' },
  { value: 16, label: 'FP16 (高精度)' },
]

export default function ModelManager() {
  const { models, setModels, removeModel, addModel, backendStatus } = useAppStore()
  const [loading, setLoading] = useState(false)
  const [downloadModalVisible, setDownloadModalVisible] = useState(false)
  const [importModelScopeModalVisible, setImportModelScopeModalVisible] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [importingModelModelScope, setImportingModelScope] = useState(false)
  const [downloadProgress, setDownloadProgress] = useState(0)
  const [searchText, setSearchText] = useState('')
  const [downloadForm] = Form.useForm()
  const [importModelScopeForm] = Form.useForm()

  const fetchModels = async () => {
    if (backendStatus !== 'connected') return
    setLoading(true)
    try {
      const list = await getModelList()
      setModels(list)
    } catch (error) {
      message.error('获取模型列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchModels()
  }, [backendStatus])

  const filteredModels = useMemo(() => {
    if (!searchText) return models
    const search = searchText.toLowerCase()
    return models.filter(m => 
      m.name.toLowerCase().includes(search) ||
      m.id.toLowerCase().includes(search)
    )
  }, [models, searchText])

  const handleDownload = async (values: { model: string; quantize: number }) => {
    setDownloading(true)
    setDownloadProgress(0)

    const progressInterval = setInterval(() => {
      setDownloadProgress(p => Math.min(p + 10, 90))
    }, 1000)

    try {
      const result = await downloadModel(values.model, { quantize: values.quantize })
      clearInterval(progressInterval)
      setDownloadProgress(100)

      message.success('模型下载成功')
      addModel(result)
      setDownloadModalVisible(false)
      downloadForm.resetFields()
      setTimeout(() => setDownloadProgress(0), 500)
    } catch (error: unknown) {
      clearInterval(progressInterval)
      setDownloadProgress(0)
      const errorMsg = error instanceof Error ? error.message : '模型下载失败'
      message.error(errorMsg)
    } finally {
      setDownloading(false)
    }
  }

  const handleImportModelScope = async (values: { model_name: string; modelscope_path?: string }) => {
    setImportingModelScope(true)
    try {
      const result = await importModelFromModelScope(values.model_name, values.modelscope_path)
      message.success('ModelScope 模型导入成功')
      addModel(result)
      setImportModelScopeModalVisible(false)
      importModelScopeForm.resetFields()
    } catch (error: unknown) {
      const errorMsg = error instanceof Error ? error.message : '导入失败'
      message.error(errorMsg)
    } finally {
      setImportingModelScope(false)
    }
  }

  const handleDelete = async (modelId: string) => {
    try {
      await deleteModel(modelId)
      removeModel(modelId)
      message.success('模型删除成功')
    } catch (error) {
      message.error('删除失败')
      fetchModels()
    }
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024 * 1024) {
      return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    }
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
  }

  const columns = [
    {
      title: '模型名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: ModelInfo) => (
        <Space key={record.id}>
          {text}
          {record.quantized && <Tag color="blue">INT{record.quantized}</Tag>}
        </Space>
      )
    },
    {
      title: '路径',
      dataIndex: 'path',
      key: 'path',
      ellipsis: true,
    },
    {
      title: '大小',
      dataIndex: 'size',
      key: 'size',
      render: (size: number) => formatSize(size),
      width: 100,
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      render: (type: string) => (
        <Tag color={type === 'base' ? 'default' : type === 'lora' ? 'green' : type === 'merged' ? 'orange' : 'default'}>
          {type === 'base' ? '基础模型' : type === 'lora' ? 'LoRA' : type === 'merged' ? '已合并' : type}
        </Tag>
      ),
      width: 100,
    },
    {
      title: '下载时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
      render: (date: string) => new Date(date).toLocaleString('zh-CN'),
      width: 170,
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: ModelInfo) => (
        <Space key={record.id}>
          <Button
            type="link"
            size="small"
            icon={<FolderOpenOutlined />}
            onClick={() => window.electronAPI?.openFolder(record.path)}
          >
            打开
          </Button>
          <Popconfirm
            title="确认删除此模型?"
            description="删除后需要重新下载"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
      width: 150,
    }
  ]

  return (
    <MotionList className={styles.container} stagger={0.08}>
      <MotionItem>
      <div className={`${glassStyles.glassCard} ${styles.headerCard}`}>
        <h1 className={styles.title}>
          <DatabaseOutlined />
          模型管理
        </h1>
        <Space>
          <Input
            placeholder="搜索模型..."
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
            style={{ width: 240 }}
            className="glass-input"
            allowClear
          />
          <Button
            icon={<ReloadOutlined />}
            onClick={fetchModels}
            loading={loading}
          >
            刷新
          </Button>
          <Button
            type="primary"
            icon={<DownloadOutlined />}
            onClick={() => setDownloadModalVisible(true)}
          >
            下载模型
          </Button>
          <Button
            icon={<ImportOutlined />}
            onClick={() => setImportModelScopeModalVisible(true)}
          >
            导入 ModelScope
          </Button>
        </Space>
      </div>
      </MotionItem>

      <MotionItem>
      <div className={`${glassStyles.glassCard} ${styles.tableCard}`}>
        {backendStatus !== 'connected' ? (
          <Empty 
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="后端服务未连接，请先启动应用" 
            style={{ margin: 'auto' }}
          />
        ) : (
          <Table
            columns={columns}
            dataSource={filteredModels}
            rowKey="id"
            loading={loading}
            locale={{ 
              emptyText: (
                <Empty 
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={
                    <div>
                      <div>暂无模型</div>
                      <div style={{ fontSize: 12, color: '#999', marginTop: 8 }}>
                        点击下载模型开始使用
                      </div>
                    </div>
                  }
                >
                  <Button type="primary" icon={<DownloadOutlined />} onClick={() => setDownloadModalVisible(true)}>
                    下载模型
                  </Button>
                </Empty>
              )
            }}
          />
        )}
      </div>
      </MotionItem>

      <Modal
        title="下载模型（魔搭社区）"
        open={downloadModalVisible}
        onCancel={() => {
          setDownloadModalVisible(false)
          downloadForm.resetFields()
          setDownloadProgress(0)
        }}
        footer={null}
        width={500}
        closable={!downloading}
        maskClosable={!downloading}
        className="glass-modal"
      >
        <Form
          form={downloadForm}
          layout="vertical"
          onFinish={handleDownload}
          initialValues={{ quantize: 4 }}
          style={{ marginTop: 24 }}
        >
          <Form.Item
            label="选择模型"
            name="model"
            rules={[{ required: true, message: '请选择要下载的模型' }]}
          >
            <Select
              placeholder="选择模型"
              options={popularModels}
              showSearch
              filterOption={(input, option) =>
                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
              disabled={downloading}
            />
          </Form.Item>

          <Form.Item
            label="量化级别"
            name="quantize"
            rules={[{ required: true }]}
          >
            <Select options={quantizeOptions} disabled={downloading} />
          </Form.Item>

          {downloading && (
            <div style={{ marginBottom: 24 }}>
              <Progress percent={downloadProgress} status="active" strokeColor="var(--accent-primary)" />
              <div style={{ textAlign: 'center', color: 'var(--text-secondary)', fontSize: 13, marginTop: 8 }}>
                正在下载模型，请稍候...
              </div>
            </div>
          )}

          <Form.Item style={{ marginBottom: 0 }}>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => setDownloadModalVisible(false)} disabled={downloading}>
                取消
              </Button>
              <Button type="primary" htmlType="submit" loading={downloading}>
                {downloading ? '下载中...' : '开始下载'}
              </Button>
            </Space>
          </Form.Item>
        </Form>

        <div className={styles.modalDescription} style={{ marginTop: 24 }}>
          <b style={{ color: 'var(--text-primary)' }}>显存建议：</b>
          <ul style={{ margin: '8px 0 0', paddingLeft: 20, color: 'var(--text-secondary)' }}>
            <li>INT4: 6GB 显存可运行 7B 模型</li>
            <li>INT8: 10GB 显存可运行 7B 模型</li>
            <li>FP16: 13GB+ 显存可运行 7B 模型</li>
          </ul>
        </div>
      </Modal>

      <Modal
        title="导入 ModelScope 模型"
        open={importModelScopeModalVisible}
        onCancel={() => {
          setImportModelScopeModalVisible(false)
          importModelScopeForm.resetFields()
        }}
        footer={null}
        width={550}
        closable={!importingModelModelScope}
        maskClosable={!importingModelModelScope}
        className="glass-modal"
      >
        <Tabs
          items={[
            {
              key: 'qwen35',
              label: 'Qwen3.5 2B',
              children: (
                <div style={{ paddingTop: 16 }}>
                  <p style={{ marginBottom: 16, color: 'var(--text-secondary)' }}>
                    从魔搭社区（ModelScope）导入已下载的 <b style={{ color: 'var(--text-primary)' }}>Qwen3.5 2B</b> 模型。
                  </p>
                  <div className={styles.modalDescription}>
                    <b style={{ color: 'var(--text-primary)' }}>默认路径：</b><br />
                    <code style={{ fontSize: 12, color: 'var(--accent-primary)', marginTop: 8, display: 'block', wordBreak: 'break-all' }}>
                      C:\Users\{'<用户名>'}\.cache\modelscope\hub\models\Qwen\Qwen3.5-2B
                    </code>
                  </div>
                </div>
              )
            },
            {
              key: 'custom',
              label: '自定义路径',
              children: (
                <div style={{ paddingTop: 16 }}>
                  <p style={{ marginBottom: 16, color: 'var(--text-secondary)' }}>
                    指定 ModelScope 模型目录的自定义路径。
                  </p>
                </div>
              )
            }
          ]}
        />

        <Form
          form={importModelScopeForm}
          layout="vertical"
          onFinish={handleImportModelScope}
          initialValues={{ model_name: 'Qwen3.5-2B' }}
          style={{ marginTop: 16 }}
        >
          <Form.Item
            label="模型名称"
            name="model_name"
            rules={[{ required: true, message: '请输入模型名称' }]}
          >
            <Input placeholder="如：Qwen3.5-2B" disabled={importingModelModelScope} />
          </Form.Item>

          <Form.Item
            label="ModelScope 路径（可选）"
            name="modelscope_path"
            tooltip="不填则使用默认路径"
          >
            <Input
              placeholder="C:\Users\...\AppData\Local\modelscope\hub\models\Qwen\Qwen3.5-2B"
              disabled={importingModelModelScope}
            />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0 }}>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => setImportModelScopeModalVisible(false)} disabled={importingModelModelScope}>
                取消
              </Button>
              <Button type="primary" htmlType="submit" loading={importingModelModelScope}>
                {importingModelModelScope ? '导入中...' : '开始导入'}
              </Button>
            </Space>
          </Form.Item>
        </Form>

        <div className={styles.modalDescription} style={{ marginTop: 24 }}>
          <b style={{ color: 'var(--text-primary)' }}>导入说明：</b>
          <ul style={{ margin: '8px 0 0', paddingLeft: 20, fontSize: 13, color: 'var(--text-secondary)' }}>
            <li>确保模型已从魔搭社区下载完成</li>
            <li>导入过程会复制模型文件到项目目录</li>
            <li>导入完成后可在模型列表中查看</li>
            <li>Qwen3.5 2B 约 4GB，建议 8GB+ 显存使用 INT4 量化</li>
          </ul>
        </div>
      </Modal>
    </MotionList>
  )
}
