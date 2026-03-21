"""
阿里 SWIFT 框架训练后端 - CLI 调用模式（重构版）
修复：
- P1-4: SWIFT 进程管理增强，防止僵尸进程
参考：https://github.com/modelscope/swift
"""
import subprocess
import json
import os
import signal
import atexit
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import threading
import logging
import time
import weakref

from core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SwiftTrainConfig:
    """SWIFT 训练配置 - 支持高精度微调"""
    model_id: str
    dataset_id: str
    method: str = "lora"
    learning_rate: float = 5e-5
    epochs: int = 3
    batch_size: int = 1
    gradient_accumulation: int = 16
    max_seq_length: int = 512
    lora_rank: int = 8
    lora_alpha: int = 16
    lora_dropout: float = 0.05
    warmup_steps: int = 100
    save_steps: int = 500
    logging_steps: int = 10
    output_dir: str = "./output"
    quantization_bit: int = 4
    val_size: float = 0.0
    warmup_ratio: float = 0.1
    weight_decay: float = 0.01
    max_grad_norm: float = 1.0
    
    use_dora: bool = False
    lr_scheduler: str = "cosine"
    label_smoothing: float = 0.0
    gradient_checkpointing: bool = True
    bf16: bool = True
    eval_steps: int = 100
    load_best_model: bool = True
    target_modules: str = "all"
    
    use_flash_attn: bool = False
    deepspeed_stage: int = 0
    offload_optimizer: bool = False
    fp16: bool = False


class SwiftBackend:
    """
    SWIFT 框架后端 - CLI 调用模式（重构版）
    
    修复：
    - P1-4: 进程组管理，防止僵尸进程
    - 添加进程监控和自动清理
    """
    
    GRACEFUL_TIMEOUT = 10
    FORCE_KILL_TIMEOUT = 5
    PROCESS_CHECK_INTERVAL = 5
    
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.log_file: Optional[Path] = None
        self._stop_event = threading.Event()
        self._current_task_id: Optional[str] = None
        self._process_lock = threading.Lock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_running = False
        
        self._instances = weakref.WeakSet()
        
        atexit.register(self._cleanup_on_exit)
    
    def _cleanup_on_exit(self):
        """程序退出时清理所有进程"""
        self._monitor_running = False
        
        with self._process_lock:
            if self.process and self.process.poll() is None:
                try:
                    self._terminate_process_tree(self.process.pid)
                except Exception:
                    pass
    
    def _terminate_process_tree(self, pid: int):
        """终止进程树（包括所有子进程）"""
        try:
            import psutil
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            
            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            
            gone, alive = psutil.wait_procs(children, timeout=self.GRACEFUL_TIMEOUT)
            
            for p in alive:
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass
            
            parent.terminate()
            parent.wait(timeout=self.GRACEFUL_TIMEOUT)
            
        except psutil.NoSuchProcess:
            pass
        except ImportError:
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
                time.sleep(self.GRACEFUL_TIMEOUT)
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    
    def _start_monitor(self):
        """启动进程监控线程"""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        
        self._monitor_running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
    
    def _monitor_loop(self):
        """监控进程状态"""
        while self._monitor_running:
            try:
                with self._process_lock:
                    if self.process and self.process.poll() is not None:
                        logger.info(f"SWIFT 进程已结束，PID: {self.process.pid}, 返回码: {self.process.returncode}")
                        self._handle_process_exit()
                
                time.sleep(self.PROCESS_CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"进程监控错误：{e}")
    
    def _handle_process_exit(self):
        """处理进程退出"""
        if self._current_task_id:
            logger.info(f"任务 {self._current_task_id} 已结束")
    
    def is_available(self) -> bool:
        """检查 SWIFT 是否可用"""
        try:
            import importlib.util
            spec = importlib.util.find_spec("swift")
            if spec is None:
                return False
            
            from swift.cli import main
            return True
        except Exception:
            return False
    
    def get_version(self) -> str:
        """获取 SWIFT 版本"""
        try:
            import swift
            return getattr(swift, "__version__", "latest")
        except Exception as e:
            return f"unknown ({e})"
    
    def build_command(self, config: SwiftTrainConfig) -> List[str]:
        """构建 SWIFT CLI 命令"""
        cmd = [
            "swift", "sft",
            "--model_id_or_path", config.model_id,
            "--dataset", config.dataset_id,
        ]

        if config.method == "full":
            cmd.extend(["--stage", "sft"])
        elif config.method == "dora":
            cmd.extend([
                "--stage", "sft-lora",
                "--use_dora", "true",
                "--lora_rank", str(config.lora_rank),
                "--lora_alpha", str(config.lora_alpha),
                "--lora_dropout_p", str(config.lora_dropout),
                "--lora_target_modules", config.target_modules,
            ])
        else:
            cmd.extend([
                "--stage", "sft-lora",
                "--lora_rank", str(config.lora_rank),
                "--lora_alpha", str(config.lora_alpha),
                "--lora_dropout_p", str(config.lora_dropout),
                "--lora_target_modules", config.target_modules,
            ])

        cmd.extend([
            "--learning_rate", str(config.learning_rate),
            "--num_train_epochs", str(config.epochs),
            "--per_device_train_batch_size", str(config.batch_size),
            "--gradient_accumulation_steps", str(config.gradient_accumulation),
            "--max_length", str(config.max_seq_length),
            "--warmup_ratio", str(config.warmup_ratio),
            "--save_steps", str(config.save_steps),
            "--logging_steps", str(config.logging_steps),
            "--output_dir", config.output_dir,
            "--weight_decay", str(config.weight_decay),
            "--max_grad_norm", str(config.max_grad_norm),
            "--lr_scheduler_type", config.lr_scheduler,
        ])

        if config.gradient_checkpointing:
            cmd.append("--gradient_checkpointing")

        if config.bf16:
            cmd.extend(["--bf16", "true"])
        elif config.fp16:
            cmd.extend(["--fp16", "true"])

        if config.label_smoothing > 0:
            cmd.extend(["--label_smoothing", str(config.label_smoothing)])

        if config.use_flash_attn:
            cmd.extend(["--use_flash_attn", "true"])
        
        if config.deepspeed_stage > 0:
            cmd.extend([
                "--deepspeed",
                "--deepspeed_zero_stage", str(config.deepspeed_stage),
            ])
            if config.offload_optimizer:
                cmd.extend(["--deepspeed_offload_optimizer", "true"])

        if config.method == "qlora" or config.quantization_bit > 0:
            cmd.extend([
                "--quantization_bit", str(config.quantization_bit),
                "--bnb_4bit_compute_dtype", "float16",
                "--bnb_4bit_use_double_quant", "true",
                "--bnb_4bit_quant_type", "nf4",
            ])

        if config.eval_steps > 0 and config.load_best_model:
            cmd.extend([
                "--evaluation_strategy", "steps",
                "--eval_steps", str(config.eval_steps),
                "--load_best_model_at_end", "true",
                "--metric_for_best_model", "eval_loss",
                "--save_total_limit", "3",
            ])

        cmd.extend([
            "--use_tensorboard", "true",
            "--tensorboard_dir", str(Path(config.output_dir) / "runs"),
        ])

        cmd.extend(["--log_level", "info"])

        return cmd
    
    def start_training(
        self, 
        config: SwiftTrainConfig, 
        log_dir: Path,
        task_id: str
    ) -> bool:
        """
        启动训练
        
        P1-4: 使用进程组管理，防止僵尸进程
        """
        with self._process_lock:
            if self.process and self.process.poll() is None:
                logger.error("已有训练任务在运行")
                return False
            
            cmd = self.build_command(config)
            logger.info(f"SWIFT 命令：{' '.join(cmd)}")
            
            log_dir.mkdir(parents=True, exist_ok=True)
            self.log_file = log_dir / "swift_training.log"
            self._current_task_id = task_id
            self._stop_event.clear()
            
            try:
                with open(self.log_file, 'w', encoding='utf-8') as f:
                    f.write(f"# SWIFT Command: {' '.join(cmd)}\n")
                    f.write(f"# Task ID: {task_id}\n")
                    f.write(f"# Start Time: {__import__('datetime').datetime.now().isoformat()}\n\n")
                    f.flush()
                    
                    self.process = subprocess.Popen(
                        cmd,
                        stdout=f,
                        stderr=subprocess.STDOUT,
                        cwd=os.getcwd(),
                        env=os.environ.copy(),
                        encoding='utf-8',
                        start_new_session=True
                    )
                
                self._start_monitor()
                
                logger.info(f"SWIFT 训练已启动，PID: {self.process.pid}, Task: {task_id}")
                return True
                
            except FileNotFoundError as e:
                logger.error(f"SWIFT 未安装：{e}")
                return False
            except Exception as e:
                logger.error(f"启动 SWIFT 训练失败：{e}")
                return False
    
    def stop_training(self) -> bool:
        """停止训练 - P1-4: 增强版进程终止"""
        with self._process_lock:
            if not self.process:
                return False
            
            if self.process.poll() is None:
                try:
                    logger.info(f"正在停止 SWIFT 训练 (PID: {self.process.pid})...")
                    
                    self._terminate_process_tree(self.process.pid)
                    
                    try:
                        self.process.wait(timeout=self.FORCE_KILL_TIMEOUT)
                    except subprocess.TimeoutExpired:
                        pass
                    
                    logger.info("SWIFT 训练已停止")
                    return True
                    
                except Exception as e:
                    logger.error(f"停止训练失败：{e}")
                    return False
            else:
                logger.info("训练进程已结束")
                return True
    
    def get_training_status(self) -> Dict[str, Any]:
        """获取训练状态"""
        with self._process_lock:
            if not self.process:
                return {"status": "idle", "task_id": None}
            
            return_code = self.process.poll()
            
            if return_code is None:
                return {
                    "status": "running",
                    "pid": self.process.pid,
                    "task_id": self._current_task_id
                }
            elif return_code == 0:
                return {
                    "status": "completed",
                    "task_id": self._current_task_id,
                    "return_code": return_code
                }
            else:
                return {
                    "status": "failed",
                    "task_id": self._current_task_id,
                    "return_code": return_code
                }
    
    def parse_training_progress(self) -> Dict[str, Any]:
        """解析训练进度（从日志文件）"""
        if not self.log_file or not self.log_file.exists():
            return {
                "epoch": 0,
                "step": 0,
                "total_steps": 0,
                "loss": 0.0,
                "lr": 0.0,
                "elapsed_time": 0.0
            }
        
        progress = {
            "epoch": 0,
            "step": 0,
            "total_steps": 0,
            "loss": 0.0,
            "lr": 0.0,
            "elapsed_time": 0.0,
            "message": ""
        }
        
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            total_steps_found = False
            
            for line in reversed(lines):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                try:
                    start = line.find('{')
                    end = line.rfind('}') + 1
                    
                    if start >= 0 and end > start:
                        log_data = json.loads(line[start:end])
                        
                        if "loss" in log_data:
                            progress["loss"] = float(log_data.get("loss", 0.0))
                        if "learning_rate" in log_data:
                            progress["lr"] = float(log_data.get("learning_rate", 0.0))
                        if "epoch" in log_data:
                            progress["epoch"] = int(float(log_data.get("epoch", 0)))
                        if "step" in log_data:
                            progress["step"] = int(log_data.get("step", 0))
                        if "total_steps" in log_data:
                            progress["total_steps"] = int(log_data.get("total_steps", 0))
                            total_steps_found = True
                        
                        if progress["step"] > 0:
                            progress["message"] = f"Training epoch {progress['epoch']}"
                            break
                            
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue
            
            if not total_steps_found and progress["step"] > 0:
                progress["total_steps"] = progress["step"] * 3
            
            try:
                mtime = self.log_file.stat().st_mtime
                start_time = self.log_file.stat().st_ctime
                progress["elapsed_time"] = mtime - start_time
            except Exception:
                pass
                
        except Exception as e:
            logger.error(f"解析日志失败：{e}")
        
        return progress
    
    def get_log_tail(self, lines: int = 50) -> List[str]:
        """获取日志末尾 N 行"""
        if not self.log_file or not self.log_file.exists():
            return []
        
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
                return [line.strip() for line in all_lines[-lines:]]
        except Exception:
            return []
    
    def cleanup(self):
        """清理资源"""
        self._monitor_running = False
        
        with self._process_lock:
            if self.process and self.process.poll() is None:
                try:
                    self._terminate_process_tree(self.process.pid)
                except Exception:
                    pass
            
            self.process = None
            self._current_task_id = None
            self._stop_event.clear()
        
        logger.debug("SWIFT Backend 已清理")


_swift_backend: Optional[SwiftBackend] = None
_swift_backend_lock = threading.Lock()


def get_swift_backend() -> SwiftBackend:
    """获取 SWIFT 后端实例（单例）"""
    global _swift_backend
    if _swift_backend is None:
        with _swift_backend_lock:
            if _swift_backend is None:
                _swift_backend = SwiftBackend()
    return _swift_backend


def reset_swift_backend():
    """重置 SWIFT 后端（用于测试）"""
    global _swift_backend
    with _swift_backend_lock:
        if _swift_backend:
            _swift_backend.cleanup()
            _swift_backend = None
