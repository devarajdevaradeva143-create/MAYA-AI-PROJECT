package com.devaraj.maya.data.local

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.devaraj.maya.data.local.entity.ConversationEntity
import com.devaraj.maya.data.local.entity.DeviceEntity
import com.devaraj.maya.data.local.entity.MessageEntity
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/** In-memory Room tests for the core chat/device tables (plan §25). */
@RunWith(AndroidJUnit4::class)
class MayaDatabaseTest {

    private lateinit var db: MayaDatabase

    @Before
    fun setUp() {
        db = Room.inMemoryDatabaseBuilder(
            ApplicationProvider.getApplicationContext(),
            MayaDatabase::class.java,
        ).allowMainThreadQueries().build()
    }

    @After
    fun tearDown() {
        db.close()
    }

    private fun message(
        id: String,
        conversationId: String = "c1",
        role: String = "USER",
        content: String = id,
        status: String = "SENT",
        createdAt: Long,
    ) = MessageEntity(
        id = id,
        conversationId = conversationId,
        role = role,
        content = content,
        status = status,
        source = "LAPTOP",
        model = null,
        error = null,
        createdAt = createdAt,
    )

    private fun conversation(id: String = "c1", updatedAt: Long = 1_000) =
        ConversationEntity(
            id = id,
            title = "Chat",
            persona = "maya",
            createdAt = 1_000,
            updatedAt = updatedAt,
        )

    @Test
    fun messagesAreOrderedByCreatedAt() = runBlocking {
        db.conversationDao().insert(conversation())
        db.messageDao().insert(message("m2", createdAt = 2_000))
        db.messageDao().insert(message("m1", createdAt = 1_000))
        db.messageDao().insert(message("m3", createdAt = 3_000))

        val messages = db.messageDao().observeByConversation("c1").first()

        assertEquals(listOf("m1", "m2", "m3"), messages.map { it.id })
    }

    @Test
    fun deletingConversationCascadesMessages() = runBlocking {
        db.conversationDao().insert(conversation())
        db.messageDao().insert(message("m1", createdAt = 1_000))
        db.messageDao().insert(message("m2", createdAt = 2_000))

        db.conversationDao().delete("c1")

        assertTrue(db.messageDao().observeByConversation("c1").first().isEmpty())
        assertNull(db.conversationDao().findById("c1"))
    }

    @Test
    fun updateStatusChangesOnlyMatchingMessages() = runBlocking {
        db.conversationDao().insert(conversation())
        db.messageDao().insert(message("m1", status = "SENDING", createdAt = 1_000))
        db.messageDao().insert(message("m2", status = "SENT", createdAt = 2_000))

        db.messageDao().updateStatus("c1", from = "SENDING", to = "FAILED")

        val messages = db.messageDao().observeByConversation("c1").first()
        assertEquals("FAILED", messages.first { it.id == "m1" }.status)
        assertEquals("SENT", messages.first { it.id == "m2" }.status)
    }

    @Test
    fun deleteByConversationKeepsOtherChats() = runBlocking {
        db.conversationDao().insert(conversation("c1"))
        db.conversationDao().insert(conversation("c2", updatedAt = 2_000))
        db.messageDao().insert(message("m1", conversationId = "c1", createdAt = 1_000))
        db.messageDao().insert(message("m2", conversationId = "c2", createdAt = 2_000))

        db.messageDao().deleteByConversation("c1")

        assertTrue(db.messageDao().observeByConversation("c1").first().isEmpty())
        assertEquals(1, db.messageDao().observeByConversation("c2").first().size)
    }

    @Test
    fun conversationTitleAndTouchArePersisted() = runBlocking {
        db.conversationDao().insert(conversation())
        db.conversationDao().updateTitle("c1", "New title", updatedAt = 5_000)
        db.conversationDao().touch("c1", updatedAt = 9_000)

        val stored = db.conversationDao().findById("c1")
        assertEquals("New title", stored?.title)
        assertEquals(9_000L, stored?.updatedAt)
    }

    @Test
    fun devicesAreOrderedByLastSeenAndAutoConnectPersists() = runBlocking {
        val dao = db.deviceDao()
        dao.upsert(DeviceEntity("d1", "Old", "10.0.0.1", 8420, lastSeen = 100))
        dao.upsert(DeviceEntity("d2", "New", "10.0.0.2", 8420, lastSeen = 200))

        assertEquals("d2", dao.mostRecent()?.id)

        dao.updateAutoConnect("d2", true)
        assertTrue(dao.findById("d2")?.autoConnect == true)
        assertFalse(dao.findById("d1")?.autoConnect == true)

        dao.touch("d1", lastSeen = 300)
        assertEquals("d1", dao.mostRecent()?.id)
        assertEquals(listOf("d1", "d2"), dao.observeAll().first().map { it.id })
    }
}
