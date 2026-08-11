package com.xiaoda.agent.bridge

import java.io.ByteArrayInputStream
import java.io.InputStream
import org.junit.Assert.assertFalse
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class BridgeRequestValidatorTest {
    private val validator = BridgeRequestValidator("https://appassets.androidplatform.net", 10L * 1024 * 1024)

    @Test
    fun `bridge rejects untrusted origins and methods outside fixed contract`() {
        assertTrue(validator.isMethodAllowed("https://appassets.androidplatform.net", "shareText"))
        assertFalse(validator.isMethodAllowed("https://evil.example", "shareText"))
        assertFalse(validator.isMethodAllowed("https://appassets.androidplatform.net", "runCommand"))
    }

    @Test
    fun `bridge validates file share and terminal parameters`() {
        assertTrue(validator.isFileRequestValid("image/*", 1024))
        assertTrue(validator.isFileRequestValid("*/*", 1024))
        assertFalse(validator.isFileRequestValid("image/*", 20L * 1024 * 1024))
        assertTrue(validator.isShareTextValid("hello"))
        assertFalse(validator.isShareTextValid("x".repeat(20_001)))
        assertTrue(validator.isAuthenticationTokenValid("opaque-provider-session"))
        assertFalse(validator.isAuthenticationTokenValid(""))
        assertFalse(validator.isAuthenticationTokenValid("line\nbreak"))
        assertFalse(validator.isAuthenticationTokenValid("x".repeat(16_385)))
        assertTrue(validator.isTerminalActionValid("status"))
        assertFalse(validator.isTerminalActionValid("run:rm -rf"))
    }

    @Test
    fun `selected files require content uri matching type and bounded real size`() {
        assertTrue(validator.isSelectedFileValid("content", "application/pdf", "application/pdf", 4_096, 8_192))
        assertTrue(validator.isSelectedFileValid("content", "image/png", "image/*", 4_096, 8_192))
        assertFalse(validator.isSelectedFileValid("file", "application/pdf", "application/pdf", 4_096, 8_192))
        assertFalse(validator.isSelectedFileValid("content", "text/plain", "application/pdf", 4_096, 8_192))
        assertFalse(validator.isSelectedFileValid("content", "application/pdf", "application/pdf", -1, 8_192))
        assertFalse(validator.isSelectedFileValid("content", "application/pdf", "application/pdf", 8_193, 8_192))
    }

    @Test
    fun `selected file content determines mime instead of provider metadata`() {
        val pdf = "%PDF-1.7\n".toByteArray()
        val png = byteArrayOf(0x89.toByte(), 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a)

        assertTrue(validator.inspectSelectedFile("content", "application/octet-stream", "application/pdf", pdf, 1_024) != null)
        assertTrue(validator.inspectSelectedFile("content", "image/jpeg", "image/*", png, 1_024)?.mimeType == "image/png")
        assertTrue(validator.inspectSelectedFile("content", "application/pdf", "application/pdf", "not a pdf".toByteArray(), 1_024) == null)
    }

    @Test
    fun `selected file inspection returns exact bytes and rejects truncated reads`() {
        val bytes = "%PDF-1.7\nbody".toByteArray()

        val result = validator.inspectSelectedFile("content", "application/pdf", "application/pdf", bytes, bytes.size.toLong())

        assertTrue(result?.sizeBytes == bytes.size.toLong())
        assertFalse(validator.inspectSelectedFile("content", "application/pdf", "application/pdf", bytes, bytes.size.toLong() - 1) != null)
    }

    @Test
    fun `selected file reader validates streamed content and closes input`() {
        val bytes = "%PDF-1.7\nbody".toByteArray()
        var closed = false
        val input = object : ByteArrayInputStream(bytes) {
            override fun close() {
                closed = true
                super.close()
            }
        }

        val result = SelectedFileReader(validator).read("content", "application/pdf", input, "application/pdf", bytes.size.toLong())

        assertEquals(bytes.size.toLong(), result?.sizeBytes)
        assertTrue(closed)
    }

    @Test
    fun `selected file reader rejects oversized streams without trusting metadata`() {
        val input = object : InputStream() {
            private var remaining = 9L
            var closed = false
            override fun read(): Int = if (remaining-- > 0) 'a'.code else -1
            override fun close() { closed = true }
        }

        val result = SelectedFileReader(validator).read("content", "text/plain", input, "text/plain", 8)

        assertNull(result)
        assertTrue(input.closed)
    }

    @Test
    fun `selected file reader rejects provider size disagreement`() {
        val bytes = "%PDF-1.7\nbody".toByteArray()

        val result = SelectedFileReader(validator).read(
            "content",
            "application/pdf",
            ByteArrayInputStream(bytes),
            "application/pdf",
            bytes.size.toLong() + 1,
            bytes.size.toLong() + 1,
        )

        assertNull(result)
    }
}
