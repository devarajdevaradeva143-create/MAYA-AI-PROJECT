package com.devaraj.maya.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.devaraj.maya.data.local.entity.PcCommandEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface PcCommandDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(command: PcCommandEntity)

    @Query("UPDATE pc_commands SET status = :status, result = :result WHERE id = :id")
    suspend fun updateStatus(id: String, status: String, result: String?)

    @Query("SELECT * FROM pc_commands ORDER BY created_at DESC LIMIT :limit")
    fun observeRecent(limit: Int): Flow<List<PcCommandEntity>>

    @Query("DELETE FROM pc_commands")
    suspend fun deleteAll()
}
