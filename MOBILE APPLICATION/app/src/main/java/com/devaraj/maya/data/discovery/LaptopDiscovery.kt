package com.devaraj.maya.data.discovery

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

data class DiscoveredLaptop(
    val name: String,
    val host: String,
    val port: Int,
)

/**
 * NSD discovery for `_maya._tcp.` (plan §13.4). Resolves services one at a
 * time because Android's NsdManager allows a single active resolve listener.
 */
class LaptopDiscovery(context: Context) {

    private val nsdManager = context.getSystemService(NsdManager::class.java)

    fun discover(): Flow<DiscoveredLaptop> = callbackFlow {
        val queue = Channel<NsdServiceInfo>(Channel.UNLIMITED)

        val listener = object : NsdManager.DiscoveryListener {
            override fun onDiscoveryStarted(serviceType: String) = Unit

            override fun onServiceFound(service: NsdServiceInfo) {
                if (service.serviceType == SERVICE_TYPE) queue.trySend(service)
            }

            override fun onServiceLost(service: NsdServiceInfo) = Unit

            override fun onDiscoveryStopped(serviceType: String) = Unit

            override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
                close()
            }

            override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) = Unit
        }

        val resolver = launch {
            for (service in queue) {
                val resolved = resolve(service) ?: continue
                trySend(resolved)
            }
        }

        try {
            nsdManager.discoverServices(SERVICE_TYPE, NsdManager.PROTOCOL_DNS_SD, listener)
        } catch (_: IllegalArgumentException) {
            close()
        }

        awaitClose {
            queue.close()
            resolver.cancel()
            try {
                nsdManager.stopServiceDiscovery(listener)
            } catch (_: IllegalArgumentException) {
                // Already stopped.
            }
        }
    }.distinctUntilChanged()

    private suspend fun resolve(service: NsdServiceInfo): DiscoveredLaptop? =
        suspendCancellableCoroutine { continuation ->
            @Suppress("DEPRECATION")
            nsdManager.resolveService(
                service,
                object : NsdManager.ResolveListener {
                    override fun onServiceResolved(info: NsdServiceInfo) {
                        val host = info.hostAddresses.firstOrNull()?.hostAddress
                        if (host == null) {
                            continuation.resume(null)
                        } else {
                            continuation.resume(
                                DiscoveredLaptop(
                                    name = info.serviceName,
                                    host = host,
                                    port = info.port,
                                ),
                            )
                        }
                    }

                    override fun onResolveFailed(info: NsdServiceInfo, errorCode: Int) {
                        continuation.resume(null)
                    }
                },
            )
        }

    companion object {
        const val SERVICE_TYPE = "_maya._tcp."
    }
}
