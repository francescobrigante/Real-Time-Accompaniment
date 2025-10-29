# =============================================================================
# FluidSynth MIDI Playback Module
# Low-latency modular synthesizer for real-time accompaniment playback
# Based on:
#   - SynthPlayer class that handles synth functionalities
#   - MIDIListener class that listens to a virtual MIDI port forwarding messages to SynthPlayer
# =============================================================================

import fluidsynth
import mido
import threading
import time
from typing import Optional


# Static data
DEFAULT_SOUNDFONT = "playback/GeneralUser-GS.sf2" # Sounds used for synthesis
DEFAULT_PROGRAM = 0  # Acoustic Grand Piano, try 1 e 2
DEFAULT_CHANNEL = 0
DEFAULT_GAIN = 1.0  # Volume level

# Audio driver selection based on OS
AUDIO_DRIVERS = {
    'darwin': 'coreaudio',   # macOS
    'linux': 'alsa',         # Linux
    'win32': 'dsound'        # Windows
}

#TODO: driver asio per windows pe prevenire latenza


# ================================= Core Synth Player =======================================

class SynthPlayer:
    """
    Low-latency FluidSynth-based synthesizer for real-time MIDI playback.
    Handles MIDI message processing and sound generation.
    """
    
    def __init__(self, soundfont_path: str = DEFAULT_SOUNDFONT, 
                 program: int = DEFAULT_PROGRAM, 
                 channel: int = DEFAULT_CHANNEL,
                 gain: float = DEFAULT_GAIN,
                 audio_driver: Optional[str] = None):
        """
        Args:
            soundfont_path: Path to .sf2 SoundFont file
            program: MIDI program number (0 = Acoustic Grand Piano)
            channel: MIDI channel to use (0-15)
            gain: Audio gain/volume (0.0 to 1.0)
            audio_driver: Audio driver ('coreaudio', 'alsa', 'dsound'). Auto-detected if None.
        """
        self.soundfont_path = soundfont_path
        self.program = program
        self.channel = channel
        self.gain = gain
        
        # Auto-detect audio driver if not specified
        if audio_driver is None:
            import sys
            platform = sys.platform
            self.audio_driver = AUDIO_DRIVERS.get(platform, 'coreaudio')
        else:
            self.audio_driver = audio_driver
        
        # Synth state
        self.synth = None
        self.sfid = None
        self.is_running = False
        
    
    def initialize(self) -> bool:
        """
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            # Create synth instance with optimized settings for low latency
            self.synth = fluidsynth.Synth(gain=self.gain, samplerate=44100.0)
            
            # Start audio driver with low latency settings
            self.synth.start(driver=self.audio_driver)
            
            # Load SoundFont
            self.sfid = self.synth.sfload(self.soundfont_path)
            if self.sfid == -1:
                raise FileNotFoundError(f"[ERROR] Cannot load SoundFont: {self.soundfont_path}")
            
            self.synth.program_select(self.channel, self.sfid, 0, self.program)
            
            self.is_running = True
            
            print(f"[SYNTH] Synthesizer initialized with gain={self.gain}, on channel {self.channel}, using SoundFont: {self.soundfont_path}")
            
            return True
            
        except Exception as e:
            print(f"[SYNTH ERROR] Initialization failed: {e}")
            import traceback
            traceback.print_exc()
            self.cleanup()
            
            return False
    
    
    def play_note(self, note: int, velocity: int = 100):
        """
        Args:
            note: MIDI note number (0-127)
            velocity: Note velocity (0-127)
        """
        if self.synth and self.is_running:
            self.synth.noteon(self.channel, note, velocity)
    
    
    def stop_note(self, note: int):
        if self.synth and self.is_running:
            self.synth.noteoff(self.channel, note)
    
    
    def handle_midi_message(self, msg: mido.Message):
        """
        Process a MIDI message and send to synth for playback
        
        Args:
            msg: mido.Message object
        """
        if not self.is_running:
            return
        
        try:
            # Use message's channel if specified, otherwise use synth's default channel
            channel = msg.channel if hasattr(msg, 'channel') else self.channel
            note_string = self.get_note_name(msg.note)
            
            if msg.type == 'note_on':
                if msg.velocity > 0:
                    print(f"[SYNTH] Playing note {note_string} ({msg.note} MIDI) with velocity {msg.velocity}")
                    self.synth.noteon(channel, msg.note, msg.velocity)
                else:
                    # Velocity 0 is equivalent to note_off
                    print(f"[ERROR] Velocity 0 -> stopping note {note_string} ({msg.note} MIDI)")
                    self.synth.noteoff(channel, msg.note)
                    
            elif msg.type == 'note_off':
                print(f"[SYNTH] Released note {note_string} ({msg.note} MIDI)")
                self.synth.noteoff(channel, msg.note)
                
        except Exception as e:
            print(f"[SYNTH ERROR] Error handling MIDI message: {e}")
            print(f"[SYNTH ERROR] Message was: {msg}")
    
    
    
    # Closes and cleans up the synthesizer resources
    def cleanup(self):
        if self.synth:
            if self.sfid is not None and self.sfid != -1:
                self.synth.sfunload(self.sfid)
            self.synth.delete()
            print("[SYNTH] Synthesizer closed")
        self.is_running = False
        
    def get_note_name(self, midi_note: int) -> str:
        CHROMATIC_NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        note_name = CHROMATIC_NOTES[midi_note % 12]
        octave = (midi_note // 12) - 1
        return f"{note_name}{octave}"


# ================================= MIDI Port Listener =======================================

class MIDIListener:
    """
    Listens to a virtual MIDI input port and forwards messages to SynthPlayer.
    Runs in a separate thread for minimal latency.
    """
    
    def __init__(self, port_name: str, synth_player: SynthPlayer):
        """
        Args:
            port_name: Name of MIDI input port to listen to
            synth_player: SynthPlayer instance to send messages to
        """
        self.port_name = port_name
        self.synth_player = synth_player
        self.is_running = False
        self.thread = None
        self.midi_port = None
    
    # Internal listening loop running in separate thread
    def _listen_loop(self):
        try:
            self.midi_port = mido.open_input(self.port_name)
            
            # Low-latency message processing loop
            for msg in self.midi_port:
                if not self.is_running:
                    break
                
                # Forward to synth immediately
                self.synth_player.handle_midi_message(msg)
                
        except Exception as e:
            print(f"[MIDI ERROR] Listener error: {e}")
            
        finally:
            # Cleanup on exit
            if self.midi_port:
                self.midi_port.close()
                print("[MIDI INFO] Port closed")
    
    
    # Start listening in background thread
    def start(self):

        if self.is_running:
            print("[MIDI WARNING] Already listening")
            return
        
        self.is_running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
    
    
    # Stop listening
    def stop(self):
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2.0)
            


# ================================= High-Level Interface =======================================

def create_playback_synth(midi_port_name: str, soundfont_path: str = DEFAULT_SOUNDFONT, program: int = DEFAULT_PROGRAM, gain: float = DEFAULT_GAIN) -> tuple[SynthPlayer, MIDIListener]:
    """
    Create and initialize a complete real-time synth system.
    
    Args:
        midi_port_name: MIDI input port to listen to (e.g., 'IAC Piano IN')
        soundfont_path: Path to SoundFont file
        program: MIDI program number
        gain: Audio volume (0.0 to 1.0)
    
    Returns:
        Tuple of (SynthPlayer, MIDIListener) instances
    """
    
    # Create synth
    synth = SynthPlayer(soundfont_path=soundfont_path, program=program, gain=gain)
    
    # Initialize synth engine
    if not synth.initialize():
        raise RuntimeError("[ERROR] Failed to initialize synthesizer")
    
    # Create MIDI listener
    listener = MIDIListener(midi_port_name, synth)
    
    return synth, listener


# ================================= Main Test =======================================

def main():
    """Test the synth player with a simple sequence."""
    
    # Configuration
    MIDI_PORT = 'IAC Piano IN'
    SOUNDFONT = DEFAULT_SOUNDFONT
    PROGRAM = 0
    GAIN = 1.0
    
    print("=" * 60)
    print("FLUIDSYNTH REAL-TIME PLAYER TEST")
    print("=" * 60)
    
    # Check audio setup
    try:
        import subprocess
        result = subprocess.run(['system_profiler', 'SPAudioDataType'], capture_output=True, text=True, timeout=5)
        print("[DEBUG] Audio devices found")
    except:
        print("[DEBUG] Could not check audio devices")
    
    print()
    
    try:
        # Create synth system
        synth, listener = create_playback_synth(
            midi_port_name=MIDI_PORT,
            soundfont_path=SOUNDFONT,
            program=PROGRAM,
            gain=GAIN
        )
        
        print(f"\n[INFO] Synth ready! Listening on: {MIDI_PORT}")
        print("[INFO] Press Ctrl+C to stop...\n")
        
        # Start listening
        listener.start()
        
        # Keep running until interrupted
        while True:
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\n[INFO] Stopping...")
        
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Cleanup
        if 'listener' in locals():
            listener.stop()
        if 'synth' in locals():
            synth.cleanup()
        
        print("[INFO] Shutdown complete")


if __name__ == "__main__":
    main()