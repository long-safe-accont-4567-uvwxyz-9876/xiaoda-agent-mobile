import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VISION_SERVICE = ROOT / "utils" / "vision_service.py"


def test_local_image_inference_service_remains_available():
    assert VISION_SERVICE.exists()

    tree = ast.parse(VISION_SERVICE.read_text(encoding="utf-8"))
    service = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "VisionService")
    methods = {node.name for node in service.body if isinstance(node, ast.FunctionDef)}

    assert "detect_objects" in methods
    assert "load_image" in methods
    assert "capture_frame" not in methods
    assert "save_frame" not in methods


def test_local_image_inference_keeps_pc_gpu_without_npu():
    source = VISION_SERVICE.read_text(encoding="utf-8")

    assert "use_vulkan_compute = True" in source
    assert "set_vulkan_device(gpu_index)" in source
    assert "XIAODA_GPU_INDEX" in source
    assert "VideoCapture" not in source
    assert "ENABLE_NPU" not in source
    assert "NPUInference" not in source
