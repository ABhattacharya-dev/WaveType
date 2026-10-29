import ctypes
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == "nt", "Windows maintenance checks")
class MaintenanceTests(unittest.TestCase):
    def test_safe_data_removal_with_real_junction_and_file_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([
                "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", str(Path(__file__).parent / "packaging/test_maintenance.ps1"),
                "-TestRoot", folder], capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_launch_gate_tracks_maintenance_mutex(self):
        import maintenance
        # A concurrently open real installer owns this name; don't interfere with it.
        if maintenance.active():
            self.skipTest("WaveType setup is currently open")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.CreateMutexW(None, False, "Local\\WaveTypeMaintenance")
        self.assertTrue(handle)
        try:
            self.assertTrue(maintenance.active())
        finally:
            kernel.CloseHandle(handle)
        self.assertFalse(maintenance.active())
