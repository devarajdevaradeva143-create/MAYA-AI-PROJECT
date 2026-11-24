package com.devaraj.maya.ui.onboarding

import android.content.Context
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.devaraj.maya.R
import com.devaraj.maya.ui.theme.MayaTheme
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class OnboardingScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context = ApplicationProvider.getApplicationContext()
    private val next = context.getString(R.string.onboarding_next)
    private val start = context.getString(R.string.onboarding_start)
    private val skip = context.getString(R.string.onboarding_skip)

    @Test
    fun nextNextThenGetStartedFinishes() {
        var finished = false
        compose.setContent {
            MayaTheme(darkTheme = false) {
                OnboardingScreen(onFinish = { finished = true })
            }
        }

        compose.onNodeWithText(next).performClick()
        compose.onNodeWithText(next).performClick()
        compose.onNodeWithText(start).performClick()

        compose.runOnIdle { assertTrue(finished) }
    }

    @Test
    fun skipFinishesImmediately() {
        var finished = false
        compose.setContent {
            MayaTheme(darkTheme = false) {
                OnboardingScreen(onFinish = { finished = true })
            }
        }

        compose.onNodeWithText(skip).performClick()

        compose.runOnIdle { assertTrue(finished) }
    }
}
