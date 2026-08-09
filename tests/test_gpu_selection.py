from unittest.mock import patch

from core import capability_detector


def test_nvidia_gpu_is_detected():
    with (
        patch.object(capability_detector.shutil, "which", side_effect=lambda name: name == "nvidia-smi"),
        patch.object(
            capability_detector.subprocess,
            "check_output",
            side_effect=["NVIDIA GeForce RTX 4090, 24564\n", "555.85\n"],
        ),
    ):
        result = capability_detector._detect_gpu()

    assert result == {
        "has_gpu": True,
        "name": "NVIDIA GeForce RTX 4090",
        "memory_mb": 24564,
        "has_cuda": True,
        "cuda_version": "555.85",
    }


def test_amd_gpu_is_detected():
    with (
        patch.object(capability_detector.shutil, "which", side_effect=lambda name: name == "rocm-smi"),
        patch.object(capability_detector.subprocess, "check_output", return_value="GPU[0]: AMD Radeon RX 7900 XTX\n"),
    ):
        result = capability_detector._detect_gpu()

    assert result["has_gpu"] is True
    assert result["name"] == "AMD GPU"
    assert result["has_cuda"] is False
