package com.devaraj.maya.data.local.entity

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "pc_commands")
data class PcCommandEntity(
    @PrimaryKey val id: String,
    val action: String,
    @ColumnInfo(name = "params_json") val paramsJson: String,
    val status: String,
    val result: String?,
    @ColumnInfo(name = "created_at") val createdAt: Long,
)
