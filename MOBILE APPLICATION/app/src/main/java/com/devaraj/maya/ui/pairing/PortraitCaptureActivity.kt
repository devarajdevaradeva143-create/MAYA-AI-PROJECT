package com.devaraj.maya.ui.pairing

import com.journeyapps.barcodescanner.CaptureActivity

/**
 * Portrait-locked capture activity for the QR scanner. The default
 * [CaptureActivity] is landscape, which made the scan screen open
 * horizontally; subclassing with a portrait manifest entry fixes that.
 */
class PortraitCaptureActivity : CaptureActivity()