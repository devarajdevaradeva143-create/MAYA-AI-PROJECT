package com.devaraj.maya.ui.connection

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import com.devaraj.maya.R
import com.devaraj.maya.data.remote.MayaErrorReason

/** English user-safe text for every network/pairing reason (plan §13.5). */
@Composable
fun reasonText(reason: MayaErrorReason?): String = stringResource(
    when (reason) {
        MayaErrorReason.WRONG_PIN -> R.string.error_wrong_pin
        MayaErrorReason.EXPIRED -> R.string.error_expired
        MayaErrorReason.RATE_LIMITED -> R.string.error_rate_limited
        MayaErrorReason.INVALID_TOKEN,
        MayaErrorReason.TOKEN_EXPIRED,
        MayaErrorReason.DEVICE_REVOKED,
        -> R.string.error_pair_again
        MayaErrorReason.ENGINE_UNAVAILABLE -> R.string.error_engine_down
        MayaErrorReason.ENGINE_TIMEOUT,
        MayaErrorReason.TIMEOUT,
        -> R.string.error_timeout
        MayaErrorReason.NO_CONNECTION -> R.string.error_no_connection
        MayaErrorReason.NON_LOCAL_HOST -> R.string.error_local_only
        MayaErrorReason.BAD_REQUEST,
        MayaErrorReason.UNSUPPORTED_ACTION,
        MayaErrorReason.PAYLOAD_TOO_LARGE,
        MayaErrorReason.NOT_FOUND,
        -> R.string.error_bad_request
        MayaErrorReason.PERMISSION_DENIED,
        MayaErrorReason.ACTION_BLOCKED,
        -> R.string.error_bad_request
        MayaErrorReason.SERVER_ERROR -> R.string.error_server
        MayaErrorReason.STT_UNAVAILABLE,
        MayaErrorReason.TTS_UNAVAILABLE,
        MayaErrorReason.UNKNOWN,
        null,
        -> R.string.error_unknown
    },
)
