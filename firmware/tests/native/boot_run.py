"""Run the actual native boot guard with simulated NVS and button/timer inputs."""
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[3]
with tempfile.TemporaryDirectory(prefix='ampve-boot-') as directory:
    binary=Path(directory)/'test'
    subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-O1','-g','-fsanitize=address,undefined',
        '-I'+str(ROOT/'firmware/tests/native/boot_stubs'),'-I'+str(ROOT/'firmware/xiaozhi/overlay/main/ampve'),
        str(ROOT/'firmware/xiaozhi/overlay/main/ampve/boot_guard.cc'),
        str(ROOT/'firmware/tests/native/boot_harness.cc'),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
