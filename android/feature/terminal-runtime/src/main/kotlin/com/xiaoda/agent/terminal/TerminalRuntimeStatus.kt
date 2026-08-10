package com.xiaoda.agent.terminal

data class TerminalRuntimeState(
    val state: String,
    val canStart: Boolean,
)

object TerminalRuntimeStatus {
    val current = TerminalRuntimeState(
        state = "disabled",
        canStart = false,
    )

    val legalReview = TerminalRuntimeGate(
        componentFrozen = false,
        bomGenerated = true,
        sbomGenerated = true,
        noticeGenerated = true,
        legalApproved = false,
        storeApproved = false,
        abiVerified = false,
        sizeVerified = false,
    )
}

data class TerminalRuntimeGate(
    val componentFrozen: Boolean,
    val bomGenerated: Boolean,
    val sbomGenerated: Boolean,
    val noticeGenerated: Boolean,
    val legalApproved: Boolean,
    val storeApproved: Boolean,
    val abiVerified: Boolean,
    val sizeVerified: Boolean,
) {
    val releaseEnabled: Boolean
        get() = componentFrozen && bomGenerated && sbomGenerated && noticeGenerated && legalApproved && storeApproved && abiVerified && sizeVerified
}
