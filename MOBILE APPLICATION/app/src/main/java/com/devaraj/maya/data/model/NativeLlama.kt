package com.devaraj.maya.data.model

/**
 * JNI bridge to the vendored llama.cpp library (Phase 9).
 * The native library is built by CMake for arm64-v8a and x86_64.
 */
object NativeLlama {

    init {
        runCatching { System.loadLibrary("maya_llama") }
    }

    external fun status(): String
    external fun isLoaded(): Boolean
    external fun loadModel(path: String): Boolean
    external fun generate(prompt: String, maxTokens: Int): String
    external fun generateStream(prompt: String, maxTokens: Int, onToken: (String) -> Unit): String
    external fun cancel()
    external fun unload()

    fun safeStatus(): String = runCatching { status() }
        .getOrElse { "Native lib unavailable: ${it.message}" }

    fun safeIsLoaded(): Boolean = runCatching { isLoaded() }.getOrDefault(false)

    fun safeLoad(path: String): Boolean = runCatching { loadModel(path) }.getOrDefault(false)

    fun safeGenerate(prompt: String, maxTokens: Int = 256): String =
        runCatching { generate(prompt, maxTokens) }
            .getOrElse { "Generation failed: ${it.message}" }

    fun safeGenerateStream(
        prompt: String,
        maxTokens: Int,
        onToken: (String) -> Unit,
    ): Result<String> = runCatching { generateStream(prompt, maxTokens, onToken) }
}
