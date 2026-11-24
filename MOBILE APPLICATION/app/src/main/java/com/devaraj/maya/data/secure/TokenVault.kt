package com.devaraj.maya.data.secure

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Android Keystore backed token storage (plan §12.4).
 *
 * Each device token is encrypted with AES-256-GCM; the file holds IV +
 * ciphertext. Tokens are never written to Room, logs or backups
 * (allowBackup=false).
 */
class TokenVault(private val context: Context) : TokenStore {

    private val keyAlias = "maya_token_key"
    private val transformation = "AES/GCM/NoPadding"
    private val gcmTagBits = 128
    private val ivBytes = 12

    /** Avoid a Keystore decrypt per HTTP request; cleared on delete. */
    private val cache = mutableMapOf<String, String?>()

    private fun secureDir(): File = File(context.filesDir, "secure").apply { mkdirs() }

    private fun fileFor(deviceId: String): File {
        val safe = deviceId.replace(Regex("[^A-Za-z0-9_-]"), "_")
        return File(secureDir(), "token_$safe.bin")
    }

    private fun secretKey(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getEntry(keyAlias, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }

        val generator = KeyGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_AES,
            "AndroidKeyStore",
        )
        generator.init(
            KeyGenParameterSpec.Builder(
                keyAlias,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return generator.generateKey()
    }

    override fun save(deviceId: String, token: String) {
        val cipher = Cipher.getInstance(transformation)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        val iv = cipher.iv
        val ciphertext = cipher.doFinal(token.toByteArray(Charsets.UTF_8))
        fileFor(deviceId).writeBytes(iv + ciphertext)
        cache[deviceId] = token
    }

    override fun load(deviceId: String): String? {
        if (cache.containsKey(deviceId)) return cache[deviceId]
        val file = fileFor(deviceId)
        if (!file.exists()) {
            cache[deviceId] = null
            return null
        }
        val bytes = file.readBytes()
        if (bytes.size <= ivBytes) {
            cache[deviceId] = null
            return null
        }
        val iv = bytes.copyOfRange(0, ivBytes)
        val ciphertext = bytes.copyOfRange(ivBytes, bytes.size)
        val cipher = Cipher.getInstance(transformation)
        cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(gcmTagBits, iv))
        val token = String(cipher.doFinal(ciphertext), Charsets.UTF_8)
        cache[deviceId] = token
        return token
    }

    override fun delete(deviceId: String) {
        fileFor(deviceId).delete()
        cache.remove(deviceId)
    }

    override fun deleteAll() {
        secureDir().listFiles()?.forEach { it.delete() }
        cache.clear()
    }
}
