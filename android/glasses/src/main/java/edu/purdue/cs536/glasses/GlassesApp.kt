package edu.purdue.cs536.glasses

import android.app.Application
import androidx.camera.camera2.Camera2Config
import androidx.camera.core.CameraSelector
import androidx.camera.core.CameraXConfig

/**
 * INMO Air 2 declares FEATURE_CAMERA_FRONT, but every camera reports LENS_FACING_BACK.
 * CameraX's startup validator then fails with "Expected camera missing from device".
 * Limiting CameraX to back cameras makes it skip the front-camera check.
 */
class GlassesApp : Application(), CameraXConfig.Provider {
    override fun getCameraXConfig(): CameraXConfig =
        CameraXConfig.Builder.fromConfig(Camera2Config.defaultConfig())
            .setAvailableCamerasLimiter(CameraSelector.DEFAULT_BACK_CAMERA)
            .build()
}
