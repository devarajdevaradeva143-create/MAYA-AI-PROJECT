package com.devaraj.maya.data.local.entity

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "audit_log")
data class AuditEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val action: String,
    val detail: String,
    val allowed: Boolean,
    @ColumnInfo(name = "created_at") val createdAt: Long,
)
