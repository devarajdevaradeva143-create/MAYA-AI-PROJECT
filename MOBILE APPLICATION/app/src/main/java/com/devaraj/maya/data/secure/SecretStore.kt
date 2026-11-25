package com.devaraj.maya.data.secure

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * AES-256-GCM encryption backed by the Android Keystore.
 *
 * The key material never leaves the device's secure hardware, so the
 * ciphertext we keep in DataStore is useless on any other device or backup.
 *
 * Format: Base64(IV || ciphertext || tag).
 */
class SecretStore(private val context: Context) {

    private val keyAlias = "maya_secret_key"
    private val transformation = "AES/GCM/NoPadding"
    private val gcmTagBits = 128
    private val ivBytes = 12

    /** Ciphertext -> plaintext, so the UI never pays a Keystore round-trip twice. */
    private val cache = mutableMapOf<String, String>()

    fun encrypt(plain: String): String {
        if (plain.isEmpty()) return ""
        val cipher = Cipher.getInstance(transformation)
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        val iv = cipher.iv
        val cipherText = cipher.doFinal(plain.toByteArray(Charsets.UTF_8))
        val combined = ByteArray(iv.size + cipherText.size)
        iv.copyInto(combined)
        cipherText.copyInto(combined, iv.size)
        return Base64.encodeToString(combined, Base64.NO_WRAP)
    }

    /**
     * Decrypt [blob]. Returns an empty string when the blob is corrupt or the
     * Keystore key was lost (for example after a restore to a new phone) —
     * callers treat that as "no key configured" and ask the user to paste again.
     */
    fun decrypt(blob: String): String {
        if (blob.isEmpty()) return ""
        cache[blob]?.let { return it }
        return try {
            val raw = Base64.decode(blob, Base64.DEFAULT)
            if (raw.size <= ivBytes) return ""
            val iv = raw.copyOfRange(0, ivBytes)
            val cipherText = raw.copyOfRange(ivBytes, raw.size)
            val cipher = Cipher.getInstance(transformation)
            cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), GCMParameterSpec(gcmTagBits, iv))
            val plain = String(cipher.doFinal(cipherText), Charsets.UTF_8)
            cache[blob] = plain
            plain
        } catch (_: Exception) {
            ""
        }
    }

    fun clearCache() {
        cache.clear()
    }

    private fun getOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (keyStore.getEntry(keyAlias, null) as? KeyStore.SecretKeyEntry)?.let {
            return it.secretKey
        }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
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

    private companion object {
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
    }
}
