package com.xiaoda.agent

import java.net.URI

enum class BackAction { GO_BACK, FINISH }

object BackNavigationPolicy {
    fun decide(canGoBack: Boolean): BackAction = if (canGoBack) BackAction.GO_BACK else BackAction.FINISH
}

data class ConnectionLifecycleState(val foreground: Boolean, val networkAvailable: Boolean)

class ConnectionLifecyclePolicy(initialState: ConnectionLifecycleState = ConnectionLifecycleState(false, false)) {
    private var foreground = initialState.foreground
    private var networkAvailable = initialState.networkAvailable
    val shouldConnect get() = foreground && networkAvailable
    fun onForegroundChanged(value: Boolean): Boolean? = update { foreground = value }
    fun onNetworkChanged(value: Boolean): Boolean? = update { networkAvailable = value }
    fun snapshot() = ConnectionLifecycleState(foreground, networkAvailable)
    private inline fun update(change: () -> Unit): Boolean? {
        val previous = shouldConnect
        change()
        return shouldConnect.takeIf { it != previous }
    }
}

class NetworkCallbackGeneration {
    private var next = 0L
    private var current: Long? = null
    fun register(): Long = (++next).also { current = it }
    fun unregister(generation: Long) {
        if (current == generation) current = null
    }
    fun isCurrent(generation: Long): Boolean = current == generation
}

private fun safeRoutePath(value: String?): String? = value
    ?.takeIf { it.startsWith("/") && !it.contains("..") && !it.contains('\\') }

object DeepLinkPolicy {
    fun route(value: String): String? {
        val uri = runCatching { URI(value) }.getOrNull() ?: return null
        if (uri.scheme != "xiaoda" || uri.host != "agent" || uri.rawQuery != null || uri.rawFragment != null) return null
        return safeRoutePath(uri.path?.takeIf(String::isNotEmpty) ?: "/")
    }
}

object NotificationNavigationPolicy {
    const val ACTION_OPEN_ROUTE = "com.xiaoda.agent.OPEN_ROUTE"
    const val EXTRA_ROUTE = "xiaoda.route"

    fun route(action: String?, requestedRoute: String?): String? =
        requestedRoute?.let(::safeRoutePath).takeIf { action == ACTION_OPEN_ROUTE }
}