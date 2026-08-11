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
        capability("multi_agent", "Multi-agent orchestration", "foundation"),
        capability("memory", "Long-term memory and retrieval", "foundation"),
        capability("scheduler", "Scheduled tasks", "planned"),
        capability("browser", "Browser automation", "planned"),
        capability("python_tools", "Local tool adapters", "planned"),
        capability("plugins", "Local plugins", "planned"),
        capability("document_processing", "Complex document processing", "foundation"),
    )

    fun descriptors(): JSONArray = JSONArray(capabilities.map(LocalCapability::descriptor))

    private fun capability(capabilityId: String, capabilityLabel: String, capabilityState: String) = object : LocalCapability {
        override val id = capabilityId
        override val label = capabilityLabel
        override val state = capabilityState
    }
}
