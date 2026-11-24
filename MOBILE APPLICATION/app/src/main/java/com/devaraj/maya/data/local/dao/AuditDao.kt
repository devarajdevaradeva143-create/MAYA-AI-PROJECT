package com.devaraj.maya.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query
import com.devaraj.maya.data.local.entity.AuditEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface AuditDao {

    @Insert
    suspend fun insert(entry: AuditEntity)

    @Query("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT :limit")
    fun observeRecent(limit: Int): Flow<List<AuditEntity>>

    @Query("DELETE FROM audit_log")
    suspend fun deleteAll()
}
