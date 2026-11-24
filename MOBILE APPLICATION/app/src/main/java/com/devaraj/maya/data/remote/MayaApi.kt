package com.devaraj.maya.data.remote

import okhttp3.RequestBody
import okhttp3.ResponseBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Query
import retrofit2.http.Streaming

/**
 * REST surface from docs/API-CONTRACT.md. Voice/PC/wake calls arrive with
 * their phases; this interface only grows (additive).
 */
interface MayaApi {

    @GET("health")
    suspend fun health(): HealthDto

    @POST("pair/claim")
    suspend fun pairClaim(@Body body: PairClaimRequest): PairResponse

    @POST("pair/qr/claim")
    suspend fun pairQrClaim(@Body body: QrClaimRequest): PairResponse

    @POST("pair/refresh")
    suspend fun pairRefresh(@Body body: RefreshRequest): RefreshResponse

    @GET("pair/devices")
    suspend fun listDevices(): DevicesDto

    @DELETE("pair/devices/{device_id}")
    suspend fun revokeDevice(@Path("device_id") deviceId: String): RevokeDto

    @POST("chat")
    suspend fun chat(@Body body: ChatRequest): ChatResponse

    @GET("pc/status")
    suspend fun pcStatus(): PcStatusDto

    @POST("pc/command")
    suspend fun pcCommand(@Body body: PcCommandRequest): PcCommandResponse

    @POST("pc/confirm")
    suspend fun pcConfirm(@Body body: PcConfirmRequest): PcCommandResponse

    @POST("pc/cancel")
    suspend fun pcCancel(@Body body: PcCancelRequest): PcCommandResponse

    @POST("pc/remote/start")
    suspend fun remoteStart(@Body body: RemoteConfirmRequest = RemoteConfirmRequest()): RemoteStartResponse

    @POST("pc/remote/stop")
    suspend fun remoteStop(@Body body: RemoteStopRequest): RemoteSessionDto

    @GET("pc/remote/status")
    suspend fun remoteStatus(@Query("session_token") sessionToken: String): RemoteStatusDto

    @GET("pc/screen")
    @Streaming
    suspend fun screen(
        @Query("session_token") sessionToken: String,
        @Query("max_width") maxWidth: Int = 1280,
        @Query("quality") quality: Int = 60,
    ): ResponseBody

    @POST("pc/input")
    suspend fun input(@Body body: InputRequest): InputResponse

    @GET("pc/files/roots")
    suspend fun fileRoots(@Query("session_token") sessionToken: String): FileRootsDto

    @GET("pc/files/list")
    suspend fun fileList(
        @Query("session_token") sessionToken: String,
        @Query("path") path: String,
    ): FileListDto

    @GET("pc/files/download")
    @Streaming
    suspend fun fileDownload(
        @Query("session_token") sessionToken: String,
        @Query("path") path: String,
    ): ResponseBody

    @PUT("pc/files/upload")
    suspend fun fileUpload(
        @Query("session_token") sessionToken: String,
        @Query("path") path: String,
        @Body body: RequestBody,
    ): FileUploadDto

    @GET("hybrid/status")
    suspend fun hybridStatus(): HybridStatusDto

    @POST("hybrid/takeover")
    suspend fun hybridTakeover(): HybridStatusDto

    @POST("hybrid/release")
    suspend fun hybridRelease(): HybridStatusDto

    @POST("wake/status")
    suspend fun wakeStatus(): WakeStatusDto

    @POST("wake/listen")
    suspend fun wakeListen(@Body body: WakeListenRequest = WakeListenRequest()): WakeListenResponse

    @POST("wake/stop")
    suspend fun wakeStop(): WakeStopResponse

    @POST("pc/device/status")
    suspend fun deviceStatus(@Body body: DeviceStatusRequest): DeviceStatusResponse
}
