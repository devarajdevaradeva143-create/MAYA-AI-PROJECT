package com.devaraj.maya.data.secure

/**
 * Contract used by pairing/connection logic. [TokenVault] is the production
 * implementation; tests use an in-memory fake.
 */
interface TokenStore {
    fun save(deviceId: String, token: String)
    fun load(deviceId: String): String?
    fun delete(deviceId: String)
    fun deleteAll()
}
