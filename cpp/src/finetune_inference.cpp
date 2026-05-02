#include "finetune_inference.h"

#include <iostream>
#include <string>

namespace {
std::string g_base_url = "http://127.0.0.1:8010";
}

int finetune_initialize(const char* base_url) {
    if (base_url != nullptr) {
        g_base_url = base_url;
    }
    return 0;
}

int finetune_generate(const char* model, const char* backend, const char* prompt) {
    std::cout << "Use REST/gRPC bridge to call " << g_base_url
              << " model=" << (model ? model : "")
              << " backend=" << (backend ? backend : "")
              << " prompt=" << (prompt ? prompt : "") << std::endl;
    return 0;
}

int finetune_stream_generate(
    const char* model,
    const char* backend,
    const char* prompt,
    finetune_stream_callback callback,
    void* user_data
) {
    (void)model;
    (void)backend;
    (void)prompt;
    if (callback != nullptr) {
        callback("stream bridge placeholder", user_data);
    }
    return 0;
}
