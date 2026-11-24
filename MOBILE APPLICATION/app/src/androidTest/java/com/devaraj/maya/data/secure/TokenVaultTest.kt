package com.devaraj.maya.data.secure

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import java.io.File
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Android Keystore round-trip (plan §12.4). Needs a real device/emulator:
 * the JVM does not provide the AndroidKeyStore provider.
 */
@RunWith(AndroidJUnit4::class)
class TokenVaultTest {

    private lateinit var context: Context
    private lateinit var vault: TokenVault

    @Before
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        vault = TokenVault(context)
        vault.deleteAll()
    }

    @After
    fun tearDown() {
        vault.deleteAll()
    }

    @Test
    fun savesAndLoadsToken() {
        vault.save("device-1", "token-value-123")
        assertEquals("token-value-123", vault.load("device-1"))
    }

    @Test
    fun overwritesExistingToken() {
        vault.save("device-1", "old-token")
        vault.save("device-1", "new-token")
        assertEquals("new-token", vault.load("device-1"))
    }

    @Test
    fun tokenIsEncryptedOnDisk() {
        val plaintext = "plain-secret-123456"
        vault.save("device-2", plaintext)

        val dir = File(context.filesDir, "secure")
        val raw = dir.listFiles().orEmpty().filter { it.isFile }
            .flatMap { it.readBytes().toList() }
            .toByteArray()
        val asText = String(raw, Charsets.ISO_8859_1)

        assertFalse("Token must not be written as plaintext", asText.contains(plaintext))
    }

    @Test
    fun deleteRemovesToken() {
        vault.save("device-1", "token-value-123")
        vault.delete("device-1")
        assertNull(vault.load("device-1"))
    }

    @Test
    fun deleteAllClearsEveryToken() {
        vault.save("device-1", "one")
        vault.save("device-2", "two")
        vault.deleteAll()
        assertNull(vault.load("device-1"))
        assertNull(vault.load("device-2"))
    }

    @Test
    fun unknownDeviceReturnsNull() {
        assertNull(vault.load("never-saved"))
    }
}
