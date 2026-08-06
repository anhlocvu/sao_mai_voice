import sys
import os
import json
import time
import threading
import queue

# Add current directory and lib directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_dir, "lib")
sys.path.append(current_dir)
sys.path.append(lib_path)

import reg_helper

# We import comtypes here after path adjustment
import comtypes
import comtypes.client

class SapiEventsSink(object):
    def __init__(self, bridge):
        self.bridge = bridge

    def StartStream(self, StreamNumber, StreamPosition):
        self.bridge.is_speaking = True
        self.bridge.send_response({"event": "start", "stream": StreamNumber})

    def EndStream(self, StreamNumber, StreamPosition):
        self.bridge.is_speaking = False
        self.bridge.send_response({"event": "end", "stream": StreamNumber})

    def Bookmark(self, StreamNumber, StreamPosition, Bookmark, BookmarkId):
        self.bridge.send_response({
            "event": "bookmark",
            "mark": Bookmark,
            "stream": StreamNumber
        })

    def Word(self, StreamNumber, StreamPosition, CharacterPosition, Length):
        self.bridge.send_response({
            "event": "word", 
            "stream": StreamNumber,
            "char_pos": CharacterPosition,
            "length": Length
        })

class SaoMaiBridge(object):
    def __init__(self):
        self.voice = None
        self.running = True
        self.tokens = {}
        self.connection = None
        self.cmd_queue = queue.Queue()
        self.is_speaking = False

    def init_sapi(self):
        # Register registry entries under HKCU
        reg_helper.register_all(lib_path)
        
        # Initialize COM
        comtypes.CoInitialize()
        self.voice = comtypes.client.CreateObject("SAPI.SpVoice")
        
        # Get all Sao Mai voice tokens
        all_voices = self.voice.GetVoices()
        SAO_MAI_NAMES = ["Mai Dung", "Minh Du", "Thanh Vi", "Thu An", "Daniel"]
        for i in range(all_voices.Count):
            token = all_voices.Item(i)
            token_id = token.Id
            token_name = token_id.split("\\")[-1]
            
            is_sao_mai = False
            if "SM_" in token_name:
                is_sao_mai = True
            else:
                for name in SAO_MAI_NAMES:
                    if name.lower() in token_name.lower():
                        is_sao_mai = True
                        break
            if is_sao_mai:
                short_name = token_name.replace("SM_", "")
                if short_name not in self.tokens:
                    self.tokens[short_name] = token
                
        # Register event sink to receive speak events
        self.sink = SapiEventsSink(self)
        self.connection = comtypes.client.GetEvents(self.voice, self.sink)
        self.send_response({"status": "ready", "voices": list(self.tokens.keys())})

    def coalesce_commands(self, cmds):
        if not cmds:
            return []
            
        # Check for exit command first
        for cmd in cmds:
            if cmd.get("action") == "exit":
                return [{"action": "exit"}]
                
        latest_voice = None
        latest_rate = None
        latest_volume = None
        
        final_action = None
        final_text = None
        
        for cmd in cmds:
            action = cmd.get("action")
            if action == "speak":
                if "voice" in cmd and cmd["voice"] is not None:
                    latest_voice = cmd["voice"]
                if "rate" in cmd and cmd["rate"] is not None:
                    latest_rate = cmd["rate"]
                if "volume" in cmd and cmd["volume"] is not None:
                    latest_volume = cmd["volume"]
                
                text = cmd.get("text", "")
                if text:
                    final_action = "speak"
                    final_text = text
            elif action == "cancel":
                final_action = "cancel"
                final_text = None
                
        coalesced = []
        
        if final_action == "speak":
            speak_cmd = {
                "action": "speak",
                "text": final_text,
                "voice": latest_voice,
                "rate": latest_rate,
                "volume": latest_volume
            }
            speak_cmd = {k: v for k, v in speak_cmd.items() if v is not None}
            coalesced.append(speak_cmd)
        elif final_action == "cancel":
            settings_cmd = {
                "action": "speak",
                "text": "",
                "voice": latest_voice,
                "rate": latest_rate,
                "volume": latest_volume
            }
            settings_cmd = {k: v for k, v in settings_cmd.items() if v is not None}
            if len(settings_cmd) > 2:
                coalesced.append(settings_cmd)
            coalesced.append({"action": "cancel"})
        else:
            settings_cmd = {
                "action": "speak",
                "text": "",
                "voice": latest_voice,
                "rate": latest_rate,
                "volume": latest_volume
            }
            settings_cmd = {k: v for k, v in settings_cmd.items() if v is not None}
            if len(settings_cmd) > 2:
                coalesced.append(settings_cmd)
                
        return coalesced

    def run(self):
        try:
            self.init_sapi()
            
            # Start background thread to read input
            input_thread = threading.Thread(target=self.read_input)
            input_thread.daemon = True
            input_thread.start()

            # Main loop on Main Thread to process COM events and queue commands
            while self.running:
                # Pump COM events briefly (1ms timeout) to allow SAPI events to be fired
                comtypes.client.PumpEvents(0.001)
                
                # Process commands from queue on Main Thread
                cmds = []
                try:
                    # Wait up to 1ms for the first command. 
                    # This blocks and keeps CPU usage at 0% when idle.
                    cmd = self.cmd_queue.get(timeout=0.001)
                    cmds.append(cmd)
                    self.cmd_queue.task_done()
                    
                    # Pull any additional commands that are already in the queue immediately
                    while not self.cmd_queue.empty():
                        cmd = self.cmd_queue.get_nowait()
                        cmds.append(cmd)
                        self.cmd_queue.task_done()
                except queue.Empty:
                    pass
                
                if cmds:
                    coalesced = self.coalesce_commands(cmds)
                    for cmd in coalesced:
                        self.handle_command(cmd)
        except Exception as e:
            # Write error to stderr so it goes to log file
            sys.stderr.write(f"Bridge run error: {e}\n")
            sys.stderr.flush()
            self.send_response({"status": "error", "message": f"Bridge error: {e}"})
        finally:
            # Cleanup registry and COM
            if self.connection:
                self.connection = None
            self.voice = None
            reg_helper.unregister_all()
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass

    def read_input(self):
        while self.running:
            try:
                line = sys.stdin.readline()
                if not line:
                    self.cmd_queue.put({"action": "exit"})
                    break
                cmd = json.loads(line.strip())
                self.cmd_queue.put(cmd)
            except Exception as e:
                sys.stderr.write(f"Error reading input: {e}\n")
                sys.stderr.flush()
                self.send_response({"error": str(e)})

    def handle_command(self, cmd):
        action = cmd.get("action")
        if action == "speak":
            text = cmd.get("text", "")
            voice_name = cmd.get("voice")
            rate = cmd.get("rate")
            volume = cmd.get("volume")
            
            # Apply settings if provided
            if voice_name and voice_name in self.tokens:
                self.voice.Voice = self.tokens[voice_name]
            if rate is not None:
                # SAPI5 rate is -10 to 10
                self.voice.Rate = int(rate)
            if volume is not None:
                self.voice.Volume = int(volume)
                
            # Speak asynchronously
            if not text:
                self.voice.Speak("", 2)
            else:
                # SPF_ASYNC = 1, SPF_PURGEBEFORESPEAK = 2, SPF_IS_XML = 8
                flags = 1 | 2 | 8
                self.voice.Speak(text, flags)
            
        elif action == "cancel":
            # Cancel current speech only if the voice is actually speaking,
            # using PURGE to clear the speech queue.
            if self.is_speaking:
                self.voice.Speak("", 2)
            
        elif action == "exit":
            self.running = False

    def send_response(self, data):
        try:
            sys.stdout.write(json.dumps(data) + "\n")
            sys.stdout.flush()
        except OSError:
            # Stdin/stdout was closed, exit
            self.running = False

if __name__ == "__main__":
    bridge = SaoMaiBridge()
    bridge.run()
