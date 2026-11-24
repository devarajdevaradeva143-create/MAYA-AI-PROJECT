package com.devaraj.maya.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable

private val MayaDarkColors = darkColorScheme(
    primary = MayaPrimary,
    onPrimary = MayaBackground,
    secondary = MayaSecondary,
    onSecondary = MayaBackground,
    tertiary = MayaAccent,
    onTertiary = MayaBackground,
    background = MayaBackground,
    onBackground = MayaOnBackground,
    surface = MayaSurface,
    onSurface = MayaOnBackground,
    surfaceVariant = MayaSurfaceHigh,
    onSurfaceVariant = MayaOnSurfaceVariant,
    error = MayaError,
    onError = MayaBackground,
    outline = MayaOutline,
)

private val MayaLightColors = lightColorScheme(
    primary = MayaPrimaryLight,
    onPrimary = MayaSurfaceLight,
    secondary = MayaSecondaryLight,
    onSecondary = MayaSurfaceLight,
    tertiary = MayaAccentLight,
    onTertiary = MayaSurfaceLight,
    background = MayaBackgroundLight,
    onBackground = MayaOnBackgroundLight,
    surface = MayaSurfaceLight,
    onSurface = MayaOnBackgroundLight,
    surfaceVariant = MayaSurfaceHighLight,
    onSurfaceVariant = MayaOnSurfaceVariantLight,
    error = MayaErrorLight,
    onError = MayaSurfaceLight,
    outline = MayaOutlineLight,
)

/**
 * Brand theme. Dynamic color is intentionally off (plan §9.2).
 */
@Composable
fun MayaTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) MayaDarkColors else MayaLightColors,
        typography = MayaTypography,
        shapes = MayaShapes,
        content = content,
    )
}
