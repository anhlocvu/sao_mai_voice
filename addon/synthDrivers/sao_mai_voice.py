import os
import subprocess
import json
import threading
import sys
import time
import synthDriverHandler
from logHandler import log

class SynthDriver(synthDriverHandler.SynthDriver):
    name = "sao_mai_voice"
    description = "Sao Mai Voice"

    supportedSettings = [
        synthDriverHandler.SynthDriver.VoiceSetting(),
        synthDriverHandler.SynthDriver.RateSetting(),
        synthDriverHandler.SynthDriver.VolumeSetting(),
    ]

    def __init__(self):
        super(SynthDriver, self).__init__()
        self._process = None
        self._voices = []
        self._current_voice = None
        self._rate = 50  # NVDA default rate
        self._volume = 100
        self._is_speaking = False
        
        # Start the 32-bit bridge process
        current_dir = os.path.dirname(__file__)
        addon_dir = os.path.dirname(current_dir)
        plugin_dir = os.path.join(addon_dir, "globalPlugins", "sao_mai_voice")
        
        python_exe = os.path.join(plugin_dir, "lib", "python32", "python.exe")
        bridge_py = os.path.join(plugin_dir, "bridge.py")
        
        if not os.path.exists(python_exe) or not os.path.exists(bridge_py):
            log.error(f"Sao Mai Voice: python.exe or bridge.py not found in {plugin_dir}")
            raise RuntimeError("Sao Mai Voice files missing.")
            
        try:
            # We use CREATE_NO_WINDOW to hide the command prompt window
            creation_flags = 0
            if sys.platform == "win32":
                # subprocess.CREATE_NO_WINDOW = 0x08000000
                creation_flags = 0x08000000
                
            self._err_log_file = open(os.path.join(plugin_dir, "sao_mai_bridge_err.log"), "w", encoding="utf-8")
            self._process = subprocess.Popen(
                [python_exe, bridge_py],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._err_log_file,
                cwd=plugin_dir,
                creationflags=creation_flags,
                text=True
            )
        except Exception as e:
            log.error(f"Sao Mai Voice: Failed to start bridge process: {e}")
            raise e

        # Read initialization response
        init_line = self._process.stdout.readline()
        if not init_line:
            raise RuntimeError("Bridge process exited immediately.")
            
        try:
            init_data = json.loads(init_line.strip())
            if init_data.get("status") == "ready":
                self._voices = init_data.get("voices", [])
                log.info(f"Sao Mai Voice initialized with voices: {self._voices}")
            else:
                raise RuntimeError(init_data.get("message", "Unknown initialization error"))
        except Exception as e:
            log.error(f"Sao Mai Voice: Init parser failed: {e}")
            self.terminate()
            raise e

        # Start stdout reading thread
        self._reader_thread = threading.Thread(target=self._read_stdout)
        self._reader_thread.daemon = True
        self._reader_thread.start()

    def terminate(self):
        if self._process:
            self._send_cmd({"action": "exit"})
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        if hasattr(self, "_err_log_file") and self._err_log_file:
            try:
                self._err_log_file.close()
            except Exception:
                pass
            self._err_log_file = None

    def _send_cmd(self, cmd):
        if self._process and self._process.stdin:
            try:
                self._process.stdin.write(json.dumps(cmd) + "\n")
                self._process.stdin.flush()
            except OSError as e:
                log.error(f"Sao Mai Voice: Error writing to bridge: {e}")

    def _read_stdout(self):
        while self._process and self._process.poll() is None:
            try:
                line = self._process.stdout.readline()
                if not line:
                    break
                data = json.loads(line.strip())
                self._handle_bridge_event(data)
            except Exception as e:
                log.error(f"Sao Mai Voice: Reader thread error: {e}")
                break

    def _handle_bridge_event(self, data):
        event = data.get("event")
        if event == "start":
            self._is_speaking = True
        elif event == "end":
            self._is_speaking = False
        elif event == "word":
            # Optional: handle word position if needed by NVDA
            pass

    @classmethod
    def check(cls):
        # We check if python.exe and DLL exist in the workspace structure
        current_dir = os.path.dirname(__file__)
        addon_dir = os.path.dirname(current_dir)
        plugin_dir = os.path.join(addon_dir, "globalPlugins", "sao_mai_voice")
        python_exe = os.path.join(plugin_dir, "lib", "python32", "python.exe")
        dll_path = os.path.join(plugin_dir, "lib", "VnTtsEng.dll")
        return os.path.exists(python_exe) and os.path.exists(dll_path)

    def speak(self, speechSequence):
        text = ""
        for item in speechSequence:
            if isinstance(item, str):
                text += item
            # We can handle other types of speech events here if needed
            
        if text:
            # Map rate 0-100 to SAPI5 rate -10 to 10
            sapi_rate = int((self._rate / 5) - 10)
            self._send_cmd({
                "action": "speak",
                "text": text,
                "voice": self._current_voice,
                "rate": sapi_rate,
                "volume": self._volume
            })

    def cancel(self):
        self._send_cmd({"action": "cancel"})
        self._is_speaking = False

    # Getters/Setters for Settings
    def _get_availableVoices(self):
        # Create a dict of VoiceInfo objects for NVDA
        voices_dict = {}
        for voice_id in self._voices:
            # Determine language based on voice name
            lang = "vi"
            if "daniel" in voice_id.lower():
                lang = "en"
            
            voices_dict[voice_id] = synthDriverHandler.VoiceInfo(
                voice_id, 
                voice_id.replace("SM_", "Sao Mai "), 
                lang
            )
        return voices_dict

    def _get_voice(self):
        if self._current_voice is None and self._voices:
            # Default voice: prefer MinhDu, then MaiDung
            for v in self._voices:
                if "minhdu" in v.lower():
                    self._current_voice = v
                    break
            if self._current_voice is None:
                for v in self._voices:
                    if "maidung" in v.lower():
                        self._current_voice = v
                        break
            if self._current_voice is None:
                self._current_voice = self._voices[0]
        return self._current_voice

    def _set_voice(self, val):
        if val in self._voices:
            self._current_voice = val
            # Apply changes immediately if currently speaking
            self._send_cmd({
                "action": "speak",
                "text": "", # Empty speak updates settings
                "voice": self._current_voice,
                "rate": int((self._rate / 5) - 10),
                "volume": self._volume
            })

    def _get_rate(self):
        return self._rate

    def _set_rate(self, val):
        self._rate = val
        self._send_cmd({
            "action": "speak",
            "text": "",
            "voice": self._current_voice,
            "rate": int((self._rate / 5) - 10),
            "volume": self._volume
        })

    def _get_volume(self):
        return self._volume

    def _set_volume(self, val):
        self._volume = val
        self._send_cmd({
            "action": "speak",
            "text": "",
            "voice": self._current_voice,
            "rate": int((self._rate / 5) - 10),
            "volume": self._volume
        })
        
    def _get_lastIndex(self):
        # Returns the last spoken index, or None if not supported
        return None
