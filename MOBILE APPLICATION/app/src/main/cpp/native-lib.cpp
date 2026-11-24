#include <jni.h>
#include <android/log.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "llama.h"
#pragma GCC diagnostic ignored "-Wdeprecated-declarations"

#define LOG_TAG "MayaLlama"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

static constexpr uint32_t kContextSize = 2048;

static llama_model* g_model = nullptr;
static llama_context* g_ctx = nullptr;
static llama_sampler* g_smpl = nullptr;
static const llama_vocab* g_vocab = nullptr;
static std::atomic<bool> g_cancel{false};
static std::once_flag g_backend_once;

// ── UTF-8 helpers ──────────────────────────────────────────────────────────
// NewStringUTF only accepts modified UTF-8, so 4-byte characters (emoji) can
// crash it. Decode manually to UTF-16 instead.

static jstring utf8_to_jstring(JNIEnv* env, const std::string& utf8) {
    if (utf8.empty()) return env->NewStringUTF("");

    std::vector<jchar> out;
    out.reserve(utf8.size());

    size_t i = 0;
    while (i < utf8.size()) {
        unsigned char c = static_cast<unsigned char>(utf8[i]);
        uint32_t cp = 0xFFFD;
        size_t extra = 0;

        if (c < 0x80) {
            cp = c;
        } else if ((c & 0xE0) == 0xC0) {
            cp = c & 0x1F;
            extra = 1;
        } else if ((c & 0xF0) == 0xE0) {
            cp = c & 0x0F;
            extra = 2;
        } else if ((c & 0xF8) == 0xF0) {
            cp = c & 0x07;
            extra = 3;
        } else {
            out.push_back(0xFFFD);
            ++i;
            continue;
        }

        if (i + extra >= utf8.size()) {
            out.push_back(0xFFFD);
            break;
        }

        bool valid = true;
        for (size_t k = 1; k <= extra; ++k) {
            unsigned char cc = static_cast<unsigned char>(utf8[i + k]);
            if ((cc & 0xC0) != 0x80) {
                valid = false;
                break;
            }
            cp = (cp << 6) | (cc & 0x3F);
        }
        if (!valid || cp > 0x10FFFF) {
            out.push_back(0xFFFD);
            ++i;
            continue;
        }

        if (cp >= 0x10000) {
            cp -= 0x10000;
            out.push_back(static_cast<jchar>(0xD800 + (cp >> 10)));
            out.push_back(static_cast<jchar>(0xDC00 + (cp & 0x3FF)));
        } else {
            out.push_back(static_cast<jchar>(cp));
        }
        i += extra + 1;
    }

    return env->NewString(out.data(), static_cast<jsize>(out.size()));
}

// Hold back a trailing incomplete multi-byte sequence between tokens.
class Utf8Chunker {
public:
    void append(const char* data, size_t n) { pending_.append(data, n); }

    std::string takeComplete() {
        size_t cut = completePrefix();
        if (cut == 0) return {};
        std::string out = pending_.substr(0, cut);
        pending_.erase(0, cut);
        return out;
    }

    std::string flush() {
        std::string out;
        out.swap(pending_);
        return out;
    }

private:
    std::string pending_;

    size_t completePrefix() const {
        if (pending_.empty()) return 0;
        size_t start = pending_.size() - 1;
        while (start > 0 && (static_cast<unsigned char>(pending_[start]) & 0xC0) == 0x80) {
            --start;
        }
        unsigned char c = static_cast<unsigned char>(pending_[start]);
        size_t need = 1;
        if ((c & 0x80) == 0) {
            need = 1;
        } else if ((c & 0xE0) == 0xC0) {
            need = 2;
        } else if ((c & 0xF0) == 0xE0) {
            need = 3;
        } else if ((c & 0xF8) == 0xF0) {
            need = 4;
        } else {
            return pending_.size();
        }
        return (start + need <= pending_.size()) ? pending_.size() : start;
    }
};

// ── JNI ────────────────────────────────────────────────────────────────────

extern "C" JNIEXPORT jstring JNICALL
Java_com_devaraj_maya_data_model_NativeLlama_status(JNIEnv* env, jobject /*thiz*/) {
    if (g_model && g_ctx) return env->NewStringUTF("Model loaded.");
    return env->NewStringUTF("No model loaded.");
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_devaraj_maya_data_model_NativeLlama_isLoaded(JNIEnv* /*env*/, jobject /*thiz*/) {
    return (g_model && g_ctx) ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_devaraj_maya_data_model_NativeLlama_loadModel(JNIEnv* env, jobject /*thiz*/, jstring path) {
    const char* cpath = env->GetStringUTFChars(path, nullptr);
    if (!cpath) return JNI_FALSE;
    LOGI("loadModel: %s", cpath);

    auto load_start = std::chrono::steady_clock::now();
    std::call_once(g_backend_once, []() { llama_backend_init(); });
    g_cancel.store(false);

    if (g_smpl) { llama_sampler_free(g_smpl); g_smpl = nullptr; }
    if (g_ctx) { llama_free(g_ctx); g_ctx = nullptr; }
    if (g_model) { llama_model_free(g_model); g_model = nullptr; }
    g_vocab = nullptr;

    llama_model_params mparams = llama_model_default_params();
    mparams.n_gpu_layers = 0; // CPU only on phone

    g_model = llama_model_load_from_file(cpath, mparams);
    env->ReleaseStringUTFChars(path, cpath);

    if (!g_model) {
        LOGE("Failed to load model");
        return JNI_FALSE;
    }
    g_vocab = llama_model_get_vocab(g_model);

    llama_context_params cparams = llama_context_default_params();
    cparams.n_ctx = kContextSize;
    cparams.n_batch = kContextSize;
    cparams.n_ubatch = 512;
    unsigned hw = std::thread::hardware_concurrency();
    if (hw == 0) hw = 4;
    cparams.n_threads = static_cast<int32_t>(std::max(2u, std::min(6u, hw)));
    cparams.n_threads_batch = cparams.n_threads;
    cparams.no_perf = true;

    g_ctx = llama_init_from_model(g_model, cparams);
    if (!g_ctx) {
        LOGE("Failed to create context");
        llama_model_free(g_model);
        g_model = nullptr;
        g_vocab = nullptr;
        return JNI_FALSE;
    }

    llama_sampler_chain_params sparams = llama_sampler_chain_default_params();
    sparams.no_perf = true;
    g_smpl = llama_sampler_chain_init(sparams);
    llama_sampler_chain_add(
        g_smpl,
        llama_sampler_init_penalties(llama_vocab_n_tokens(g_vocab), 64, 1.1f, 0.0f, 0.0f));
    llama_sampler_chain_add(g_smpl, llama_sampler_init_top_k(40));
    llama_sampler_chain_add(g_smpl, llama_sampler_init_top_p(0.9f, 1));
    llama_sampler_chain_add(g_smpl, llama_sampler_init_temp(0.7f));
    llama_sampler_chain_add(g_smpl, llama_sampler_init_dist(LLAMA_DEFAULT_SEED));

    LOGI("Model loaded (ctx=%u, threads=%d)", cparams.n_ctx, cparams.n_threads);
    auto load_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                       std::chrono::steady_clock::now() - load_start)
                       .count();
    LOGI("model load took %lld ms", static_cast<long long>(load_ms));
    return JNI_TRUE;
}

static jstring generate_impl(
    JNIEnv* env,
    jstring prompt,
    jint max_tokens,
    jobject callback,
    bool streaming) {
    if (!g_model || !g_ctx || !g_vocab || !g_smpl) {
        LOGE("generate: model not loaded");
        return utf8_to_jstring(env, "");
    }
    if (!prompt) return utf8_to_jstring(env, "");

    const char* c_prompt = env->GetStringUTFChars(prompt, nullptr);
    if (!c_prompt) return utf8_to_jstring(env, "");
    std::string text(c_prompt);
    env->ReleaseStringUTFChars(prompt, c_prompt);

    if (text.empty()) return utf8_to_jstring(env, "");

    g_cancel.store(false);
    llama_sampler_reset(g_smpl);
    llama_memory_clear(llama_get_memory(g_ctx), true);

    auto gen_start = std::chrono::steady_clock::now();

    int n_prompt = -llama_tokenize(
        g_vocab, text.c_str(), static_cast<int>(text.size()), nullptr, 0, true, true);
    if (n_prompt <= 0) {
        LOGE("generate: tokenize failed (%d)", n_prompt);
        return utf8_to_jstring(env, "");
    }

    std::vector<llama_token> prompt_tokens(static_cast<size_t>(n_prompt));
    int tokenized = llama_tokenize(
        g_vocab,
        text.c_str(),
        static_cast<int>(text.size()),
        prompt_tokens.data(),
        n_prompt,
        true,
        true);
    if (tokenized < 0) {
        LOGE("generate: tokenize failed (%d)", tokenized);
        return utf8_to_jstring(env, "");
    }

    uint32_t n_ctx = llama_n_ctx(g_ctx);
    int room = static_cast<int>(n_ctx) - tokenized - 4;
    if (room <= 0) {
        LOGE("generate: prompt too long (%d tokens, ctx %u)", tokenized, n_ctx);
        return utf8_to_jstring(env, "");
    }
    int to_generate = std::min(static_cast<int>(max_tokens), room);
    if (to_generate <= 0) return utf8_to_jstring(env, "");

    auto tokenize_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                           std::chrono::steady_clock::now() - gen_start)
                           .count();
    LOGI(
        "generate start: prompt=%d tokens, max=%d, tokenize=%lld ms",
        tokenized,
        to_generate,
        static_cast<long long>(tokenize_ms));

    llama_batch batch = llama_batch_get_one(prompt_tokens.data(), tokenized);
    if (llama_decode(g_ctx, batch) != 0) {
        LOGE("generate: prompt decode failed");
        return utf8_to_jstring(env, "");
    }

    auto prompt_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                         std::chrono::steady_clock::now() - gen_start)
                         .count();
    LOGI("prompt decoded in %lld ms", static_cast<long long>(prompt_ms));

    jclass callback_class = nullptr;
    jmethodID callback_invoke = nullptr;
    if (streaming && callback) {
        callback_class = env->GetObjectClass(callback);
        callback_invoke = env->GetMethodID(
            callback_class, "invoke", "(Ljava/lang/Object;)Ljava/lang/Object;");
        if (!callback_invoke) {
            env->ExceptionClear();
            callback_invoke = nullptr;
        }
    }

    std::string result;
    Utf8Chunker chunker;
    int generated = 0;
    bool first_token = true;

    for (; generated < to_generate; ++generated) {
        if (g_cancel.load()) break;

        llama_token new_token = llama_sampler_sample(g_smpl, g_ctx, -1);
        if (llama_vocab_is_eog(g_vocab, new_token)) break;

        if (first_token) {
            first_token = false;
            auto first_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                                std::chrono::steady_clock::now() - gen_start)
                                .count();
            LOGI("first token after %lld ms", static_cast<long long>(first_ms));
        }

        char buf[512];
        int n = llama_token_to_piece(g_vocab, new_token, buf, sizeof(buf), 0, false);
        if (n < 0) break;
        result.append(buf, static_cast<size_t>(n));
        chunker.append(buf, static_cast<size_t>(n));

        if (callback_invoke) {
            std::string piece = chunker.takeComplete();
            if (!piece.empty()) {
                jstring js = utf8_to_jstring(env, piece);
                env->CallObjectMethod(callback, callback_invoke, js);
                env->DeleteLocalRef(js);
                if (env->ExceptionCheck()) {
                    env->ExceptionClear();
                    break;
                }
            }
        }

        llama_batch next = llama_batch_get_one(&new_token, 1);
        if (llama_decode(g_ctx, next) != 0) break;
    }

    if (callback_invoke) {
        std::string tail = chunker.flush();
        if (!tail.empty()) {
            jstring js = utf8_to_jstring(env, tail);
            env->CallObjectMethod(callback, callback_invoke, js);
            env->DeleteLocalRef(js);
            if (env->ExceptionCheck()) env->ExceptionClear();
        }
    }
    if (callback_class) env->DeleteLocalRef(callback_class);

    auto total_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                        std::chrono::steady_clock::now() - gen_start)
                        .count();
    double tokens_per_sec = total_ms > 0
        ? (static_cast<double>(generated) * 1000.0 / static_cast<double>(total_ms))
        : 0.0;
    LOGI(
        "generate: %d tokens (prompt=%d, cancel=%d) in %lld ms (%.2f tok/s)",
        generated,
        tokenized,
        static_cast<int>(g_cancel.load()),
        static_cast<long long>(total_ms),
        tokens_per_sec);
    return utf8_to_jstring(env, result);
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_devaraj_maya_data_model_NativeLlama_generate(
    JNIEnv* env,
    jobject /*thiz*/,
    jstring prompt,
    jint max_tokens) {
    return generate_impl(env, prompt, max_tokens, nullptr, false);
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_devaraj_maya_data_model_NativeLlama_generateStream(
    JNIEnv* env,
    jobject /*thiz*/,
    jstring prompt,
    jint max_tokens,
    jobject callback) {
    return generate_impl(env, prompt, max_tokens, callback, true);
}

extern "C" JNIEXPORT void JNICALL
Java_com_devaraj_maya_data_model_NativeLlama_cancel(JNIEnv* /*env*/, jobject /*thiz*/) {
    g_cancel.store(true);
    LOGI("cancel requested");
}

extern "C" JNIEXPORT void JNICALL
Java_com_devaraj_maya_data_model_NativeLlama_unload(JNIEnv* /*env*/, jobject /*thiz*/) {
    g_cancel.store(true);
    if (g_smpl) { llama_sampler_free(g_smpl); g_smpl = nullptr; }
    if (g_ctx) { llama_free(g_ctx); g_ctx = nullptr; }
    if (g_model) { llama_model_free(g_model); g_model = nullptr; }
    g_vocab = nullptr;
    LOGI("unloaded");
}
