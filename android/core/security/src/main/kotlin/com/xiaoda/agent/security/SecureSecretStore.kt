package com.xiaoda.agent.security

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import java.security.MessageDigest
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

interface SecureSecretStore {
    fun put(name: String, value: String)
    fun get(name: String): String?
    fun remove(name: String)
}

class InMemorySecureSecretStore : SecureSecretStore {
    private val values = mutableMapOf<String, String>()
    override fun put(name: String, value: String) { values[name] = value }
    override fun get(name: String): String? = values[name]
    override fun remove(name: String) { values.remove(name) }
}

class KeystoreSecretStore(context: Context) : SecureSecretStore {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    override fun put(name: String, value: String) {
        require(name.isNotBlank())
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val storageKey = storageKey(name)
        preferences.edit()
            .putString("$storageKey.ciphertext", Base64.encodeToString(cipher.doFinal(value.toByteArray(Charsets.UTF_8)), Base64.NO_WRAP))
            .putString("$storageKey.iv", Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
            .apply()
    }

    override fun get(name: String): String? {
        val storageKey = storageKey(name)
        val ciphertext = preferences.getString("$storageKey.ciphertext", null) ?: return null
        val iv = preferences.getString("$storageKey.iv", null) ?: return null
        return runCatching {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)))
            String(cipher.doFinal(Base64.decode(ciphertext, Base64.NO_WRAP)), Charsets.UTF_8)
        }.getOrNull()
    }

    override fun remove(name: String) {
        val storageKey = storageKey(name)
        preferences.edit().remove("$storageKey.ciphertext").remove("$storageKey.iv").apply()
    }

    private fun storageKey(name: String): String = MessageDigest.getInstance("SHA-256")
        .digest(name.toByteArray(Charsets.UTF_8))
        .joinToString("") { "%02x".format(it) }

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").run {
            init(
                KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .build(),
            )
            generateKey()
        }
    }

    private companion object {
        const val ALIAS = "xiaoda.local.secrets"
        const val PREFERENCES = "xiaoda_local_secrets"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
    }
}
