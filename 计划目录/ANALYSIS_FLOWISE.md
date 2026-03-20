# 🔍 Flowise 可视化工作流架构深度分析

## 📁 项目结构分析

```
flowise/
├── packages/
│   │
│   ├── ui/                     # React 前端
│   │   ├── src/
│   │   │   ├── views/
│   │   │   │   ├── canvas/           # 画布页面
│   │   │   │   │   └── Canvas.tsx    # 主画布组件
│   │   │   │   ├── chatbot/          # 聊天机器人页面
│   │   │   │   └── settings/         # 设置页面
│   │   │   ├── components/
│   │   │   │   ├── nodes/            # 节点组件
│   │   │   │   │   ├── InputNode.tsx
│   │   │   │   │   ├── LLMNode.tsx
│   │   │   │   │   ├── RAGNode.tsx
│   │   │   │   │   └── OutputNode.tsx
│   │   │   │   ├── edges/            # 边组件
│   │   │   │   └── toolbar/          # 工具栏
│   │   │   ├── stores/               # 状态管理
│   │   │   │   └── canvasStore.ts
│   │   │   └── services/             # API 服务
│   │   │       └── workflowApi.ts
│   │   └── package.json
│   │
│   ├── components/               # 节点组件库
│   │   ├── nodes/
│   │   │   ├── inputs/
│   │   │   │   ├── TextInputNode.ts
│   │   │   │   └── FileInputNode.ts
│   │   │   ├── llms/
│   │   │   │   ├── ChatOpenAI.ts
│   │   │   │   ├── ChatOllama.ts
│   │   │   │   └── HuggingFaceNode.ts
│   │   │   ├── chains/
│   │   │   │   ├── ConversationChain.ts
│   │   │   │   └── RetrievalChain.ts
│   │   │   ├── vectorstores/
│   │   │   │   ├── Chroma.ts
│   │   │   │   └── Pinecone.ts
│   │   │   ├── embeddings/
│   │   │   │   └── OpenAIEmbeddings.ts
│   │   │   └── output/
│   │   │       └── ResponseNode.ts
│   │   ├── index.ts              # 组件注册
│   │   └── package.json
│   │
│   └── server/                   # 执行引擎
│       ├── src/
│       │   ├── services/
│       │   │   ├── workflowExecutor.ts   # 工作流执行器
│       │   │   ├── graphBuilder.ts       # 图构建器
│       │   │   └── nodeExecutor.ts       # 节点执行器
│       │   ├── utils/
│       │   │   ├── topologicalSort.ts    # 拓扑排序
│       │   │   └── dataMapper.ts         # 数据映射
│       │   └── index.ts
│       └── package.json
│
├── docker/
├── package.json
└── README.md
```

---

## 🎨 可视化编辑器实现

### 1. React Flow 画布组件

```tsx
// packages/ui/src/views/canvas/Canvas.tsx

import React, { useCallback, useState } from 'react';
import ReactFlow, {
  Node,
  Edge,
  addEdge,
  useNodesState,
  useEdgesState,
  Controls,
  Background,
  MiniMap,
  Connection,
} from 'reactflow';
import 'reactflow/dist/style.css';

import InputNode from '../../components/nodes/InputNode';
import LLMNode from '../../components/nodes/LLMNode';
import OutputNode from '../../components/nodes/OutputNode';

const nodeTypes = {
  input: InputNode,
  llm: LLMNode,
  output: OutputNode,
};

export default function Canvas() {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);

  // 处理连接
  const onConnect = useCallback(
    (params: Connection) => {
      setEdges((eds) => addEdge({
        ...params,
        type: 'smoothstep',
        animated: true,
      }, eds));
    },
    [setEdges]
  );

  // 添加节点
  const addNode = (type: string, position: { x: number; y: number }) => {
    const newNode: Node = {
      id: `${type}_${Date.now()}`,
      type,
      position,
      data: {
        label: `${type} Node`,
        config: {},
      },
    };
    setNodes((nds) => [...nds, newNode]);
  };

  // 更新节点配置
  const updateNodeConfig = (nodeId: string, config: Record<string, any>) => {
    setNodes((nds) =>
      nds.map((node) => {
        if (node.id === nodeId) {
          return {
            ...node,
            data: {
              ...node.data,
              config,
            },
          };
        }
        return node;
      })
    );
  };

  // 执行工作流
  const executeWorkflow = async () => {
    try {
      const response = await fetch('/api/workflow/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nodes, edges }),
      });
      const result = await response.json();
      console.log('Execution result:', result);
    } catch (error) {
      console.error('Execution failed:', error);
    }
  };

  return (
    <div style={{ width: '100%', height: '100vh' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={(_, node) => setSelectedNode(node)}
        nodeTypes={nodeTypes}
        fitView
        snapToGrid
        snapGrid={[15, 15]}
      >
        <Controls />
        <MiniMap />
        <Background gap={15} size={1} />
      </ReactFlow>

      {/* 节点配置面板 */}
      {selectedNode && (
        <NodeConfigPanel
          node={selectedNode}
          onUpdate={(config) => updateNodeConfig(selectedNode.id, config)}
        />
      )}

      {/* 执行按钮 */}
      <button onClick={executeWorkflow} className="execute-btn">
        运行工作流
      </button>
    </div>
  );
}
```

---

### 2. 自定义节点组件

```tsx
// packages/ui/src/components/nodes/LLMNode.tsx

import React, { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';

interface LLMNodeData {
  label: string;
  config: {
    model?: string;
    temperature?: number;
    maxTokens?: number;
  };
}

const LLMNode: React.FC<NodeProps<LLMNodeData>> = ({ data, selected }) => {
  return (
    <div
      className={`node llm-node ${selected ? 'selected' : ''}`}
      style={{
        width: 200,
        padding: 12,
        background: '#fff',
        border: '1px solid #ddd',
        borderRadius: 8,
        boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
      }}
    >
      {/* 输入 Handle */}
      <Handle
        type="target"
        position={Position.Left}
        style={{
          background: '#555',
          width: 10,
          height: 10,
        }}
      />

      {/* 节点头部 */}
      <div className="node-header">
        <div className="node-icon">🤖</div>
        <div className="node-label">{data.label}</div>
      </div>

      {/* 节点内容 */}
      <div className="node-content">
        <div className="config-item">
          <label>模型:</label>
          <span className="value">{data.config.model || '未设置'}</span>
        </div>
        <div className="config-item">
          <label>温度:</label>
          <span className="value">{data.config.temperature ?? 0.7}</span>
        </div>
      </div>

      {/* 输出 Handle */}
      <Handle
        type="source"
        position={Position.Right}
        style={{
          background: '#1677ff',
          width: 10,
          height: 10,
        }}
      />
    </div>
  );
};

export default memo(LLMNode);
```

---

### 3. 节点配置面板

```tsx
// packages/ui/src/components/NodeConfigPanel.tsx

import React from 'react';
import { Node } from 'reactflow';
import { Input, Select, Slider, Button } from 'antd';

interface NodeConfigPanelProps {
  node: Node;
  onUpdate: (config: Record<string, any>) => void;
  onClose: () => void;
}

export default function NodeConfigPanel({
  node,
  onUpdate,
  onClose,
}: NodeConfigPanelProps) {
  const handleChange = (key: string, value: any) => {
    onUpdate({
      ...node.data.config,
      [key]: value,
    });
  };

  return (
    <div className="config-panel">
      <div className="config-header">
        <h3>{node.data.label} 配置</h3>
        <Button onClick={onClose}>关闭</Button>
      </div>

      <div className="config-body">
        {node.type === 'llm' && (
          <>
            <div className="config-item">
              <label>模型</label>
              <Select
                value={node.data.config.model}
                onChange={(value) => handleChange('model', value)}
                options={[
                  { label: 'Llama 2 7B', value: 'llama2:7b' },
                  { label: 'Qwen 7B', value: 'qwen:7b' },
                  { label: 'Mistral 7B', value: 'mistral:7b' },
                ]}
              />
            </div>

            <div className="config-item">
              <label>温度 (Temperature)</label>
              <Slider
                min={0}
                max={2}
                step={0.1}
                value={node.data.config.temperature ?? 0.7}
                onChange={(value) => handleChange('temperature', value)}
                marks={{
                  0: '精确',
                  0.7: '平衡',
                  2: '创意',
                }}
              />
            </div>

            <div className="config-item">
              <label>最大 Token 数</label>
              <Input
                type="number"
                value={node.data.config.maxTokens}
                onChange={(e) =>
                  handleChange('maxTokens', parseInt(e.target.value))
                }
              />
            </div>
          </>
        )}

        {node.type === 'input' && (
          <>
            <div className="config-item">
              <label>输入类型</label>
              <Select
                value={node.data.config.inputType}
                onChange={(value) => handleChange('inputType', value)}
                options={[
                  { label: '文本输入', value: 'text' },
                  { label: '文件上传', value: 'file' },
                  { label: '固定值', value: 'fixed' },
                ]}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
```

---

## ⚙️ 执行引擎实现

### 1. 图构建器

```typescript
// packages/server/src/services/graphBuilder.ts

import { Node, Edge } from 'reactflow';

interface GraphNode {
  id: string;
  type: string;
  data: any;
  inputs: string[];
  outputs: string[];
}

export class GraphBuilder {
  private nodes: Map<string, GraphNode> = new Map();
  private adjacencyList: Map<string, string[]> = new Map();

  constructor(nodes: Node[], edges: Edge[]) {
    this.buildGraph(nodes, edges);
  }

  private buildGraph(nodes: Node[], edges: Edge[]) {
    // 初始化节点
    for (const node of nodes) {
      this.nodes.set(node.id, {
        id: node.id,
        type: node.type,
        data: node.data,
        inputs: [],
        outputs: [],
      });
      this.adjacencyList.set(node.id, []);
    }

    // 建立边关系
    for (const edge of edges) {
      const sourceOutputs = this.adjacencyList.get(edge.source)!;
      sourceOutputs.push(edge.target);

      const targetNode = this.nodes.get(edge.target)!;
      targetNode.inputs.push(edge.source);

      const sourceNode = this.nodes.get(edge.source)!;
      sourceNode.outputs.push(edge.target);
    }
  }

  getNodes(): GraphNode[] {
    return Array.from(this.nodes.values());
  }

  getInputs(nodeId: string): string[] {
    return this.nodes.get(nodeId)?.inputs || [];
  }

  getOutputs(nodeId: string): string[] {
    return this.adjacencyList.get(nodeId) || [];
  }
}
```

---

### 2. 拓扑排序

```typescript
// packages/server/src/utils/topologicalSort.ts

import { GraphBuilder } from '../services/graphBuilder';

export function topologicalSort(graph: GraphBuilder): string[] {
  const nodes = graph.getNodes();
  const visited = new Set<string>();
  const result: string[] = [];

  function visit(nodeId: string) {
    if (visited.has(nodeId)) return;

    visited.add(nodeId);

    // 先访问所有依赖的节点
    const inputs = graph.getInputs(nodeId);
    for (const inputId of inputs) {
      visit(inputId);
    }

    result.push(nodeId);
  }

  // 访问所有节点
  for (const node of nodes) {
    visit(node.id);
  }

  return result;
}

// 检测环
export function hasCycle(graph: GraphBuilder): boolean {
  const nodes = graph.getNodes();
  const visiting = new Set<string>();
  const visited = new Set<string>();

  function dfs(nodeId: string): boolean {
    if (visiting.has(nodeId)) return true; // 发现环
    if (visited.has(nodeId)) return false;

    visiting.add(nodeId);

    const outputs = graph.getOutputs(nodeId);
    for (const outputId of outputs) {
      if (dfs(outputId)) return true;
    }

    visiting.delete(nodeId);
    visited.add(nodeId);

    return false;
  }

  for (const node of nodes) {
    if (dfs(node.id)) return true;
  }

  return false;
}
```

---

### 3. 工作流执行器

```typescript
// packages/server/src/services/workflowExecutor.ts

import { GraphBuilder } from './graphBuilder';
import { topologicalSort } from '../utils/topologicalSort';
import { executeNode } from './nodeExecutor';

interface ExecutionResult {
  nodeId: string;
  output: any;
  error?: string;
}

export class WorkflowExecutor {
  private graph: GraphBuilder;
  private results: Map<string, any> = new Map();

  constructor(nodes: any[], edges: any[]) {
    this.graph = new GraphBuilder(nodes, edges);
  }

  async execute(inputData: any): Promise<ExecutionResult[]> {
    // 1. 检测环
    if (hasCycle(this.graph)) {
      throw new Error('工作流中存在循环依赖');
    }

    // 2. 拓扑排序确定执行顺序
    const executionOrder = topologicalSort(this.graph);

    // 3. 依次执行节点
    const results: ExecutionResult[] = [];

    for (const nodeId of executionOrder) {
      const node = this.graph.getNodes().find(n => n.id === nodeId);
      if (!node) continue;

      try {
        // 收集输入
        const inputs = this.collectInputs(nodeId);

        // 如果是输入节点，使用初始输入
        if (node.type === 'input') {
          this.results.set(nodeId, inputData);
        } else {
          // 执行节点
          const output = await executeNode(node, inputs);
          this.results.set(nodeId, output);
        }

        results.push({ nodeId, output: this.results.get(nodeId) });
      } catch (error) {
        results.push({
          nodeId,
          output: null,
          error: (error as Error).message,
        });
        throw error;
      }
    }

    return results;
  }

  private collectInputs(nodeId: string): any[] {
    const inputIds = this.graph.getInputs(nodeId);
    return inputIds.map(id => this.results.get(id));
  }
}
```

---

### 4. 节点执行器

```typescript
// packages/server/src/services/nodeExecutor.ts

import { GraphNode } from './graphBuilder';

export async function executeNode(
  node: GraphNode,
  inputs: any[]
): Promise<any> {
  switch (node.type) {
    case 'input':
      return executeInputNode(node, inputs);

    case 'llm':
      return executeLLMNode(node, inputs);

    case 'rag':
      return executeRAGNode(node, inputs);

    case 'output':
      return executeOutputNode(node, inputs);

    default:
      throw new Error(`未知的节点类型：${node.type}`);
  }
}

async function executeInputNode(
  node: GraphNode,
  inputs: any[]
): Promise<any> {
  // 输入节点直接返回配置值
  return node.data.config.value || inputs[0];
}

async function executeLLMNode(
  node: GraphNode,
  inputs: any[]
): Promise<any> {
  const prompt = inputs[0];
  const config = node.data.config;

  // 调用 LLM
  const response = await callLLM({
    model: config.model,
    prompt,
    temperature: config.temperature,
    maxTokens: config.maxTokens,
  });

  return response.content;
}

async function executeRAGNode(
  node: GraphNode,
  inputs: any[]
): Promise<any> {
  const query = inputs[0];
  const config = node.data.config;

  // 向量检索
  const results = await vectorSearch({
    query,
    collection: config.collection,
    topK: config.topK || 5,
  });

  return {
    context: results.map(r => r.text).join('\n'),
    sources: results,
  };
}

async function executeOutputNode(
  node: GraphNode,
  inputs: any[]
): Promise<any> {
  // 输出节点返回所有输入
  return {
    output: inputs,
    format: node.data.config.format,
  };
}

// 调用 LLM 的辅助函数
async function callLLM(config: {
  model: string;
  prompt: string;
  temperature?: number;
  maxTokens?: number;
}): Promise<{ content: string }> {
  // 这里可以调用不同的推理后端
  const response = await fetch('http://localhost:11434/api/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: config.model,
      prompt: config.prompt,
      temperature: config.temperature,
      max_tokens: config.maxTokens,
    }),
  });

  const data = await response.json();
  return { content: data.response };
}

// 向量检索辅助函数
async function vectorSearch(config: {
  query: string;
  collection: string;
  topK: number;
}): Promise<Array<{ text: string; score: number }>> {
  // 调用向量数据库
  const response = await fetch('/api/vector/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });

  return response.json();
}
```

---

## 🎯 节点类型设计

### 节点注册系统

```typescript
// packages/components/nodes/index.ts

import { NodeDefinition } from './types';
import { TextInputNode } from './inputs/TextInputNode';
import { LLMNode } from './llms/LLMNode';
import { RAGNode } from './chains/RAGNode';
import { OutputNode } from './output/OutputNode';

export const nodeRegistry: Record<string, NodeDefinition> = {
  textInput: {
    type: 'textInput',
    name: '文本输入',
    icon: '📝',
    category: '输入',
    component: TextInputNode,
    config: {
      value: { type: 'string', default: '' },
      placeholder: { type: 'string', default: '输入文本...' },
    },
  },

  chatLLM: {
    type: 'chatLLM',
    name: '聊天模型',
    icon: '🤖',
    category: 'LLM',
    component: LLMNode,
    config: {
      model: { type: 'select', options: ['llama2:7b', 'qwen:7b'] },
      temperature: { type: 'number', min: 0, max: 2, step: 0.1 },
      maxTokens: { type: 'number', default: 1024 },
    },
  },

  ragRetrieval: {
    type: 'ragRetrieval',
    name: 'RAG 检索',
    icon: '🔍',
    category: 'RAG',
    component: RAGNode,
    config: {
      collection: { type: 'string' },
      topK: { type: 'number', default: 5 },
    },
  },

  textOutput: {
    type: 'textOutput',
    name: '文本输出',
    icon: '📤',
    category: '输出',
    component: OutputNode,
    config: {
      format: { type: 'select', options: ['text', 'json', 'markdown'] },
    },
  },
};

export function getNodeDefinition(type: string): NodeDefinition | null {
  return nodeRegistry[type] || null;
}
```

---

## 📋 实现检查清单

### 可视化编辑器
- [ ] React Flow 集成
- [ ] 节点拖拽
- [ ] 节点连接
- [ ] 画布缩放/平移
- [ ] 节点配置面板
- [ ] 工具栏（添加节点）

### 节点系统
- [ ] 输入节点
- [ ] LLM 节点
- [ ] RAG 节点
- [ ] 输出节点
- [ ] 节点注册表
- [ ] 可插拔设计

### 执行引擎
- [ ] 图构建器
- [ ] 拓扑排序
- [ ] 环检测
- [ ] 节点执行器
- [ ] 错误处理
- [ ] 执行日志

### 数据流
- [ ] 节点间数据传递
- [ ] 输入输出映射
- [ ] 数据类型检查
- [ ] 数据转换

---

**下一步**: 根据这个分析，我们可以设计自己的工作流系统！
