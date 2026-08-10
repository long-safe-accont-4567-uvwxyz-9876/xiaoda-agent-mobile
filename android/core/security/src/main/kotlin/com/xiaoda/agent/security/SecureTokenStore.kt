package com.xiaoda.agent.security

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

interface SecureTokenStore {
    fun write(token: String)
    fun read(): String?
    fun clear()
}

class InMemorySecureTokenStore : SecureTokenStore {
    private var token: String? = null
    override fun write(token: String) { this.token = token }
    override fun read(): String? = token
    override fun clear() { token = null }
}

class KeystoreTokenStore(context: Context) : SecureTokenStore {
    private val preferences = context.getSharedPreferences("secure_session", Context.MODE_PRIVATE)

    override fun write(token: String) {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key())
        preferences.edit()
            .putString("ciphertext", android.util.Base64.encodeToString(cipher.doFinal(token.toByteArray()), android.util.Base64.NO_WRAP))
            .putString("iv", android.util.Base64.encodeToString(cipher.iv, android.util.Base64.NO_WRAP))
            .apply()
    }

    override fun read(): String? {
        val ciphertext = preferences.getString("ciphertext", null) ?: return null
        val iv = preferences.getString("iv", null) ?: return null
        return runCatching {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, android.util.Base64.decode(iv, android.util.Base64.NO_WRAP)))
            String(cipher.doFinal(android.util.Base64.decode(ciphertext, android.util.Base64.NO_WRAP)))
        }.getOrNull()
    }

    override fun clear() { preferences.edit().clear().apply() }

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").run {
            init(KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build())
            generateKey()
        }
    }

    private companion object {
        const val ALIAS = "xiaoda.session.token"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
    }
}
