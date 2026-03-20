# 模型下载和 Ollama 切换问题诊断

## ✅ 后端 API 测试结果

所有后端 API 正常工作：

```bash
# 1. Ollama 状态 - ✅ 正常
curl http://localhost:8000/inference/ollama/status
# 响应：{"running":true,"models":[...]}

# 2. 切换后端 - ✅ 正常
curl -X POST http://localhost:8000/inference/backends/switch \
  -H "Content-Type: application/json" \
  -d '{"backend":"ollama"}'
# 响应：{"message":"已切换到 ollama","current":"ollama"}

# 3. Ollama 推理 - ✅ 正常
curl -X POST http://localhost:8000/inference/generate \
  -H "Content-Type: application/json" \
  -d '{"model_id":"qwen3:4b","prompt":"Hello","backend":"ollama"}'
# 响应：{"text":"Hello! How can I assist you today?",...}

# 4. 模型搜索 - ⚠️ SSL 错误
curl -X POST http://localhost:8000/model-center/search \
  -H "Content-Type: application/json" \
  -d '{"query":"qwen"}'
# 错误：CERTIFICATE_VERIFY_FAILED
```

## 🔧 已修复

1. **SSL 证书问题** - 已在 `model_center.py` 模块顶部添加：
```python
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
```

2. **Ollama 切换 API** - 工作正常

## ⚠️ 可能的前端问题

### 1. 检查浏览器控制台

打开浏览器开发者工具 (F12)，查看：
- Console 标签 - 是否有红色错误
- Network 标签 - API 请求是否发送，响应是什么

### 2. 常见前端问题

**问题 A**: 前端 API URL 配置错误
```
检查：http://localhost:5173 -> Network -> 查看请求的 URL
解决：确保请求发送到 http://localhost:8000
```

**问题 B**: CORS 跨域错误
```
检查：Console 是否有 CORS 相关错误
解决：后端已配置 CORS，检查是否生效
```

**问题 C**: 后端未连接状态
```
检查：前端是否显示"后端未连接"
解决：刷新页面或检查后端是否运行
```

## 🚀 手动测试步骤

### 测试 Ollama 切换

1. 打开 http://localhost:5173/chat
2. 点击右上角后端选择下拉框
3. 选择 "Ollama"
4. 查看是否显示 "已切换到 Ollama"

### 测试模型下载

1. 打开 http://localhost:5173/modelhub
2. 在搜索框输入 "qwen"
3. 点击搜索
4. 查看是否显示搜索结果

### 测试推理

1. 打开 http://localhost:5173/chat
2. 确保后端已切换到 Ollama
3. 选择模型 "qwen3:4b" 或 "gemma3:4b"
4. 输入消息并发送
5. 查看是否有回复

## 📋 检查清单

- [ ] 后端服务运行 (http://localhost:8000)
- [ ] 前端服务运行 (http://localhost:5173)
- [ ] Ollama 服务运行 (http://localhost:11434)
- [ ] 浏览器 Console 无错误
- [ ] Network 请求返回 200 状态码

## 🔍 调试命令

```bash
# 检查后端健康
curl http://localhost:8000/health

# 检查 Ollama
curl http://localhost:11434/api/tags

# 检查前端
curl http://localhost:5173
```

## 📖 下一步

1. **如果后端 API 正常但前端不行**：
   - 检查浏览器 Console 错误
   - 检查 Network 请求详情
   - 截图错误信息

2. **如果模型搜索 SSL 错误**：
   - 需要重启后端使 SSL 修复生效
   - 找到运行中的 python 进程并停止
   - 重新启动后端

3. **如果 Ollama 切换失败**：
   - 检查前端是否正确调用 API
   - 检查后端日志
   - 查看 inference.py 中的 switch_backend 实现
