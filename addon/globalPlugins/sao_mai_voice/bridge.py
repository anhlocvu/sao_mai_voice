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
        self.bridge.active_streams.add(StreamNumber)
        self.bridge.send_response({"event": "start", "stream": StreamNumber})

    def EndStream(self, StreamNumber, StreamPosition):
        if StreamNumber not in self.bridge.active_streams:
            return
            
        self.bridge.active_streams.remove(StreamNumber)
            
        # Check if SpVoice is still busy speaking or has queued items
        is_busy = False
        try:
            # RunningState: 2 is speaking/busy, 1 is done/idle
            is_busy = (self.bridge.voice.Status.RunningState == 2)
        except Exception:
            is_busy = bool(self.bridge.active_streams)
            
        if not is_busy:
            self.bridge.is_speaking = False
            self.bridge.active_streams.clear()
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
        self.active_streams = set()

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
                
        coalesced = []
        
        # Accumulate settings
        current_voice = None
        current_rate = None
        current_volume = None
        
        for cmd in cmds:
            action = cmd.get("action")
            if action == "speak":
                if "voice" in cmd and cmd["voice"] is not None:
                    current_voice = cmd["voice"]
                if "rate" in cmd and cmd["rate"] is not None:
                    current_rate = cmd["rate"]
                if "volume" in cmd and cmd["volume"] is not None:
                    current_volume = cmd["volume"]
                
                text = cmd.get("text", "")
                if text:
                    # Create a new speak command with accumulated settings so far
                    speak_cmd = {
                        "action": "speak",
                        "text": text,
                        "voice": current_voice,
                        "rate": current_rate,
                        "volume": current_volume
                    }
                    speak_cmd = {k: v for k, v in speak_cmd.items() if v is not None}
                    coalesced.append(speak_cmd)
                    
            elif action == "cancel":
                # Cancel clears all pending speak commands in the batch
                coalesced = [{"action": "cancel"}]
                
        # If there are accumulated settings at the end and no speak command followed them,
        # we append a settings update command (speak with empty text)
        if not coalesced or coalesced[-1].get("action") == "cancel":
            settings_cmd = {
                "action": "speak",
                "text": "",
                "voice": current_voice,
                "rate": current_rate,
                "volume": current_volume
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
                # Pump COM events briefly (2ms timeout) to allow SAPI events to be fired
                # This blocks the main thread in a COM-safe way when idle.
                comtypes.client.PumpEvents(0.002)
                
                # Process commands from queue on Main Thread (non-blocking)
                cmds = []
                try:
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
            
            # Apply settings if provided (takes effect immediately on SpVoice)
            if voice_name and voice_name in self.tokens:
                self.voice.Voice = self.tokens[voice_name]
            if rate is not None:
                # SAPI5 rate is -10 to 10
                self.voice.Rate = int(rate)
            if volume is not None:
                self.voice.Volume = int(volume)
                
            # Speak asynchronously if text is provided
            if text:
                # SVSFlagsAsync = 1, SVSFIsXML = 8
                # SAPI5 will automatically queue multiple Speak calls sequentially
                flags = 1 | 8
                try:
                    stream_num = self.voice.Speak(text, flags)
                    if isinstance(stream_num, int):
                        self.active_streams.add(stream_num)
                except Exception as e:
                    sys.stderr.write(f"Speak error: {e}\n")
                    sys.stderr.flush()
            
        elif action == "cancel":
            # Always execute cancel to ensure the engine is cleared properly
            self.is_speaking = False
            self.active_streams.clear()
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
