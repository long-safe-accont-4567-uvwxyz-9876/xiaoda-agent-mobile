package com.xiaoda.agent.bridge

import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.net.URI
import java.nio.charset.CodingErrorAction

data class SelectedFileInspection(val mimeType: String, val sizeBytes: Long, val bytes: ByteArray)

class BridgeRequestValidator(private val trustedOrigin: String, private val maxFileBytes: Long) {
    fun isMethodAllowed(origin: String, method: String): Boolean = originOf(origin) == trustedOrigin && method in BridgeContract.allowedMethods
    fun isFileRequestValid(accept: String, maxBytes: Long): Boolean = maxBytes in 1..maxFileBytes && accept in ALLOWED_MIME_TYPES
    fun isSelectedFileValid(scheme: String?, actualType: String?, requestedType: String, actualBytes: Long, requestedMaxBytes: Long): Boolean {
        if (scheme != "content" || actualBytes < 0 || actualBytes > requestedMaxBytes || !isFileRequestValid(requestedType, requestedMaxBytes)) return false
        return actualType != null && (requestedType == actualType || requestedType.endsWith("/*") && actualType.startsWith(requestedType.removeSuffix("*")))
    }
    fun inspectSelectedFile(scheme: String?, reportedType: String?, requestedType: String, bytes: ByteArray, requestedMaxBytes: Long): SelectedFileInspection? {
        if (scheme != "content" || bytes.size.toLong() > requestedMaxBytes || !isFileRequestValid(requestedType, requestedMaxBytes)) return null
        val detectedType = detectMimeType(bytes) ?: return null
        if (!mimeMatches(requestedType, detectedType)) return null
        return SelectedFileInspection(detectedType, bytes.size.toLong(), bytes)
    }
    fun isShareTextValid(text: String): Boolean = text.isNotBlank() && text.length <= 20_000
    fun isAuthenticationTokenValid(token: String): Boolean =
        token.length in 1..MAX_AUTH_TOKEN_LENGTH && token.none(Char::isISOControl)
    fun isTerminalActionValid(action: String): Boolean = action in setOf("open", "status", "stop")

    private fun originOf(value: String): String? = runCatching {
        val uri = URI(value)
        "${uri.scheme}://${uri.host}${if (uri.port == -1) "" else ":${uri.port}"}"
    }.getOrNull()

    private fun mimeMatches(expected: String, actual: String): Boolean = expected == "*/*" || expected == actual || expected.endsWith("/*") && actual.startsWith(expected.removeSuffix("*"))

    private fun detectMimeType(bytes: ByteArray): String? = when {
        bytes.startsWith("%PDF-".toByteArray()) -> "application/pdf"
        bytes.startsWith(byteArrayOf(0x89.toByte(), 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a)) -> "image/png"
        bytes.startsWith(byteArrayOf(0xff.toByte(), 0xd8.toByte(), 0xff.toByte())) -> "image/jpeg"
        bytes.startsWith("GIF87a".toByteArray()) || bytes.startsWith("GIF89a".toByteArray()) -> "image/gif"
        bytes.size >= 12 && bytes.copyOfRange(0, 4).contentEquals("RIFF".toByteArray()) && bytes.copyOfRange(8, 12).contentEquals("WEBP".toByteArray()) -> "image/webp"
        bytes.size >= 12 && bytes.copyOfRange(0, 4).contentEquals("RIFF".toByteArray()) && bytes.copyOfRange(8, 12).contentEquals("WAVE".toByteArray()) -> "audio/wav"
        bytes.startsWith("ID3".toByteArray()) || bytes.size >= 2 && bytes[0] == 0xff.toByte() && bytes[1].toInt() and 0xe0 == 0xe0 -> "audio/mpeg"
        bytes.size >= 12 && bytes.copyOfRange(4, 8).contentEquals("ftyp".toByteArray()) -> "video/mp4"
        bytes.startsWith(byteArrayOf(0x1a, 0x45, 0xdf.toByte(), 0xa3.toByte())) -> "video/webm"
        isPlainText(bytes) -> "text/plain"
        else -> null
    }

    private fun isPlainText(bytes: ByteArray): Boolean {
        if (bytes.isEmpty() || bytes.any { it == 0.toByte() }) return false
        return runCatching {
            Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT).decode(java.nio.ByteBuffer.wrap(bytes))
        }.isSuccess
    }

    private fun ByteArray.startsWith(prefix: ByteArray): Boolean = size >= prefix.size && prefix.indices.all { this[it] == prefix[it] }

    private companion object {
        const val MAX_AUTH_TOKEN_LENGTH = 16_384
        val ALLOWED_MIME_TYPES = setOf("*/*", "image/*", "audio/*", "video/*", "text/plain", "application/pdf")
    }
}

class SelectedFileReader(private val validator: BridgeRequestValidator) {
    fun read(
        scheme: String?,
        reportedType: String?,
        input: InputStream,
        requestedType: String,
        requestedMaxBytes: Long,
        reportedSizeBytes: Long? = null,
    ): SelectedFileInspection? = input.use { stream ->
        if (reportedSizeBytes != null && reportedSizeBytes !in 0..requestedMaxBytes) return null
        val output = ByteArrayOutputStream()
        val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
        var total = 0L
        while (true) {
            val read = stream.read(buffer)
            if (read < 0) break
            total += read
            if (total > requestedMaxBytes) return null
            output.write(buffer, 0, read)
        }
        if (reportedSizeBytes != null && reportedSizeBytes != total) return null
        validator.inspectSelectedFile(scheme, reportedType, requestedType, output.toByteArray(), requestedMaxBytes)
    }
}
