from core.runtime_policy import build_runtime_policy


def test_runtime_policy_prefers_low_memory_local_stack_for_llama_cpp(monkeypatch):
    monkeypatch.setattr(
        "core.runtime_policy.get_device_info",
        lambda use_cache=False: {"cuda_available": True, "memory_total": 6.0},
    )

    policy = build_runtime_policy(
        model_path="demo-model.gguf",
        backend="llama-cpp",
        options={"num_ctx": 4096, "num_batch": 4},
    )

    assert policy["hardware_profile"]["profile"] == "gpu-8gb"
    assert policy["quantization"]["quant_type"] == "gguf"
    assert policy["n_gpu_layers"] == -1
    assert policy["num_ctx"] == 4096


def test_runtime_policy_selects_int4_for_low_memory_huggingface(monkeypatch):
    monkeypatch.setattr(
        "core.runtime_policy.get_device_info",
        lambda use_cache=False: {"cuda_available": True, "memory_total": 4.0},
    )

    policy = build_runtime_policy(
        model_path="hf-model",
        backend="huggingface",
        options={"num_batch": 2},
    )

    assert policy["load_in_4bit"] is True
    assert policy["load_in_8bit"] is False
    assert policy["enable_batching"] in {True, False}
