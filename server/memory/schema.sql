-- 记忆系统数据库 Schema
-- 支持 PostgreSQL + pgvector 扩展
-- 参考 supermemory 项目架构设计

-- 启用必要的扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================
-- 实体表 (知识图谱节点)
-- ============================================
CREATE TABLE IF NOT EXISTS entities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    attributes JSONB DEFAULT '{}',
    embedding vector(1536),
    confidence FLOAT DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    source VARCHAR(50) DEFAULT 'unknown',
    access_count INT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    user_id VARCHAR(100) DEFAULT 'default',
    
    CONSTRAINT valid_entity_type CHECK (
        entity_type IN ('person', 'project', 'skill', 'concept', 'tool', 
                        'organization', 'location', 'event', 'preference', 'habit', 'other')
    )
);

-- 实体表索引
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities USING gin(to_tsvector('simple', name));
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_user_id ON entities(user_id);
CREATE INDEX IF NOT EXISTS idx_entities_created_at ON entities(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_entities_confidence ON entities(confidence DESC);
CREATE INDEX IF NOT EXISTS idx_entities_embedding ON entities USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ============================================
-- 关系表 (知识图谱边)
-- ============================================
CREATE TABLE IF NOT EXISTS relations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    target_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relation_type VARCHAR(100) NOT NULL,
    weight FLOAT DEFAULT 1.0 CHECK (weight >= 0 AND weight <= 2),
    evidence TEXT,
    confidence FLOAT DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT unique_relation UNIQUE(source_id, target_id, relation_type),
    CONSTRAINT valid_relation_type CHECK (
        relation_type IN ('knows', 'works_on', 'uses', 'prefers', 'has_skill',
                         'related_to', 'part_of', 'located_at', 'happened_at',
                         'causes', 'mentions', 'depends_on', 'other')
    )
);

-- 关系表索引
CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_id);
CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_id);
CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relation_type);
CREATE INDEX IF NOT EXISTS idx_relations_weight ON relations(weight DESC);

-- ============================================
-- 记忆表 (长期记忆存储)
-- ============================================
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content TEXT NOT NULL,
    memory_type VARCHAR(50) NOT NULL,
    embedding vector(1536),
    importance FLOAT DEFAULT 0.5 CHECK (importance >= 0 AND importance <= 1),
    access_count INT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_accessed TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    user_id VARCHAR(100) DEFAULT 'default',
    entity_ids UUID[] DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    
    CONSTRAINT valid_memory_type CHECK (
        memory_type IN ('personal', 'preference', 'project', 'skill', 
                       'habit', 'history', 'knowledge', 'fact', 'other')
    )
);

-- 记忆表索引
CREATE INDEX IF NOT EXISTS idx_memories_content ON memories USING gin(to_tsvector('simple', content));
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type);
CREATE INDEX IF NOT EXISTS idx_memories_user_id ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);
CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_embedding ON memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ============================================
-- 短期记忆表 (会话上下文)
-- ============================================
CREATE TABLE IF NOT EXISTS short_term_memories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    importance FLOAT DEFAULT 0.5,
    entities UUID[] DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() + INTERVAL '24 hours',
    
    CONSTRAINT valid_role CHECK (role IN ('user', 'assistant', 'system'))
);

-- 短期记忆索引
CREATE INDEX IF NOT EXISTS idx_stm_session ON short_term_memories(session_id);
CREATE INDEX IF NOT EXISTS idx_stm_created_at ON short_term_memories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_stm_expires ON short_term_memories(expires_at);

-- ============================================
-- 会话表
-- ============================================
CREATE TABLE IF NOT EXISTS sessions (
    id VARCHAR(100) PRIMARY KEY,
    user_id VARCHAR(100) DEFAULT 'default',
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_activity TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    message_count INT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active',
    metadata JSONB DEFAULT '{}',
    
    CONSTRAINT valid_status CHECK (status IN ('active', 'paused', 'ended'))
);

-- 会话索引
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_last_activity ON sessions(last_activity DESC);

-- ============================================
-- 记忆更新历史表
-- ============================================
CREATE TABLE IF NOT EXISTS memory_updates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id UUID REFERENCES entities(id) ON DELETE SET NULL,
    memory_id UUID REFERENCES memories(id) ON DELETE SET NULL,
    update_type VARCHAR(50) NOT NULL,
    before_value JSONB,
    after_value JSONB,
    conflict_resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 更新历史索引
CREATE INDEX IF NOT EXISTS idx_updates_entity ON memory_updates(entity_id);
CREATE INDEX IF NOT EXISTS idx_updates_memory ON memory_updates(memory_id);
CREATE INDEX IF NOT EXISTS idx_updates_created_at ON memory_updates(created_at DESC);

-- ============================================
-- MCP 资源表 (跨平台记忆共享)
-- ============================================
CREATE TABLE IF NOT EXISTS mcp_resources (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    uri VARCHAR(500) NOT NULL UNIQUE,
    resource_type VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    mime_type VARCHAR(100) DEFAULT 'application/json',
    content JSONB NOT NULL,
    user_id VARCHAR(100) DEFAULT 'default',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT valid_resource_type CHECK (
        resource_type IN ('entity', 'memory', 'context', 'graph', 'session')
    )
);

-- MCP 资源索引
CREATE INDEX IF NOT EXISTS idx_mcp_uri ON mcp_resources(uri);
CREATE INDEX IF NOT EXISTS idx_mcp_type ON mcp_resources(resource_type);
CREATE INDEX IF NOT EXISTS idx_mcp_user ON mcp_resources(user_id);

-- ============================================
-- 视图定义
-- ============================================

-- 实体关系视图
CREATE OR REPLACE VIEW entity_relations_view AS
SELECT 
    e.id AS entity_id,
    e.name AS entity_name,
    e.entity_type,
    r.id AS relation_id,
    r.relation_type,
    r.weight,
    r.confidence AS relation_confidence,
    e2.id AS related_entity_id,
    e2.name AS related_entity_name,
    e2.entity_type AS related_entity_type
FROM entities e
LEFT JOIN relations r ON e.id = r.source_id
LEFT JOIN entities e2 ON r.target_id = e2.id;

-- 记忆摘要视图
CREATE OR REPLACE VIEW memory_summary_view AS
SELECT 
    user_id,
    memory_type,
    COUNT(*) AS count,
    AVG(importance) AS avg_importance,
    AVG(access_count) AS avg_access_count,
    MAX(created_at) AS last_created,
    MAX(last_accessed) AS last_accessed
FROM memories
GROUP BY user_id, memory_type;

-- 活跃实体视图
CREATE OR REPLACE VIEW active_entities_view AS
SELECT 
    id,
    name,
    entity_type,
    confidence,
    access_count,
    updated_at,
    (access_count * confidence) AS activity_score
FROM entities
WHERE updated_at > NOW() - INTERVAL '7 days'
ORDER BY activity_score DESC;

-- ============================================
-- 函数定义
-- ============================================

-- 向量相似度搜索函数
CREATE OR REPLACE FUNCTION search_similar_entities(
    query_embedding vector(1536),
    query_user_id VARCHAR(100) DEFAULT 'default',
    match_limit INT DEFAULT 10,
    similarity_threshold FLOAT DEFAULT 0.7
)
RETURNS TABLE (
    id UUID,
    name VARCHAR(255),
    entity_type VARCHAR(50),
    similarity FLOAT
)
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        e.id,
        e.name,
        e.entity_type,
        1 - (e.embedding <=> query_embedding) AS similarity
    FROM entities e
    WHERE e.user_id = query_user_id
      AND e.embedding IS NOT NULL
      AND 1 - (e.embedding <=> query_embedding) > similarity_threshold
    ORDER BY e.embedding <=> query_embedding
    LIMIT match_limit;
END;
$$ LANGUAGE plpgsql;

-- 向量相似度搜索记忆函数
CREATE OR REPLACE FUNCTION search_similar_memories(
    query_embedding vector(1536),
    query_user_id VARCHAR(100) DEFAULT 'default',
    match_limit INT DEFAULT 10,
    similarity_threshold FLOAT DEFAULT 0.7
)
RETURNS TABLE (
    id UUID,
    content TEXT,
    memory_type VARCHAR(50),
    similarity FLOAT
)
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        m.id,
        m.content,
        m.memory_type,
        1 - (m.embedding <=> query_embedding) AS similarity
    FROM memories m
    WHERE m.user_id = query_user_id
      AND m.embedding IS NOT NULL
      AND 1 - (m.embedding <=> query_embedding) > similarity_threshold
    ORDER BY m.embedding <=> query_embedding
    LIMIT match_limit;
END;
$$ LANGUAGE plpgsql;

-- 获取实体上下文（多跳关系）
CREATE OR REPLACE FUNCTION get_entity_context(
    entity_uuid UUID,
    max_depth INT DEFAULT 2
)
RETURNS TABLE (
    entity_id UUID,
    entity_name VARCHAR(255),
    relation_type VARCHAR(100),
    related_id UUID,
    related_name VARCHAR(255),
    depth INT
)
AS $$
WITH RECURSIVE entity_graph AS (
    -- 基础情况：起始实体
    SELECT 
        e.id AS entity_id,
        e.name AS entity_name,
        NULL::VARCHAR(100) AS relation_type,
        e.id AS related_id,
        e.name AS related_name,
        0 AS depth
    FROM entities e
    WHERE e.id = entity_uuid
    
    UNION ALL
    
    -- 递归：通过关系连接的实体
    SELECT 
        eg.entity_id,
        eg.entity_name,
        r.relation_type,
        e2.id,
        e2.name,
        eg.depth + 1
    FROM entity_graph eg
    JOIN relations r ON eg.related_id = r.source_id
    JOIN entities e2 ON r.target_id = e2.id
    WHERE eg.depth < max_depth
)
SELECT * FROM entity_graph WHERE depth > 0
ORDER BY depth, relation_type;
$$ LANGUAGE sql;

-- 清理过期短期记忆
CREATE OR REPLACE FUNCTION cleanup_expired_memories()
RETURNS INT
AS $$
DECLARE
    deleted_count INT;
BEGIN
    DELETE FROM short_term_memories 
    WHERE expires_at < NOW();
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- 更新实体访问计数
CREATE OR REPLACE FUNCTION touch_entity(entity_uuid UUID)
RETURNS VOID
AS $$
BEGIN
    UPDATE entities
    SET 
        access_count = access_count + 1,
        updated_at = NOW()
    WHERE id = entity_uuid;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- 触发器定义
-- ============================================

-- 自动更新 updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_entities_updated_at
    BEFORE UPDATE ON entities
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_memories_last_accessed
    BEFORE UPDATE ON memories
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_mcp_resources_updated_at
    BEFORE UPDATE ON mcp_resources
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- 初始数据
-- ============================================

-- 插入默认会话
INSERT INTO sessions (id, user_id, status)
VALUES ('default', 'default', 'active')
ON CONFLICT (id) DO NOTHING;

-- ============================================
-- 权限设置 (根据实际需求调整)
-- ============================================

-- 创建只读用户示例
-- CREATE USER memory_readonly WITH PASSWORD 'your_password';
-- GRANT CONNECT ON DATABASE your_database TO memory_readonly;
-- GRANT USAGE ON SCHEMA public TO memory_readonly;
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO memory_readonly;

-- 创建读写用户示例
-- CREATE USER memory_readwrite WITH PASSWORD 'your_password';
-- GRANT CONNECT ON DATABASE your_database TO memory_readwrite;
-- GRANT USAGE ON SCHEMA public TO memory_readwrite;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO memory_readwrite;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO memory_readwrite;
