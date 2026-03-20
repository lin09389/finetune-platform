"""
KV Cache 优化模块

功能�?- KV Cache 量化配置
- 缓存预热功能
- 缓存分配策略
- PagedAttention 支持
"""
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
import math

logger = logging.getLogger(__name__)


class CacheQuantization(str, Enum):
    """Cache 量化类型"""
    FP16 = "fp16"
    FP8 = "fp8"
    INT8 = "int8"
    INT4 = "int4"


@dataclass
class KVCacheConfig:
    """KV Cache 配置"""
    block_size: int = 16
    max_num_blocks_per_seq: int = 256
    max_num_seqs: int = 256
    gpu_memory_utilization: float = 0.9
    cache_quantization: CacheQuantization = CacheQuantization.FP16
    swap_space: int = 4  # GB
    max_swap_blocks: int = 4096
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_size": self.block_size,
            "max_num_blocks_per_seq": self.max_num_blocks_per_seq,
            "max_num_seqs": self.max_num_seqs,
            "gpu_memory_utilization": self.gpu_memory_utilization,
            "cache_quantization": self.cache_quantization.value,
            "swap_space": self.swap_space,
            "max_swap_blocks": self.max_swap_blocks,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KVCacheConfig":
        return cls(
            block_size=data.get("block_size", 16),
            max_num_blocks_per_seq=data.get("max_num_blocks_per_seq", 256),
            max_num_seqs=data.get("max_num_seqs", 256),
            gpu_memory_utilization=data.get("gpu_memory_utilization", 0.9),
            cache_quantization=CacheQuantization(data.get("cache_quantization", "fp16")),
            swap_space=data.get("swap_space", 4),
            max_swap_blocks=data.get("max_swap_blocks", 4096),
        )


@dataclass
class CacheBlock:
    """Cache �?""
    block_id: int
    ref_count: int = 0
    token_ids: List[int] = field(default_factory=list)
    is_full: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_id": self.block_id,
            "ref_count": self.ref_count,
            "token_ids": self.token_ids,
            "is_full": self.is_full,
        }


@dataclass
class CacheStats:
    """Cache 统计"""
    total_blocks: int = 0
    used_blocks: int = 0
    free_blocks: int = 0
    hit_rate: float = 0.0
    miss_rate: float = 0.0
    evictions: int = 0
    swaps_in: int = 0
    swaps_out: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_blocks": self.total_blocks,
            "used_blocks": self.used_blocks,
            "free_blocks": self.free_blocks,
            "hit_rate": self.hit_rate,
            "miss_rate": self.miss_rate,
            "evictions": self.evictions,
            "swaps_in": self.swaps_in,
            "swaps_out": self.swaps_out,
        }


class KVCacheManager:
    """
    KV Cache 管理�?    
    功能�?    - PagedAttention 块管�?    - Cache 预热
    - 内存优化
    - 统计监控
    """
    
    def __init__(self, config: Optional[KVCacheConfig] = None):
        self.config = config or KVCacheConfig()
        
        self._blocks: Dict[int, CacheBlock] = {}
        self._free_blocks: List[int] = []
        self._seq_blocks: Dict[str, List[int]] = {}
        
        self._stats = CacheStats()
        self._total_memory_bytes = 0
        self._block_memory_bytes = 0
        
        self._prefix_cache: Dict[str, List[int]] = {}
        self._prefix_hits = 0
        self._prefix_misses = 0
    
    def initialize(self, num_blocks: int, block_memory_bytes: int):
        """初始�?Cache"""
        self._block_memory_bytes = block_memory_bytes
        self._total_memory_bytes = num_blocks * block_memory_bytes
        
        for i in range(num_blocks):
            self._blocks[i] = CacheBlock(block_id=i)
            self._free_blocks.append(i)
        
        self._stats.total_blocks = num_blocks
        self._stats.free_blocks = num_blocks
        
        logger.info(f"KV Cache 初始�? {num_blocks} �? {self._total_memory_bytes / 1024**3:.2f} GB")
    
    def allocate_block(self) -> Optional[int]:
        """分配一个块"""
        if not self._free_blocks:
            self._evict_lru_block()
        
        if not self._free_blocks:
            logger.warning("没有可用�?)
            return None
        
        block_id = self._free_blocks.pop(0)
        block = self._blocks[block_id]
        block.ref_count = 1
        block.token_ids = []
        block.is_full = False
        
        self._stats.used_blocks += 1
        self._stats.free_blocks -= 1
        
        return block_id
    
    def allocate_blocks(self, num_blocks: int) -> List[int]:
        """分配多个�?""
        allocated = []
        for _ in range(num_blocks):
            block_id = self.allocate_block()
            if block_id is None:
                break
            allocated.append(block_id)
        return allocated
    
    def free_block(self, block_id: int) -> bool:
        """释放�?""
        if block_id not in self._blocks:
            return False
        
        block = self._blocks[block_id]
        block.ref_count -= 1
        
        if block.ref_count <= 0:
            block.ref_count = 0
            block.token_ids = []
            block.is_full = False
            self._free_blocks.append(block_id)
            
            self._stats.used_blocks -= 1
            self._stats.free_blocks += 1
        
        return True
    
    def free_blocks(self, block_ids: List[int]):
        """释放多个�?""
        for block_id in block_ids:
            self.free_block(block_id)
    
    def _evict_lru_block(self) -> bool:
        """LRU 淘汰�?""
        lru_block_id = None
        lru_ref_count = float('inf')
        
        for block_id, block in self._blocks.items():
            if block.ref_count > 0 and block.ref_count < lru_ref_count:
                lru_ref_count = block.ref_count
                lru_block_id = block_id
        
        if lru_block_id is not None:
            self._blocks[lru_block_id].ref_count = 0
            self._free_blocks.append(lru_block_id)
            self._stats.evictions += 1
            logger.debug(f"LRU 淘汰�? {lru_block_id}")
            return True
        
        return False
    
    def add_prefix_cache(self, prefix_hash: str, block_ids: List[int]):
        """添加前缀缓存"""
        self._prefix_cache[prefix_hash] = block_ids.copy()
        for block_id in block_ids:
            if block_id in self._blocks:
                self._blocks[block_id].ref_count += 1
    
    def get_prefix_cache(self, prefix_hash: str) -> Optional[List[int]]:
        """获取前缀缓存"""
        if prefix_hash in self._prefix_cache:
            self._prefix_hits += 1
            self._update_hit_rate()
            return self._prefix_cache[prefix_hash].copy()
        
        self._prefix_misses += 1
        self._update_hit_rate()
        return None
    
    def _update_hit_rate(self):
        """更新命中�?""
        total = self._prefix_hits + self._prefix_misses
        if total > 0:
            self._stats.hit_rate = self._prefix_hits / total
            self._stats.miss_rate = self._prefix_misses / total
    
    def allocate_sequence(self, seq_id: str, num_blocks: int) -> List[int]:
        """为序列分配块"""
        block_ids = self.allocate_blocks(num_blocks)
        self._seq_blocks[seq_id] = block_ids
        return block_ids
    
    def free_sequence(self, seq_id: str):
        """释放序列的所有块"""
        if seq_id in self._seq_blocks:
            self.free_blocks(self._seq_blocks[seq_id])
            del self._seq_blocks[seq_id]
    
    def get_sequence_blocks(self, seq_id: str) -> List[int]:
        """获取序列的块"""
        return self._seq_blocks.get(seq_id, [])
    
    def estimate_memory_for_tokens(
        self,
        num_tokens: int,
        num_layers: int,
        num_heads: int,
        head_dim: int,
        dtype_bytes: int = 2
    ) -> int:
        """估算指定 token 数需要的内存"""
        tokens_per_block = self.config.block_size
        
        num_blocks = math.ceil(num_tokens / tokens_per_block)
        
        kv_bytes_per_token = 2 * num_layers * num_heads * head_dim * dtype_bytes
        
        total_bytes = num_blocks * tokens_per_block * kv_bytes_per_token
        
        return total_bytes
    
    def estimate_max_tokens(
        self,
        total_memory_bytes: int,
        num_layers: int,
        num_heads: int,
        head_dim: int,
        dtype_bytes: int = 2
    ) -> int:
        """估算最大可缓存 token �?""
        kv_bytes_per_token = 2 * num_layers * num_heads * head_dim * dtype_bytes
        
        tokens_per_block = self.config.block_size
        block_memory = tokens_per_block * kv_bytes_per_token
        
        num_blocks = total_memory_bytes // block_memory
        
        return num_blocks * tokens_per_block
    
    def get_stats(self) -> CacheStats:
        """获取统计信息"""
        return self._stats
    
    def get_utilization(self) -> float:
        """获取内存利用�?""
        if self._stats.total_blocks == 0:
            return 0.0
        return self._stats.used_blocks / self._stats.total_blocks
    
    def get_memory_info(self) -> Dict[str, Any]:
        """获取内存信息"""
        return {
            "total_memory_gb": self._total_memory_bytes / 1024**3,
            "used_memory_gb": (self._stats.used_blocks * self._block_memory_bytes) / 1024**3,
            "free_memory_gb": (self._stats.free_blocks * self._block_memory_bytes) / 1024**3,
            "utilization": self.get_utilization(),
            "block_size": self.config.block_size,
            "num_blocks": self._stats.total_blocks,
        }


class CacheWarmer:
    """
    Cache 预热�?    
    预加载常用前缀�?Cache
    """
    
    def __init__(self, cache_manager: KVCacheManager):
        self._cache_manager = cache_manager
        self._warmup_prompts: List[str] = []
        self._warmup_prefixes: Dict[str, List[int]] = {}
    
    def add_warmup_prompt(self, prompt: str):
        """添加预热提示"""
        self._warmup_prompts.append(prompt)
    
    def add_warmup_prefix(self, prefix: str, token_ids: List[int]):
        """添加预热前缀"""
        prefix_hash = self._hash_prefix(token_ids)
        self._warmup_prefixes[prefix_hash] = token_ids
    
    def _hash_prefix(self, token_ids: List[int]) -> str:
        """计算前缀哈希"""
        import hashlib
        return hashlib.md5(str(token_ids).encode()).hexdigest()
    
    async def warmup(self) -> int:
        """执行预热"""
        warmed = 0
        
        for prefix_hash, token_ids in self._warmup_prefixes.items():
            num_blocks = math.ceil(len(token_ids) / self._cache_manager.config.block_size)
            block_ids = self._cache_manager.allocate_blocks(num_blocks)
            
            if block_ids:
                self._cache_manager.add_prefix_cache(prefix_hash, block_ids)
                warmed += len(block_ids)
        
        logger.info(f"Cache 预热完成: {warmed} �?)
        return warmed
    
    def clear_warmup_data(self):
        """清除预热数据"""
        self._warmup_prompts.clear()
        self._warmup_prefixes.clear()


def create_cache_config(
    gpu_memory_gb: float,
    model_config: Dict[str, Any],
    quantization: CacheQuantization = CacheQuantization.FP16
) -> KVCacheConfig:
    """创建优化�?Cache 配置"""
    dtype_bytes = {
        CacheQuantization.FP16: 2,
        CacheQuantization.FP8: 1,
        CacheQuantization.INT8: 1,
        CacheQuantization.INT4: 0.5,
    }
    
    num_layers = model_config.get("num_layers", 32)
    num_heads = model_config.get("num_heads", 32)
    head_dim = model_config.get("head_dim", 128)
    
    cache_manager = KVCacheManager()
    max_tokens = cache_manager.estimate_max_tokens(
        int(gpu_memory_gb * 1024**3 * 0.9),
        num_layers,
        num_heads,
        head_dim,
        dtype_bytes[quantization]
    )
    
    block_size = 16
    max_num_blocks = max_tokens // block_size
    
    return KVCacheConfig(
        block_size=block_size,
        max_num_blocks_per_seq=max_tokens // block_size,
        max_num_seqs=min(256, max_num_blocks // 4),
        gpu_memory_utilization=0.9,
        cache_quantization=quantization,
    )


_cache_manager: Optional[KVCacheManager] = None


def get_cache_manager() -> KVCacheManager:
    """获取 Cache 管理器单�?""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = KVCacheManager()
    return _cache_manager
