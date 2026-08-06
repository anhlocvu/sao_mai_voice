import os
import sys
import winreg

CLSID_SAO_MAI = "{7DDCD6E4-E60A-4C60-B7AA-C9A652FEEDF2}"

VOICES = {
    "SM_MaiDung": {
        "name": "Sao Mai Mai Dung",
        "vce": "MaiDung.vce",
        "dat": "MaiDung.dat",
        "lang": "42a",
        "gender": "Female"
    },
    "SM_MinhDu": {
        "name": "Sao Mai Minh Du",
        "vce": "VNVoice.vce",
        "dat": "MinhDu.dat",
        "lang": "42a",
        "gender": "Female"
    },
    "SM_ThanhVi": {
        "name": "Sao Mai Thanh Vi",
        "vce": "VNVoice.vce",
        "dat": "ThanhVi.dat",
        "lang": "42a",
        "gender": "Female"
    },
    "SM_ThuAn": {
        "name": "Sao Mai Thu An",
        "vce": "VNVoice.vce",
        "dat": "ThuAn.dat",
        "lang": "42a",
        "gender": "Female"
    },
    "SM_Daniel": {
        "name": "Sao Mai Daniel",
        "vce": "Daniel.vce",
        "dat": "Daniel.dat",
        "lang": "409",
        "gender": "Male"
    }
}

def register_all(lib_path):
    """
    Registers the VnTtsEng.dll CLSID and all voice tokens in HKCU registry.
    lib_path: Absolute path to the directory containing DLL and voice files.
    """
    dll_path = os.path.join(lib_path, "VnTtsEng.dll")
    if not os.path.exists(dll_path):
        raise FileNotFoundError(f"DLL not found: {dll_path}")

    # 1. Register COM CLSID in HKCU
    clsid_path = f"Software\\Classes\\CLSID\\{CLSID_SAO_MAI}"
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, clsid_path)
        winreg.SetValue(key, "", winreg.REG_SZ, "Sao Mai VNVoice TTS Engine")
        
        inproc_key = winreg.CreateKey(key, "InprocServer32")
        winreg.SetValue(inproc_key, "", winreg.REG_SZ, dll_path)
        winreg.SetValueEx(inproc_key, "ThreadingModel", 0, winreg.REG_SZ, "Both")
    except Exception as e:
        sys.stderr.write(f"Error registering CLSID: {e}\n")
        sys.stderr.flush()
        return False

    # 2. Register SAPI5 Voice Tokens
    tokens_base_path = "Software\\Microsoft\\Speech\\Voices\\Tokens"
    for token_id, voice_info in VOICES.items():
        vce_path = os.path.join(lib_path, voice_info["vce"])
        dat_path = os.path.join(lib_path, voice_info["dat"])
        
        if not os.path.exists(vce_path) or not os.path.exists(dat_path):
            sys.stderr.write(f"Warning: Skipping {token_id} because files do not exist.\n")
            sys.stderr.flush()
            continue
            
        token_path = f"{tokens_base_path}\\{token_id}"
        try:
            token_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, token_path)
            winreg.SetValue(token_key, "", winreg.REG_SZ, voice_info["name"])
            winreg.SetValueEx(token_key, "CLSID", 0, winreg.REG_SZ, CLSID_SAO_MAI)
            winreg.SetValueEx(token_key, "VoiceData", 0, winreg.REG_SZ, vce_path)
            winreg.SetValueEx(token_key, "VoiceDef", 0, winreg.REG_SZ, dat_path)
            
            # Attributes subkey
            attr_key = winreg.CreateKey(token_key, "Attributes")
            winreg.SetValueEx(attr_key, "Name", 0, winreg.REG_SZ, voice_info["name"])
            winreg.SetValueEx(attr_key, "Language", 0, winreg.REG_SZ, voice_info["lang"])
            winreg.SetValueEx(attr_key, "Gender", 0, winreg.REG_SZ, voice_info["gender"])
            winreg.SetValueEx(attr_key, "Age", 0, winreg.REG_SZ, "Adult")
            winreg.SetValueEx(attr_key, "Vendor", 0, winreg.REG_SZ, "Sao Mai Center")
        except Exception as e:
            sys.stderr.write(f"Error registering voice token {token_id}: {e}\n")
            sys.stderr.flush()
            return False
            
    sys.stderr.write("Registration completed successfully.\n")
    sys.stderr.flush()
    return True

def unregister_all():
    """
    Cleans up all registry entries created under HKCU.
    """
    # Helper to recursively delete registry keys
    def delete_key_recursive(key, subkey):
        try:
            hkey = winreg.OpenKey(key, subkey, 0, winreg.KEY_ALL_ACCESS)
        except OSError:
            return
        while True:
            try:
                sub = winreg.EnumKey(hkey, 0)
                delete_key_recursive(hkey, sub)
            except OSError:
                break
        winreg.CloseKey(hkey)
        try:
            winreg.DeleteKey(key, subkey)
        except OSError:
            pass

    # Delete voice tokens
    tokens_base_path = "Software\\Microsoft\\Speech\\Voices\\Tokens"
    for token_id in VOICES.keys():
        delete_key_recursive(winreg.HKEY_CURRENT_USER, f"{tokens_base_path}\\{token_id}")
        
    # Delete CLSID
    clsid_path = f"Software\\Classes\\CLSID\\{CLSID_SAO_MAI}"
    delete_key_recursive(winreg.HKEY_CURRENT_USER, clsid_path)
    sys.stderr.write("Unregistration completed.\n")
    sys.stderr.flush()
