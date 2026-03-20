# 🔍 AnythingLLM 核心代码深度分析

## 📁 项目结构分析

```
anything-llm/
├── server/                   # 后端服务 (Node.js + Express)
│   ├── controllers/          # 控制器层
│   │   ├── documentController.js    # 文档管理
│   │   ├── workspaceController.js   # 工作空间管理
│   │   ├── chatController.js        # 聊天 API
│   │   └── vectorController.js      # 向量检索
│   ├── models/             # 数据模型
│   │   ├── Workspace.js           # 工作空间模型
│   │   ├── Document.js            # 文档模型
│   │   └── ChatHistory.js         # 聊天历史模型
│   ├── utils/              # 工具函数
│   │   ├── embeddings/            # 向量化模块
│   │   ├── files/                 # 文件处理
│   │   └── helpers/               # 辅助函数
│   ├── storage/            # 存储层
│   │   ├── documents/             # 文档存储
│   │   └── vector-cache/          # 向量缓存
│   └── index.js            # 入口文件
│
├── collector/                # 文档收集器
│   ├── processors/           # 文档处理器
│   │   ├── pdfProcessor.js          # PDF 解析
│   │   ├── textProcessor.js         # 文本解析
│   │   └── markdownProcessor.js     # Markdown 解析
│   └── chunker/              # 文本分块
│       └── TextChunker.js
│
├── embed/                    # 向量化服务
│   ├── embedders/            # 嵌入模型
│   │   ├── localEmbedder.js         # 本地嵌入
│   │   └── openAiEmbedder.js        # OpenAI 嵌入
│   └── index.js
│
├── runtime/                  # 运行时管理
│   ├── models/               # 模型管理
│   └── backends/             # 推理后端
│
├── frontend/                 # React 前端
│   ├── src/
│   │   ├── components/       # 组件
│   │   │   ├── Workspace/           # 工作空间组件
│   │   │   ├── Chat/                # 聊天组件
│   │   │   └── Documents/           # 文档管理组件
│   │   ├── pages/            # 页面
│   │   └── services/         # API 服务
│   └── package.json
│
└── package.json
```

---

## 🔧 核心模块详解

### 1. 文档处理流程

#### 文档上传控制器
```javascript
// server/controllers/documentController.js

const { ProcessDocument } = require('../utils/files');
const { embedText } = require('../embed');

exports.uploadDocument = async (req, res) => {
  const { workspaceId } = req.params;
  const { file } = req.files;
  
  try {
    // 1. 保存原始文件
    const filePath = await saveFile(file, workspaceId);
    
    // 2. 解析文档内容
    const content = await parseDocument(filePath);
    
    // 3. 文本分块
    const chunks = await chunkText(content);
    
    // 4. 向量化
    const embeddings = await embedText(chunks);
    
    // 5. 存储到向量数据库
    await storeVectors(workspaceId, embeddings, chunks);
    
    // 6. 更新文档元数据
    await Document.create({
      workspaceId,
      filePath,
      chunkCount: chunks.length,
    });
    
    res.json({ success: true, message: '文档处理完成' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
};
```

#### PDF 解析器
```javascript
// collector/processors/pdfProcessor.js

const pdf = require('pdf-parse');
const fs = require('fs');

class PDFProcessor {
  async process(filePath) {
    const dataBuffer = fs.readFileSync(filePath);
    
    try {
      const data = await pdf(dataBuffer);
      return {
        content: data.text,
        metadata: {
          pages: data.numpages,
          info: data.info,
        },
      };
    } catch (error) {
      throw new Error(`PDF 解析失败：${error.message}`);
    }
  }
}

module.exports = PDFProcessor;
```

#### 文本分块器
```javascript
// collector/chunker/TextChunker.js

class TextChunker {
  constructor(options = {}) {
    this.chunkSize = options.chunkSize || 500;
    this.chunkOverlap = options.chunkOverlap || 50;
  }
  
  chunk(text) {
    const chunks = [];
    let start = 0;
    
    while (start < text.length) {
      // 获取当前块
      let end = start + this.chunkSize;
      let chunk = text.slice(start, end);
      
      // 尝试在句子边界处切分
      if (end < text.length) {
        const lastPeriod = chunk.lastIndexOf('.');
        const lastNewline = chunk.lastIndexOf('\n');
        
        if (lastPeriod > this.chunkSize * 0.5) {
          end = start + lastPeriod + 1;
          chunk = text.slice(start, end);
        } else if (lastNewline > this.chunkSize * 0.5) {
          end = start + lastNewline + 1;
          chunk = text.slice(start, end);
        }
      }
      
      chunks.push(chunk.trim());
      start = end - this.chunkOverlap;
    }
    
    return chunks;
  }
  
  // 按段落分块（更智能）
  chunkByParagraph(text) {
    const paragraphs = text.split(/\n\s*\n/);
    const chunks = [];
    let currentChunk = '';
    
    for (const paragraph of paragraphs) {
      if (currentChunk.length + paragraph.length > this.chunkSize) {
        chunks.push(currentChunk.trim());
        currentChunk = paragraph;
      } else {
        currentChunk += '\n' + paragraph;
      }
    }
    
    if (currentChunk) {
      chunks.push(currentChunk.trim());
    }
    
    return chunks;
  }
}

module.exports = TextChunker;
```

---

### 2. 向量化模块

#### 嵌入服务
```javascript
// embed/embedders/localEmbedder.js

const { SentenceTransformer } = require('@xenova/transformers');

class LocalEmbedder {
  constructor() {
    this.model = null;
  }
  
  async load() {
    if (!this.model) {
      this.model = await SentenceTransformer.fromPretrained(
        'Xenova/all-MiniLM-L6-v2'
      );
    }
  }
  
  async embed(texts) {
    await this.load();
    
    const embeddings = [];
    for (const text of texts) {
      const embedding = await this.model.encode(text, {
        pooling: 'mean',
        normalize: true,
      });
      embeddings.push(Array.from(embedding.data));
    }
    
    return embeddings;
  }
}

module.exports = LocalEmbedder;
```

#### 向量化 API
```javascript
// embed/index.js

const LocalEmbedder = require('./embedders/localEmbedder');
const embedder = new LocalEmbedder();

async function embedText(chunks) {
  try {
    const embeddings = await embedder.embed(chunks);
    return {
      success: true,
      embeddings,
    };
  } catch (error) {
    throw new Error(`向量化失败：${error.message}`);
  }
}

module.exports = { embedText };
```

---

### 3. 向量数据库集成

#### LanceDB 存储
```javascript
// server/storage/vectorDb.js

const lancedb = require('@lancedb/lancedb');

class VectorStore {
  constructor() {
    this.db = null;
    this.collection = null;
  }
  
  async connect(dbPath) {
    this.db = await lancedb.connect(dbPath);
  }
  
  async createCollection(workspaceId) {
    const schema = {
      id: 'string',
      vector: 'float[]',
      text: 'string',
      metadata: 'json',
    };
    
    this.collection = await this.db.createTable(
      `workspace_${workspaceId}`,
      [],
      { schema }
    );
  }
  
  async addVectors(workspaceId, vectors, texts, metadatas) {
    const data = vectors.map((vector, i) => ({
      id: `chunk_${i}_${Date.now()}`,
      vector,
      text: texts[i],
      metadata: metadatas[i],
    }));
    
    await this.collection.add(data);
  }
  
  async search(workspaceId, queryVector, topK = 5) {
    const results = await this.collection
      .search(queryVector)
      .limit(topK)
      .execute();
    
    return results.map(r => ({
      text: r.text,
      metadata: r.metadata,
      distance: r.score,
    }));
  }
}

module.exports = VectorStore;
```

---

### 4. RAG 检索流程

#### 检索控制器
```javascript
// server/controllers/vectorController.js

const VectorStore = require('../storage/vectorDb');
const { embedText } = require('../embed');

const vectorStore = new VectorStore();

exports.searchWorkspace = async (req, res) => {
  const { workspaceId } = req.params;
  const { query, topK = 5 } = req.body;
  
  try {
    // 1. 向量化查询
    const queryEmbedding = await embedText([query]);
    
    // 2. 相似度搜索
    const results = await vectorStore.search(
      workspaceId,
      queryEmbedding[0],
      topK
    );
    
    // 3. 组装上下文
    const context = results
      .map(r => r.text)
      .join('\n\n---\n\n');
    
    res.json({
      success: true,
      context,
      sources: results.map(r => r.metadata),
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
};
```

---

### 5. 聊天 API（带 RAG）

```javascript
// server/controllers/chatController.js

const { searchWorkspace } = require('./vectorController');

exports.sendMessage = async (req, res) => {
  const { workspaceId } = req.params;
  const { message, history } = req.body;
  
  try {
    // 1. RAG 检索
    const ragResults = await searchWorkspace(workspaceId, message, 5);
    
    // 2. 构建提示词
    const prompt = buildPrompt(message, ragResults.context, history);
    
    // 3. 调用 LLM
    const response = await callLLM(prompt);
    
    // 4. 保存聊天记录
    await ChatHistory.create({
      workspaceId,
      role: 'user',
      content: message,
    });
    await ChatHistory.create({
      workspaceId,
      role: 'assistant',
      content: response,
    });
    
    res.json({
      success: true,
      response,
      sources: ragResults.sources,
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
};

function buildPrompt(question, context, history) {
  return `
你是一个有帮助的助手。请基于以下上下文回答问题。

上下文:
${context}

历史对话:
${history.map(h => `${h.role}: ${h.content}`).join('\n')}

问题: ${question}

回答:`;
}
```

---

### 6. 工作空间隔离

```javascript
// server/models/Workspace.js

const db = require('../db');

class Workspace {
  static async create({ name, slug }) {
    const workspace = await db.workspace.create({
      data: {
        name,
        slug,
        createdAt: new Date(),
      },
    });
    
    // 为每个工作空间创建独立的向量集合
    await vectorStore.createCollection(workspace.id);
    
    return workspace;
  }
  
  static async getAll() {
    return await db.workspace.findMany({
      include: {
        documents: true,
        chats: true,
      },
    });
  }
  
  static async delete(id) {
    // 删除向量数据
    await vectorStore.deleteCollection(id);
    
    // 删除元数据
    await db.workspace.delete({ where: { id } });
  }
}

module.exports = Workspace;
```

---

## 🎯 可借鉴的设计模式

### 1. 模块化处理器
```javascript
// 可插拔的文档处理器
const processors = {
  'pdf': PDFProcessor,
  'docx': DocxProcessor,
  'txt': TextProcessor,
  'md': MarkdownProcessor,
};

function getProcessor(fileType) {
  return new processors[fileType]();
}
```

### 2. 策略模式（向量化）
```javascript
// 支持多种嵌入模型
const embedders = {
  'local': LocalEmbedder,
  'openai': OpenAIEmbedder,
  'ollama': OllamaEmbedder,
};

function getEmbedder(strategy) {
  return new embedders[strategy]();
}
```

### 3. 工厂模式（向量数据库）
```javascript
// 支持多种向量数据库
const vectorDbs = {
  'lancedb': LanceDB,
  'chromadb': ChromaDB,
  'pinecone': Pinecone,
};

function getVectorDB(type) {
  return new vectorDbs[type]();
}
```

---

## 📋 实现检查清单

### RAG 基础功能
- [ ] 文档上传接口
- [ ] PDF/TXT/MD 解析器
- [ ] 文本分块器
- [ ] 向量化服务
- [ ] 向量数据库集成
- [ ] 相似度检索 API

### 工作空间管理
- [ ] 创建/删除工作空间
- [ ] 工作空间隔离
- [ ] 文档归属管理

### 聊天集成
- [ ] RAG 增强的聊天 API
- [ ] 上下文组装
- [ ] 引用来源显示

---

**下一步**: 根据这个分析，我们可以开始实现 RAG 功能模块！
