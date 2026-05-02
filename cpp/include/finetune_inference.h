#pragma once

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*finetune_stream_callback)(const char* chunk, void* user_data);

int finetune_initialize(const char* base_url);
int finetune_generate(const char* model, const char* backend, const char* prompt);
int finetune_stream_generate(
    const char* model,
    const char* backend,
    const char* prompt,
    finetune_stream_callback callback,
    void* user_data
);

#ifdef __cplusplus
}
#endif
