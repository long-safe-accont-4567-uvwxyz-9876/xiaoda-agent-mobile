package com.xiaoda.agent.local

import org.json.JSONArray
import org.json.JSONObject

interface LocalCapability {
    val id: String
    val label: String
    val state: String
    fun descriptor(): JSONObject = JSONObject().put("id", id).put("label", label).put("state", state)
}

class LocalCapabilityRegistry {
    private val capabilities = listOf(
        capability("multi_agent", "? Agent ??", "foundation"),
        capability("memory", "???????", "foundation"),
        capability("scheduler", "????", "planned"),
        capability("browser", "??????", "planned"),
        capability("python_tools", "Python ?????", "planned"),
        capability("plugins", "????", "planned"),
        capability("document_processing", "??????", "foundation"),
    )

    fun descriptors(): JSONArray = JSONArray(capabilities.map(LocalCapability::descriptor))

    private fun capability(capabilityId: String, capabilityLabel: String, capabilityState: String) = object : LocalCapability {
        override val id = capabilityId
        override val label = capabilityLabel
        override val state = capabilityState
    }
}
