package com.devaraj.maya.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.devaraj.maya.data.local.entity.DeviceEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface DeviceDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(device: DeviceEntity)

    @Query("SELECT * FROM devices ORDER BY last_seen DESC")
    fun observeAll(): Flow<List<DeviceEntity>>

    @Query("SELECT * FROM devices WHERE id = :id")
    suspend fun findById(id: String): DeviceEntity?

    @Query("SELECT * FROM devices ORDER BY last_seen DESC LIMIT 1")
    suspend fun mostRecent(): DeviceEntity?

    @Query("UPDATE devices SET auto_connect = :enabled WHERE id = :id")
    suspend fun updateAutoConnect(id: String, enabled: Boolean)

    @Query("UPDATE devices SET last_seen = :lastSeen WHERE id = :id")
    suspend fun touch(id: String, lastSeen: Long)

    @Query("DELETE FROM devices WHERE id = :id")
    suspend fun delete(id: String)

    @Query("DELETE FROM devices")
    suspend fun deleteAll()
}
