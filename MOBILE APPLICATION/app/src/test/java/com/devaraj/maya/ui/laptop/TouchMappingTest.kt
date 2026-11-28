package com.devaraj.maya.ui.laptop

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.unit.IntSize
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class TouchMappingTest {

    private val box = IntSize(1000, 500)

    @Test
    fun centerMapsToCenter() {
        val p = mapTouchToImage(Offset(500f, 250f), box, IntSize(1600, 900))!!
        assertEquals(0.5f, p.x, 0.001f)
        assertEquals(0.5f, p.y, 0.001f)
    }

    @Test
    fun letterboxTouchIsIgnored() {
        // 16:9 image inside a 2:1 box: drawn 888.9 x 500, bars ~55.5 wide.
        assertNull(mapTouchToImage(Offset(10f, 250f), box, IntSize(1600, 900)))
        assertNull(mapTouchToImage(Offset(990f, 250f), box, IntSize(1600, 900)))
    }

    @Test
    fun topLeftOfImageMapsToZero() {
        val p = mapTouchToImage(Offset(56f, 0f), box, IntSize(1600, 900))!!
        assertEquals(0f, p.x, 0.01f)
        assertEquals(0f, p.y, 0.01f)
    }

    @Test
    fun portraitImageIsPillarboxed() {
        // 9:16 image inside a 2:1 box: drawn 281.25 x 500 centered.
        val p = mapTouchToImage(Offset(500f, 250f), box, IntSize(900, 1600))!!
        assertEquals(0.5f, p.x, 0.001f)
        assertEquals(0.5f, p.y, 0.001f)
        assertNull(mapTouchToImage(Offset(100f, 250f), box, IntSize(900, 1600)))
    }

    @Test
    fun zeroSizesReturnNull() {
        assertNull(mapTouchToImage(Offset(10f, 10f), IntSize.Zero, IntSize(100, 100)))
        assertNull(mapTouchToImage(Offset(10f, 10f), IntSize(100, 100), IntSize.Zero))
    }
}
