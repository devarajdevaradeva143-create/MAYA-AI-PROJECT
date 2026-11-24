package com.devaraj.maya.data.local.entity

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "devices")
data class DeviceEntity(
    @PrimaryKey val id: String,
    val name: String,
    val host: String,
    val port: Int,
    @ColumnInfo(name = "last_seen") val lastSeen: Long,
    @ColumnInfo(name = "auto_connect") val autoConnect: Boolean = false,
)
