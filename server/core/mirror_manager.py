"""
镜像管理器 - 国内环境适配
支持 HuggingFace、ModelScope、阿里云镜像源
"""
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class MirrorSource(str, Enum):
    OFFICIAL = "official"
    HF_MIRROR = "hf-mirror"
    ALIYUN = "aliyun"
    MODELSCOPE = "modelscope"
    AUTO = "auto"


@dataclass
class MirrorConfig:
    hf_endpoint: str
    modelscope_endpoint: str | None = None
    pip_index: str | None = None
    pip_trusted_host: str | None = None
    description: str = ""
    priority: int = 0


MIRROR_CONFIGS: dict[MirrorSource, MirrorConfig] = {
    MirrorSource.OFFICIAL: MirrorConfig(
        hf_endpoint="https://huggingface.co",
        description="HuggingFace 官方源",
        priority=0,
    ),
    MirrorSource.HF_MIRROR: MirrorConfig(
        hf_endpoint="https://hf-mirror.com",
        description="HF-Mirror 镜像（推荐）",
        priority=1,
    ),
    MirrorSource.ALIYUN: MirrorConfig(
        hf_endpoint="https://mirrors.aliyun.com/huggingface",
        pip_index="https://mirrors.aliyun.com/pypi/simple",
        pip_trusted_host="mirrors.aliyun.com",
        description="阿里云镜像",
        priority=2,
    ),
    MirrorSource.MODELSCOPE: MirrorConfig(
        hf_endpoint="https://modelscope.cn/models",
        modelscope_endpoint="https://modelscope.cn",
        description="ModelScope 魔搭社区",
        priority=3,
    ),
}


@dataclass
class DownloadProgress:
    total_bytes: int = 0
    downloaded_bytes: int = 0
    current_file: str = ""
    speed_bps: float = 0.0
    eta_seconds: float = 0.0
    start_time: float = 0.0


class MirrorManager:
    """
    镜像管理器
    
    特性:
    - 支持多种镜像源
    - 自动检测国内环境
    - 下载失败自动回退
    - 进度回调支持
    """

    def __init__(
        self,
        source: MirrorSource = MirrorSource.HF_MIRROR,
        cache_dir: str | None = None,
    ):
        self.source = source
        self.cache_dir = cache_dir or os.path.expanduser("~/.cache/huggingface")
        self.config = MIRROR_CONFIGS.get(source, MIRROR_CONFIGS[MirrorSource.HF_MIRROR])
        self._fallback_order = self._get_fallback_order()
        self._current_source = source
        self._progress_callbacks: list[Callable[[DownloadProgress], None]] = []

    def _get_fallback_order(self) -> list[MirrorSource]:
        """获取回退顺序"""
        order = [MirrorSource.HF_MIRROR, MirrorSource.ALIYUN, MirrorSource.MODELSCOPE]
        if self.source in order:
            order.remove(self.source)
            order.insert(0, self.source)
        return order

    def setup(self) -> None:
        """配置镜像环境变量"""
        os.environ["HF_ENDPOINT"] = self.config.hf_endpoint

        if self.cache_dir:
            os.environ["TRANSFORMERS_CACHE"] = self.cache_dir
            os.environ["HF_HOME"] = self.cache_dir
            os.environ["HF_HUB_CACHE"] = self.cache_dir

        if self.config.pip_index:
            pip_config = f"[global]\nindex-url = {self.config.pip_index}\n"
            if self.config.pip_trusted_host:
                pip_config += f"trusted-host = {self.config.pip_trusted_host}\n"

            pip_conf_path = os.path.expanduser("~/.pip/pip.conf")
            os.makedirs(os.path.dirname(pip_conf_path), exist_ok=True)
            with open(pip_conf_path, "w") as f:
                f.write(pip_config)
            logger.info(f"已配置 pip 镜像: {self.config.pip_index}")

        if self.source == MirrorSource.MODELSCOPE:
            self._setup_modelscope()

        logger.info(f"镜像环境已配置: {self.source.value} ({self.config.hf_endpoint})")

    def _setup_modelscope(self) -> None:
        """配置 ModelScope SDK"""
        try:
            import modelscope
            if self.config.modelscope_endpoint:
                os.environ["MODELSCOPE_CACHE"] = self.cache_dir
            logger.info("ModelScope SDK 已配置")
        except ImportError:
            logger.warning("ModelScope SDK 未安装，请运行: pip install modelscope")

    def add_progress_callback(self, callback: Callable[[DownloadProgress], None]) -> None:
        """添加进度回调"""
        self._progress_callbacks.append(callback)

    def _notify_progress(self, progress: DownloadProgress) -> None:
        """通知进度更新"""
        for callback in self._progress_callbacks:
            try:
                callback(progress)
            except Exception as e:
                logger.warning(f"进度回调错误: {e}")

    def download_model(
        self,
        model_id: str,
        local_dir: str | None = None,
        revision: str = "main",
        max_retries: int = 3,
    ) -> str:
        """
        下载模型（支持自动回退）
        
        Args:
            model_id: 模型 ID
            local_dir: 本地目录
            revision: 模型版本
            max_retries: 最大重试次数
            
        Returns:
            模型本地路径
        """
        local_dir = local_dir or os.path.join(self.cache_dir, "models", model_id.replace("/", "--"))

        for attempt, source in enumerate(self._fallback_order):
            if attempt >= max_retries:
                break

            try:
                self._current_source = source
                config = MIRROR_CONFIGS[source]
                os.environ["HF_ENDPOINT"] = config.hf_endpoint

                logger.info(f"尝试从 {source.value} 下载模型: {model_id}")

                if source == MirrorSource.MODELSCOPE:
                    return self._download_from_modelscope(model_id, local_dir)
                else:
                    return self._download_from_hf(model_id, local_dir, revision)

            except Exception as e:
                logger.warning(f"从 {source.value} 下载失败: {e}")
                if attempt < len(self._fallback_order) - 1:
                    logger.info("尝试下一个镜像源...")
                continue

        raise RuntimeError(f"所有镜像源下载失败: {model_id}")

    def _download_from_hf(
        self,
        model_id: str,
        local_dir: str,
        revision: str = "main",
    ) -> str:
        """从 HuggingFace 下载"""
        from huggingface_hub import snapshot_download

        progress = DownloadProgress(start_time=time.time())

        def progress_callback(repo_id, repo_type, revision_info, downloaded, total):
            progress.downloaded_bytes = downloaded
            progress.total_bytes = total
            progress.speed_bps = downloaded / (time.time() - progress.start_time) if time.time() > progress.start_time else 0
            self._notify_progress(progress)

        path = snapshot_download(
            repo_id=model_id,
            local_dir=local_dir,
            revision=revision,
            local_dir_use_symlinks=False,
        )

        logger.info(f"模型下载完成: {model_id} -> {path}")
        return path

    def _download_from_modelscope(
        self,
        model_id: str,
        local_dir: str,
    ) -> str:
        """从 ModelScope 下载"""
        try:
            from modelscope import snapshot_download

            ms_model_id = model_id.replace("/", "/")

            path = snapshot_download(
                model_id=ms_model_id,
                cache_dir=self.cache_dir,
            )

            logger.info(f"ModelScope 下载完成: {model_id} -> {path}")
            return path

        except ImportError:
            raise RuntimeError("ModelScope SDK 未安装，请运行: pip install modelscope")

    def download_dataset(
        self,
        dataset_id: str,
        local_dir: str | None = None,
    ) -> str:
        """下载数据集"""
        local_dir = local_dir or os.path.join(self.cache_dir, "datasets", dataset_id.replace("/", "--"))

        for source in self._fallback_order:
            try:
                config = MIRROR_CONFIGS[source]
                os.environ["HF_ENDPOINT"] = config.hf_endpoint

                if source == MirrorSource.MODELSCOPE:
                    return self._download_dataset_from_modelscope(dataset_id, local_dir)
                else:
                    return self._download_dataset_from_hf(dataset_id, local_dir)

            except Exception as e:
                logger.warning(f"从 {source.value} 下载数据集失败: {e}")
                continue

        raise RuntimeError(f"所有镜像源下载数据集失败: {dataset_id}")

    def _download_dataset_from_hf(self, dataset_id: str, local_dir: str) -> str:
        """从 HuggingFace 下载数据集"""
        from huggingface_hub import snapshot_download

        return snapshot_download(
            repo_id=dataset_id,
            repo_type="dataset",
            local_dir=local_dir,
        )

    def _download_dataset_from_modelscope(self, dataset_id: str, local_dir: str) -> str:
        """从 ModelScope 下载数据集"""
        try:
            from modelscope.msdatasets import MsDataset

            ds = MsDataset.load(dataset_id, subset_name="default")
            return local_dir
        except ImportError:
            raise RuntimeError("ModelScope SDK 未安装")

    def get_current_source(self) -> MirrorSource:
        """获取当前使用的镜像源"""
        return self._current_source

    def test_connection(self, source: MirrorSource | None = None) -> dict[str, bool]:
        """测试镜像源连接"""
        import requests

        results = {}
        sources_to_test = [source] if source else list(MIRROR_CONFIGS.keys())

        for src in sources_to_test:
            config = MIRROR_CONFIGS.get(src)
            if not config:
                continue

            try:
                response = requests.get(config.hf_endpoint, timeout=10)
                results[src.value] = response.status_code == 200
            except Exception:
                results[src.value] = False

        return results

    @staticmethod
    def detect_china_environment() -> bool:
        """检测是否在中国大陆环境"""
        try:
            import requests
            response = requests.get("https://huggingface.co", timeout=5)
            return False
        except Exception:
            return True

    @staticmethod
    def get_recommended_source() -> MirrorSource:
        """获取推荐的镜像源"""
        if MirrorManager.detect_china_environment():
            return MirrorSource.HF_MIRROR
        return MirrorSource.OFFICIAL


_mirror_manager: MirrorManager | None = None


def get_mirror_manager(
    source: MirrorSource | None = None,
    cache_dir: str | None = None,
) -> MirrorManager:
    """获取镜像管理器单例"""
    global _mirror_manager

    if _mirror_manager is None:
        if source is None:
            source = MirrorManager.get_recommended_source()
        _mirror_manager = MirrorManager(source=source, cache_dir=cache_dir)
        _mirror_manager.setup()

    return _mirror_manager


def reset_mirror_manager() -> MirrorManager:
    """重置镜像管理器"""
    global _mirror_manager
    _mirror_manager = None
    return get_mirror_manager()
