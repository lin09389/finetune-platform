#include "finetune_inference.h"

#include <iostream>

void on_chunk(const char* chunk, void* user_data) {
    (void)user_data;
    std::cout << chunk << std::endl;
}

int main() {
    finetune_initialize("http://127.0.0.1:8010");
    finetune_generate("your-local-model", "llama-cpp", "请用一句话介绍这个平台。");
    finetune_stream_generate("your-local-model", "llama-cpp", "继续补充一句。", on_chunk, nullptr);
    return 0;
}
