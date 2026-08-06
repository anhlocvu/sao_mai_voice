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
        self.bridge.send_response({"event": "start", "stream": StreamNumber})

    def EndStream(self, StreamNumber, StreamPosition):
        self.bridge.send_response({"event": "end", "stream": StreamNumber})

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

    def run(self):
        try:
            self.init_sapi()
            
            # Start background thread to read input
            input_thread = threading.Thread(target=self.read_input)
            input_thread.daemon = True
            input_thread.start()

            # Main loop on Main Thread to process COM events and queue commands
            while self.running:
                # Pump COM messages to process events
                comtypes.client.PumpEvents(0.01)
                
                # Process commands from queue on Main Thread
                try:
                    while not self.cmd_queue.empty():
                        cmd = self.cmd_queue.get_nowait()
                        self.handle_command(cmd)
                        self.cmd_queue.task_done()
                except queue.Empty:
                    pass
                    
                time.sleep(0.01)
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
            # SPF_ASYNC = 1, SPF_PURGEBEFORESPEAK = 2
            flags = 1 | 2
            self.voice.Speak(text, flags)
            
        elif action == "cancel":
            # Cancel current speech by speaking empty string with PURGE
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
