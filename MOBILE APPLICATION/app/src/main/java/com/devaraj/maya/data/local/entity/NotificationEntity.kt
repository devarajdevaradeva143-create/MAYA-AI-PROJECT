package com.devaraj.maya.data.local.entity

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "notifications",
    indices = [Index(value = ["posted_at"])],
)
data class NotificationEntity(
    @PrimaryKey val id: String,
    @ColumnInfo(name = "package_name") val packageName: String,
    val title: String?,
    val body: String?,
    @ColumnInfo(name = "posted_at") val postedAt: Long,
    val important: Boolean = false,
)
