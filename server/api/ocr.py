"""
OCR 识别 API
支持图片文字识别，集�?Tesseract OCR 引擎
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import base64
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ocr", tags=["ocr"])

# 线程池用于异步执�?OCR
_ocr_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ocr-")

# 检�?Tesseract 是否可用
try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
    logger.info("Tesseract OCR 引擎已加�?)
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("Tesseract OCR 未安装，OCR 功能将返回占位响�?)

# 语言代码映射
LANGUAGE_MAP = {
    "ch": "chi_sim",      # 简体中�?    "ch_tra": "chi_tra",  # 繁体中文
    "en": "eng",          # 英文
    "ja": "jpn",          # 日文
    "ko": "kor",          # 韩文
    "de": "deu",          # 德文
    "fr": "fra",          # 法文
    "es": "spa",          # 西班牙文
    "ru": "rus",          # 俄文
}


class OCRRequest(BaseModel):
    """OCR 请求"""
    image_base64: str = Field(..., description="Base64 编码的图片数�?)
    language: str = Field(default="ch", description="语言代码: ch, en, ja, ko")
    detect_language: bool = Field(default=False, description="自动检测语言")
    preserve_interword_spaces: bool = Field(default=True, description="保留单词间空�?)


class OCRRegion(BaseModel):
    """OCR 识别区域"""
    bounding_box: str = Field(..., description="边界框坐�?x,y,width,height")
    text: str = Field(..., description="识别的文�?)
    confidence: float = Field(..., description="置信�?0-1")


class OCRResponse(BaseModel):
    """OCR 响应"""
    text: str = Field(..., description="识别的完整文�?)
    confidence: float = Field(default=0.0, description="平均置信�?)
    regions: List[OCRRegion] = Field(default_factory=list, description="识别区域列表")
    language: str = Field(default="", description="检测到的语言")
    processing_time: float = Field(default=0.0, description="处理时间（秒�?)
    engine: str = Field(default="tesseract", description="使用�?OCR 引擎")


class BatchOCRRequest(BaseModel):
    """批量 OCR 请求"""
    images: List[str] = Field(..., description="Base64 编码的图片列�?)
    language: str = Field(default="ch", description="语言代码")


class BatchOCRResponse(BaseModel):
    """批量 OCR 响应"""
    results: List[OCRResponse] = Field(default_factory=list)
    total_processing_time: float = Field(default=0.0)


class LanguageInfo(BaseModel):
    """语言信息"""
    code: str
    name: str
    tesseract_code: str
    available: bool


def _perform_ocr(image_data: bytes, language: str = "ch") -> dict:
    """
    执行 OCR 识别（同步函数，在线程池中运行）
    
    Args:
        image_data: 图片二进制数�?        language: 语言代码
        
    Returns:
        OCR 结果字典
    """
    if not TESSERACT_AVAILABLE:
        return {
            "text": "OCR 功能需要安�?Tesseract OCR。请运行: pip install pytesseract pillow",
            "confidence": 0.0,
            "regions": [],
            "language": language,
            "engine": "placeholder",
        }
    
    start_time = datetime.now()
    
    try:
        # 打开图片
        image = Image.open(BytesIO(image_data))
        
        # 转换语言代码
        tess_lang = LANGUAGE_MAP.get(language, "eng")
        
        # 执行 OCR
        data = pytesseract.image_to_data(
            image,
            lang=tess_lang,
            output_type=pytesseract.Output.DICT
        )
        
        # 提取文本
        full_text = pytesseract.image_to_string(image, lang=tess_lang)
        
        # 解析区域
        regions = []
        confidences = []
        n_boxes = len(data['text'])
        
        for i in range(n_boxes):
            if int(data['conf'][i]) > 0:  # 只保留有置信度的区域
                text = data['text'][i].strip()
                if text:  # 只保留非空文�?                    confidence = int(data['conf'][i]) / 100.0
                    confidences.append(confidence)
                    
                    regions.append(OCRRegion(
                        bounding_box=f"{data['left'][i]},{data['top'][i]},{data['width'][i]},{data['height'][i]}",
                        text=text,
                        confidence=confidence
                    ))
        
        # 计算平均置信�?        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return {
            "text": full_text.strip(),
            "confidence": round(avg_confidence, 3),
            "regions": regions,
            "language": language,
            "processing_time": round(processing_time, 3),
            "engine": "tesseract",
        }
        
    except Exception as e:
        logger.error(f"OCR 处理失败: {e}")
        return {
            "text": f"OCR 处理失败: {str(e)}",
            "confidence": 0.0,
            "regions": [],
            "language": language,
            "processing_time": 0.0,
            "engine": "error",
        }


@router.post("", response_model=OCRResponse)
async def ocr_image(request: OCRRequest):
    """
    对单张图片执�?OCR 识别
    
    - **image_base64**: Base64 编码的图片数�?    - **language**: 语言代码 (ch=中文, en=英文, ja=日文, ko=韩文)
    """
    try:
        # 解码 Base64
        image_data = base64.b64decode(request.image_base64)
        
        # 在线程池中执�?OCR（避免阻塞）
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _ocr_executor,
            _perform_ocr,
            image_data,
            request.language
        )
        
        return OCRResponse(**result)
        
    except Exception as e:
        logger.error(f"OCR API 错误: {e}")
        raise HTTPException(status_code=500, detail=f"OCR 处理失败: {str(e)}")


@router.post("/batch", response_model=BatchOCRResponse)
async def batch_ocr(request: BatchOCRRequest):
    """
    批量 OCR 识别
    
    - **images**: Base64 编码的图片列表（最�?10 张）
    """
    if len(request.images) > 10:
        raise HTTPException(status_code=400, detail="最多支�?10 张图�?)
    
    start_time = datetime.now()
    results = []
    
    loop = asyncio.get_event_loop()
    
    for image_base64 in request.images:
        try:
            image_data = base64.b64decode(image_base64)
            result = await loop.run_in_executor(
                _ocr_executor,
                _perform_ocr,
                image_data,
                request.language
            )
            results.append(OCRResponse(**result))
        except Exception as e:
            logger.error(f"批量 OCR 错误: {e}")
            results.append(OCRResponse(
                text="",
                confidence=0.0,
                regions=[],
                engine="error"
            ))
    
    total_time = (datetime.now() - start_time).total_seconds()
    
    return BatchOCRResponse(
        results=results,
        total_processing_time=round(total_time, 3)
    )


@router.get("/languages", response_model=List[LanguageInfo])
async def get_supported_languages():
    """获取支持�?OCR 语言列表"""
    languages = []
    
    for code, name in [("ch", "中文"), ("en", "英文"), ("ja", "日文"), 
                       ("ko", "韩文"), ("de", "德文"), ("fr", "法文"),
                       ("es", "西班牙文"), ("ru", "俄文")]:
        tess_code = LANGUAGE_MAP.get(code, code)
        
        # 检查语言包是否可�?        available = TESSERACT_AVAILABLE
        if TESSERACT_AVAILABLE:
            try:
                import pytesseract
                langs = pytesseract.get_languages()
                available = tess_code in langs
            except:
                available = False
        
        languages.append(LanguageInfo(
            code=code,
            name=name,
            tesseract_code=tess_code,
            available=available
        ))
    
    return languages


@router.get("/status")
async def get_ocr_status():
    """获取 OCR 引擎状�?""
    return {
        "engine": "tesseract" if TESSERACT_AVAILABLE else "placeholder",
        "available": TESSERACT_AVAILABLE,
        "message": "OCR 引擎就绪" if TESSERACT_AVAILABLE else "请安�?Tesseract OCR: pip install pytesseract pillow",
        "supported_languages": list(LANGUAGE_MAP.keys()) if TESSERACT_AVAILABLE else [],
    }
