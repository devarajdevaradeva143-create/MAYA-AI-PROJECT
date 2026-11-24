package com.devaraj.maya.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import com.devaraj.maya.data.local.dao.AuditDao
import com.devaraj.maya.data.local.dao.ConversationDao
import com.devaraj.maya.data.local.dao.DeviceDao
import com.devaraj.maya.data.local.dao.MessageDao
import com.devaraj.maya.data.local.dao.NotificationDao
import com.devaraj.maya.data.local.dao.PcCommandDao
import com.devaraj.maya.data.local.entity.AuditEntity
import com.devaraj.maya.data.local.entity.ConversationEntity
import com.devaraj.maya.data.local.entity.DeviceEntity
import com.devaraj.maya.data.local.entity.MessageEntity
import com.devaraj.maya.data.local.entity.NotificationEntity
import com.devaraj.maya.data.local.entity.PcCommandEntity

@Database(
    entities = [
        ConversationEntity::class,
        MessageEntity::class,
        DeviceEntity::class,
        PcCommandEntity::class,
        NotificationEntity::class,
        AuditEntity::class,
    ],
    version = 1,
    exportSchema = true,
)
abstract class MayaDatabase : RoomDatabase() {
    abstract fun conversationDao(): ConversationDao
    abstract fun messageDao(): MessageDao
    abstract fun deviceDao(): DeviceDao
    abstract fun pcCommandDao(): PcCommandDao
    abstract fun notificationDao(): NotificationDao
    abstract fun auditDao(): AuditDao

    companion object {
        const val NAME = "maya.db"
    }
}
