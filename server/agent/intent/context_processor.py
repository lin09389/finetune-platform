"""
多轮对话上下文理解模块
支持对话状态追踪、意图链预测、实体记忆、槽位填充
"""
import re
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime
from enum import Enum
import threading

logger = logging.getLogger(__name__)


class DialogueState(str, Enum):
    """对话状态"""
    IDLE = "idle"
    COLLECTING_PARAMS = "collecting_params"
    CONFIRMING = "confirming"
    EXECUTING = "executing"
    FOLLOW_UP = "follow_up"
    ERROR = "error"


class EntityType(str, Enum):
    """实体类型"""
    FILE_PATH = "file_path"
    DIRECTORY = "directory"
    APP_NAME = "app_name"
    URL = "url"
    TEXT = "text"
    NUMBER = "number"
    COORDINATE = "coordinate"


@dataclass
class Entity:
    """实体"""
    type: EntityType
    value: Any
    confidence: float = 1.0
    source: str = "extracted"
    turn_index: int = 0


@dataclass
class Slot:
    """槽位"""
    name: str
    value: Any = None
    required: bool = True
    filled: bool = False
    prompt: str = ""
    validation_regex: Optional[str] = None
    
    def is_valid(self) -> bool:
        """验证槽位值"""
        if not self.filled or self.value is None:
            return False
        if self.validation_regex:
            return bool(re.match(self.validation_regex, str(self.value)))
        return True


@dataclass
class DialogueTurn:
    """对话轮次"""
    turn_index: int
    user_message: str
    detected_intent: Optional[str] = None
    detected_params: Dict[str, Any] = field(default_factory=dict)
    system_response: str = ""
    entities: List[Entity] = field(default_factory=list)
    state: DialogueState = DialogueState.IDLE
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class IntentChain:
    """意图链"""
    intents: List[str]
    probability: float
    context_requirements: List[str] = field(default_factory=list)
    description: str = ""


class DialogueMemory:
    """对话记忆"""
    
    def __init__(self, session_id: str, max_turns: int = 20):
        self.session_id = session_id
        self.max_turns = max_turns
        self.turns: List[DialogueTurn] = []
        self.entities: Dict[str, List[Entity]] = defaultdict(list)
        self.slots: Dict[str, Slot] = {}
        self.current_intent: Optional[str] = None
        self.state: DialogueState = DialogueState.IDLE
        self.pending_actions: List[Dict[str, Any]] = []
        self.user_preferences: Dict[str, Any] = {}
        self.created_at = datetime.now()
        self.last_updated = datetime.now()
        self._lock = threading.Lock()
    
    def add_turn(
        self,
        user_message: str,
        intent: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        system_response: str = "",
        entities: Optional[List[Entity]] = None
    ) -> DialogueTurn:
        """添加对话轮次"""
        with self._lock:
            turn_index = len(self.turns)
            turn = DialogueTurn(
                turn_index=turn_index,
                user_message=user_message,
                detected_intent=intent,
                detected_params=params or {},
                system_response=system_response,
                entities=entities or [],
                state=self.state
            )
            
            self.turns.append(turn)
            
            if len(self.turns) > self.max_turns:
                self.turns = self.turns[-self.max_turns:]
            
            if entities:
                turn.entities = entities
                for entity in entities:
                    entity.turn_index = turn_index
                    self.entities[entity.type.value].append(entity)
            
            self.last_updated = datetime.now()
            return turn
    
    def _cleanup_entities(self, turn: DialogueTurn):
        """清理过期实体"""
        for entity in turn.entities:
            if entity.type.value in self.entities:
                self.entities[entity.type.value] = [
                    e for e in self.entities[entity.type.value]
                    if e.turn_index != turn.turn_index
                ]
    
    def get_recent_intents(self, n: int = 5) -> List[str]:
        """获取最近的意图"""
        intents = []
        for turn in reversed(self.turns[-n:]):
            if turn.detected_intent:
                intents.append(turn.detected_intent)
        return intents
    
    def get_recent_entities(self, entity_type: Optional[str] = None, n: int = 5) -> List[Entity]:
        """获取最近的实体"""
        if entity_type:
            return self.entities.get(entity_type, [])[-n:]
        
        all_entities = []
        for entities in self.entities.values():
            all_entities.extend(entities)
        return sorted(all_entities, key=lambda e: e.turn_index, reverse=True)[:n]
    
    def get_last_entity(self, entity_type: str) -> Optional[Entity]:
        """获取最后一个特定类型的实体"""
        entities = self.entities.get(entity_type, [])
        return entities[-1] if entities else None
    
    def resolve_reference(self, reference: str) -> Optional[Any]:
        """解析引用"""
        reference_map = {
            "它": EntityType.FILE_PATH,
            "这个": EntityType.FILE_PATH,
            "那个": EntityType.FILE_PATH,
            "这个文件": EntityType.FILE_PATH,
            "那个文件": EntityType.FILE_PATH,
            "这个目录": EntityType.DIRECTORY,
            "那个目录": EntityType.DIRECTORY,
            "这个应用": EntityType.APP_NAME,
            "那个应用": EntityType.APP_NAME,
            "这个网址": EntityType.URL,
            "那个网址": EntityType.URL,
        }
        
        entity_type = reference_map.get(reference)
        if entity_type:
            entity = self.get_last_entity(entity_type.value)
            if entity:
                return entity.value
        
        ordinal_map = {
            "第一个": 0,
            "第二个": 1,
            "第三个": 2,
            "最后一个": -1,
        }
        
        if reference in ordinal_map:
            index = ordinal_map[reference]
            entities = self.get_recent_entities(EntityType.FILE_PATH.value, 10)
            if entities:
                try:
                    return entities[index].value
                except IndexError:
                    return None
        
        return None
    
    def set_slot(self, name: str, value: Any, required: bool = True, prompt: str = "", validation_regex: Optional[str] = None):
        """设置槽位"""
        self.slots[name] = Slot(
            name=name,
            value=value,
            required=required,
            filled=value is not None,
            prompt=prompt,
            validation_regex=validation_regex
        )
    
    def fill_slot(self, name: str, value: Any) -> bool:
        """填充槽位"""
        if name in self.slots:
            self.slots[name].value = value
            self.slots[name].filled = True
            return True
        return False
    
    def get_missing_slots(self) -> List[Slot]:
        """获取缺失的槽位"""
        return [s for s in self.slots.values() if s.required and not s.is_valid()]
    
    def clear_slots(self):
        """清除槽位"""
        self.slots.clear()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "turn_count": len(self.turns),
            "current_intent": self.current_intent,
            "state": self.state.value,
            "recent_intents": self.get_recent_intents(5),
            "entities_count": {k: len(v) for k, v in self.entities.items()},
            "slots": {k: {"value": v.value, "filled": v.filled} for k, v in self.slots.items()},
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat()
        }


class IntentChainPredictor:
    """意图链预测器"""
    
    INTENT_CHAINS = [
        IntentChain(
            intents=["file_create", "file_write"],
            probability=0.85,
            context_requirements=[],
            description="创建文件后写入内容"
        ),
        IntentChain(
            intents=["file_read", "file_write"],
            probability=0.75,
            context_requirements=["file_path"],
            description="读取文件后修改"
        ),
        IntentChain(
            intents=["file_list", "file_read"],
            probability=0.70,
            context_requirements=[],
            description="列出文件后打开"
        ),
        IntentChain(
            intents=["screenshot", "file_write"],
            probability=0.65,
            context_requirements=[],
            description="截图后保存"
        ),
        IntentChain(
            intents=["app_open", "url_open"],
            probability=0.60,
            context_requirements=[],
            description="打开应用后访问网址"
        ),
        IntentChain(
            intents=["file_read", "file_delete"],
            probability=0.50,
            context_requirements=["file_path"],
            description="查看文件后删除"
        ),
    ]
    
    def __init__(self):
        self.chain_history: Dict[str, List[str]] = defaultdict(list)
    
    def predict_next(self, current_intent: str, memory: DialogueMemory) -> List[Tuple[str, float]]:
        """预测下一个意图"""
        predictions = []
        
        for chain in self.INTENT_CHAINS:
            if current_intent in chain.intents:
                current_index = chain.intents.index(current_intent)
                if current_index < len(chain.intents) - 1:
                    next_intent = chain.intents[current_index + 1]
                    
                    context_satisfied = True
                    for req in chain.context_requirements:
                        if req not in memory.slots or not memory.slots[req].filled:
                            context_satisfied = False
                            break
                    
                    prob = chain.probability if context_satisfied else chain.probability * 0.5
                    predictions.append((next_intent, prob))
        
        recent_intents = memory.get_recent_intents(3)
        if tuple(recent_intents[-2:]) in self.chain_history:
            for next_intent in self.chain_history[tuple(recent_intents[-2:])]:
                predictions.append((next_intent, 0.6))
        
        predictions.sort(key=lambda x: x[1], reverse=True)
        return predictions[:3]
    
    def record_chain(self, intents: List[str]):
        """记录意图链"""
        if len(intents) >= 2:
            key = tuple(intents[:-1])
            self.chain_history[key].append(intents[-1])


class ContextAwareDetector:
    """上下文感知检测器"""
    
    INTENT_SLOTS = {
        "file_create": [
            Slot("file_path", required=True, prompt="请提供文件路径"),
            Slot("content", required=False)
        ],
        "file_read": [
            Slot("file_path", required=True, prompt="请提供要读取的文件路径")
        ],
        "file_write": [
            Slot("file_path", required=True, prompt="请提供文件路径"),
            Slot("content", required=True, prompt="请提供要写入的内容")
        ],
        "file_delete": [
            Slot("file_path", required=True, prompt="请提供要删除的文件路径")
        ],
        "file_list": [
            Slot("directory", required=False, prompt="请提供目录路径")
        ],
        "app_open": [
            Slot("app_name", required=True, prompt="请提供应用名称")
        ],
        "url_open": [
            Slot("url", required=True, prompt="请提供网址", validation_regex=r"https?://\S+")
        ],
        "screenshot": [],
        "mouse_click": [
            Slot("x", required=True, prompt="请提供X坐标"),
            Slot("y", required=True, prompt="请提供Y坐标")
        ],
        "keyboard_type": [
            Slot("text", required=True, prompt="请提供要输入的文本")
        ]
    }
    
    CONTEXT_KEYWORDS = {
        "它": "reference_previous",
        "这个": "reference_current",
        "那个": "reference_previous",
        "刚才": "reference_previous_action",
        "继续": "continue_action",
        "重复": "repeat_action",
        "再": "repeat_action",
        "然后": "sequence_next",
        "接着": "sequence_next",
        "之后": "sequence_next"
    }
    
    def __init__(self):
        self.memories: Dict[str, DialogueMemory] = {}
        self.chain_predictor = IntentChainPredictor()
        self._lock = threading.Lock()
    
    def get_memory(self, session_id: str) -> DialogueMemory:
        """获取对话记忆"""
        with self._lock:
            if session_id not in self.memories:
                self.memories[session_id] = DialogueMemory(session_id)
            return self.memories[session_id]
    
    def detect_with_context(
        self,
        message: str,
        session_id: str,
        base_intent: Optional[str] = None,
        base_params: Optional[Dict[str, Any]] = None
    ) -> Tuple[Optional[str], Dict[str, Any], float, DialogueState]:
        """
        结合上下文检测意图
        
        Args:
            message: 用户消息
            session_id: 会话ID
            base_intent: 基础检测结果
            base_params: 基础参数
            
        Returns:
            (intent_name, params, confidence_boost, state)
        """
        memory = self.get_memory(session_id)
        params = base_params or {}
        confidence_boost = 0.0
        
        for keyword, action in self.CONTEXT_KEYWORDS.items():
            if keyword in message:
                if action == "reference_previous":
                    resolved = memory.resolve_reference("那个")
                    if resolved:
                        if "file_path" not in params:
                            params["file_path"] = resolved
                        confidence_boost += 0.15
                
                elif action == "reference_current":
                    resolved = memory.resolve_reference("这个")
                    if resolved:
                        if "file_path" not in params:
                            params["file_path"] = resolved
                        confidence_boost += 0.15
                
                elif action == "reference_previous_action":
                    recent_intents = memory.get_recent_intents(1)
                    if recent_intents:
                        base_intent = recent_intents[0]
                        confidence_boost += 0.2
                
                elif action == "continue_action":
                    if memory.current_intent:
                        base_intent = memory.current_intent
                        confidence_boost += 0.25
                
                elif action == "repeat_action":
                    recent_intents = memory.get_recent_intents(1)
                    if recent_intents:
                        base_intent = recent_intents[0]
                        confidence_boost += 0.2
        
        if base_intent:
            self._init_slots(memory, base_intent)
            
            for key, value in params.items():
                memory.fill_slot(key, value)
            
            missing_slots = memory.get_missing_slots()
            if missing_slots:
                memory.state = DialogueState.COLLECTING_PARAMS
            else:
                memory.state = DialogueState.IDLE
        
        return base_intent, params, min(confidence_boost, 0.3), memory.state
    
    def _init_slots(self, memory: DialogueMemory, intent: str):
        """初始化槽位"""
        memory.clear_slots()
        
        slots = self.INTENT_SLOTS.get(intent, [])
        for slot in slots:
            memory.set_slot(
                name=slot.name,
                value=None,
                required=slot.required,
                prompt=slot.prompt,
                validation_regex=slot.validation_regex
            )
    
    def get_missing_slot_prompt(self, session_id: str) -> Optional[str]:
        """获取缺失槽位的提示"""
        memory = self.get_memory(session_id)
        missing = memory.get_missing_slots()
        
        if missing:
            return missing[0].prompt
        return None
    
    def predict_next_intent(self, session_id: str) -> List[Tuple[str, float]]:
        """预测下一个意图"""
        memory = self.get_memory(session_id)
        
        if memory.current_intent:
            return self.chain_predictor.predict_next(memory.current_intent, memory)
        
        return []
    
    def update_after_action(
        self,
        session_id: str,
        intent: str,
        params: Dict[str, Any],
        success: bool,
        system_response: str = ""
    ):
        """动作执行后更新上下文"""
        memory = self.get_memory(session_id)
        
        entities = self._extract_entities(params)
        
        memory.add_turn(
            user_message="",
            intent=intent,
            params=params,
            system_response=system_response,
            entities=entities
        )
        
        memory.current_intent = intent
        
        if success:
            memory.state = DialogueState.FOLLOW_UP
        else:
            memory.state = DialogueState.ERROR
    
    def _extract_entities(self, params: Dict[str, Any]) -> List[Entity]:
        """从参数中提取实体"""
        entities = []
        
        entity_type_map = {
            "file_path": EntityType.FILE_PATH,
            "directory": EntityType.DIRECTORY,
            "app_name": EntityType.APP_NAME,
            "url": EntityType.URL,
            "text": EntityType.TEXT,
            "x": EntityType.COORDINATE,
            "y": EntityType.COORDINATE
        }
        
        for key, value in params.items():
            if key in entity_type_map and value:
                entities.append(Entity(
                    type=entity_type_map[key],
                    value=value,
                    confidence=1.0,
                    source="param"
                ))
        
        return entities
    
    def get_dialogue_summary(self, session_id: str) -> Dict[str, Any]:
        """获取对话摘要"""
        memory = self.get_memory(session_id)
        
        return {
            "turn_count": len(memory.turns),
            "current_intent": memory.current_intent,
            "state": memory.state.value,
            "recent_intents": memory.get_recent_intents(5),
            "predicted_next": self.predict_next_intent(session_id),
            "missing_slots": [s.name for s in memory.get_missing_slots()],
            "memory": memory.to_dict()
        }
    
    def clear_session(self, session_id: str):
        """清除会话"""
        with self._lock:
            if session_id in self.memories:
                del self.memories[session_id]


class MultiTurnIntentProcessor:
    """多轮意图处理器"""
    
    def __init__(self, detector, context_detector: Optional[ContextAwareDetector] = None):
        self.detector = detector
        self.context_detector = context_detector or ContextAwareDetector()
    
    def process(
        self,
        message: str,
        session_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        处理多轮对话意图
        
        Args:
            message: 用户消息
            session_id: 会话ID
            context: 额外上下文
            
        Returns:
            处理结果
        """
        base_result = self.detector.detect(message, session_id, context)
        
        intent, params, boost, state = self.context_detector.detect_with_context(
            message,
            session_id,
            base_result.intent_type if hasattr(base_result, 'intent_type') else base_result.action,
            base_result.params if hasattr(base_result, 'params') else {}
        )
        
        if hasattr(base_result, 'confidence'):
            base_result.confidence = min(base_result.confidence + boost, 1.0)
        if hasattr(base_result, 'params'):
            base_result.params = params
        if hasattr(base_result, 'intent_type'):
            base_result.intent_type = intent
        
        missing_prompt = self.context_detector.get_missing_slot_prompt(session_id)
        
        predicted_next = self.context_detector.predict_next_intent(session_id)
        
        return {
            "result": base_result,
            "state": state.value,
            "missing_slot_prompt": missing_prompt,
            "predicted_next_intents": predicted_next,
            "dialogue_summary": self.context_detector.get_dialogue_summary(session_id)
        }
    
    def confirm_action(self, session_id: str, confirmed: bool) -> Dict[str, Any]:
        """确认动作"""
        memory = self.context_detector.get_memory(session_id)
        
        if confirmed:
            memory.state = DialogueState.EXECUTING
            return {
                "status": "confirmed",
                "intent": memory.current_intent,
                "params": {k: v.value for k, v in memory.slots.items() if v.filled}
            }
        else:
            memory.state = DialogueState.IDLE
            memory.clear_slots()
            return {
                "status": "cancelled"
            }
    
    def record_result(
        self,
        session_id: str,
        intent: str,
        params: Dict[str, Any],
        success: bool,
        response: str = ""
    ):
        """记录执行结果"""
        self.context_detector.update_after_action(
            session_id, intent, params, success, response
        )


def create_context_detector() -> ContextAwareDetector:
    """创建上下文感知检测器"""
    return ContextAwareDetector()


def create_multi_turn_processor(detector) -> MultiTurnIntentProcessor:
    """创建多轮意图处理器"""
    return MultiTurnIntentProcessor(detector)
