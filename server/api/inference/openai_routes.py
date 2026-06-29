import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse

from api.inference.openai_schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionStreamResponse,
    ChatCompletionMessage,
    Choice,
    StreamChoice,
    DeltaMessage,
    Usage,
    ModelListResponse,
    ModelCard
)
from core.inference.engine_factory import get_engine, InferenceEngineFactory
from core.inference.engine_base import ChatRequest, ChatMessage, StreamChunk

logger = logging.getLogger(__name__)

router = APIRouter(tags=["OpenAI Compatible API"])


@router.get("/v1/models", response_model=ModelListResponse)
async def list_models():
    """List available models across all backends."""
    # Since different engines might have different loaded models, 
    # we return a static list or dynamically query them. 
    # For a unified gateway, returning the default engine's models is a start.
    engine = get_engine()
    models = engine.get_available_models()
    
    # Also add known aliases or defaults
    if not models:
        models = ["default"]
        
    cards = [ModelCard(id=m) for m in models]
    return ModelListResponse(data=cards)


async def _stream_generator(engine, chat_request: ChatRequest, model_name: str) -> AsyncGenerator[str, None]:
    """Convert engine StreamChunk to OpenAI SSE format."""
    try:
        # Check if the engine supports chat_stream natively
        if hasattr(engine, "chat_stream"):
            generator = engine.chat_stream(chat_request)
        else:
            # Fallback to chat -> generate text -> stream (which might just be a single chunk)
            # Or if it's a model that needs stringification first
            logger.warning(f"Engine {engine.name} does not support chat_stream natively, falling back to chat.")
            response = await engine.chat(chat_request)
            chunk = StreamChunk(content=response.text, done=True, tokens_so_far=response.tokens_generated, finish_reason=response.finish_reason)
            
            async def _mock_gen():
                yield chunk
            generator = _mock_gen()

        async for chunk in generator:
            stream_choice = StreamChoice(
                index=0,
                delta=DeltaMessage(role="assistant", content=chunk.content) if chunk.content else DeltaMessage(),
                finish_reason=chunk.finish_reason if chunk.done else None
            )
            
            resp = ChatCompletionStreamResponse(
                id="chatcmpl-stream",
                model=model_name,
                choices=[stream_choice]
            )
            yield f"data: {resp.model_dump_json(exclude_none=True)}\n\n"

        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.error(f"Error in stream generator: {e}", exc_info=True)
        # Yield an error delta or just end the stream
        yield "data: [DONE]\n\n"


@router.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest, raw_request: Request):
    """OpenAI compatible chat completions endpoint."""
    try:
        # 1. Resolve Backend
        # We can use a header or default to the primary engine. 
        # In the future, this can be dynamically routed based on model size or quantization.
        backend = raw_request.headers.get("x-backend")
        engine = get_engine(backend=backend)
        
        if not engine:
            raise HTTPException(status_code=503, detail="No suitable backend engine available.")

        # 2. Convert Request
        core_messages = []
        system_prompt = None
        for msg in request.messages:
            if msg.role == "system" and system_prompt is None:
                system_prompt = msg.content
            else:
                core_messages.append(ChatMessage(role=msg.role, content=msg.content or ""))

        chat_request = ChatRequest(
            model_id=request.model,
            messages=core_messages,
            system_prompt=system_prompt,
            temperature=request.temperature or 0.7,
            top_p=request.top_p or 0.9,
            max_tokens=request.max_tokens or 1024,
            metadata={"stop": request.stop}
        )

        # 3. Handle Streaming
        if request.stream:
            return StreamingResponse(
                _stream_generator(engine, chat_request, request.model),
                media_type="text/event-stream"
            )

        # 4. Handle Sync Response
        response = await engine.chat(chat_request)

        # 5. Convert Response
        choice = Choice(
            index=0,
            message=ChatCompletionMessage(role="assistant", content=response.text),
            finish_reason=response.finish_reason
        )

        usage = Usage(
            completion_tokens=response.tokens_generated,
            prompt_tokens=0, # If engine doesn't provide prompt tokens
            total_tokens=response.tokens_generated
        )

        return ChatCompletionResponse(
            id=f"chatcmpl-{int(response.processing_time_ms)}",
            model=request.model,
            choices=[choice],
            usage=usage
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OpenAI API Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
