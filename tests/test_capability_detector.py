from core.capability_detector import CapabilityProfile


def test_prompt_segment_keeps_pc_system_and_gpu_only():
    profile = CapabilityProfile(
        platform_os="Windows",
        platform_arch="AMD64",
        hostname="desktop",
        processor="Intel Core",
        has_gpu=True,
        gpu_name="NVIDIA GeForce RTX",
        gpu_memory_mb=8192,
        has_cuda=True,
        cuda_version="555.0",
    )

    segment = profile.to_prompt_segment("D:/xiaoda-data")

    assert "Windows" in segment
    assert "NVIDIA GeForce RTX" in segment
    assert "D:/xiaoda-data" in segment
    for retired in ("GPIO", "I2C", "SPI", "UART", "PWM", "摄像头", "NPU", "SBC"):
        assert retired not in segment


def test_capability_profile_has_no_edge_hardware_fields():
    fields = CapabilityProfile.__dataclass_fields__

    for retired in ("has_gpio", "has_i2c", "has_camera", "is_sbc", "npu_enabled"):
        assert retired not in fields
