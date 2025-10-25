# ==================================================================================================================
# Thread-safe MIDI input listener that tracks the last N completed notes with durations, using a sliding window.
# Only adds notes to window when they are released (note_on -> note_off).
# Tracks beat position for synchronization with real-time pipeline.
# ==================================================================================================================

import mido
import time
import threading
from typing import Optional, List, Tuple, Dict
from collections import deque

# Import shared constants from utils
from utils import CHROMATIC_NOTES


class MidiInputListener(threading.Thread):
    """
    MIDI input listener that tracks the last N completed notes with durations.
    Only adds notes to window when they are released (note_on -> note_off).
    Tracks beat position for synchronization with real-time pipeline.
    """
    
    def __init__(self, port_name: str, window_size: int = 10, bpm: float = 120.0):
        """
        Args:
            port_name: MIDI input port name to listen to
            window_size: Maximum number of completed notes to keep in history window
        """
        super().__init__(daemon=True)   # Daemon: auto-terminates when main thread exits
        self.port_name = port_name      # Input port name
        self.in_port = None             # MIDI input port object
        self.window_size = window_size
        self.bpm = bpm
        self.seconds_per_beat = 60.0 / bpm
        
        # Thread control
        self._stop_event = threading.Event()
        self._lock = threading.Lock()  # Protects all shared data below
        
        # Sliding window: stores (note_number, duration_beats) tuples
        # Duration is measured in beats (not seconds) for better music-time alignment
        self._note_window: deque = deque(maxlen=window_size)
        
        # Temporary storage: tracks when each note was pressed (note_number -> press_timestamp)
        # Used to calculate duration when note is released
        self._pending_notes: Dict[int, float] = {}
        
        # Beat position tracking: current position in beats since start
        # This allows the pipeline to know "where we are" in the musical timeline
        self._beat_position: float = 0.0
        self._start_time: Optional[float] = None  # Timestamp when first note was played



    # Main thread loop
    # Listens for incoming MIDI messages on the specified port and processes them until stopped
    def run(self):
        try:
            with mido.open_input(self.port_name) as self.in_port:
                print(f"[INFO] Listener MIDI started on port: {self.port_name}")
                
                while not self._stop_event.is_set():
                    # Check for pending messages
                    for msg in self.in_port.iter_pending():
                        self._process_message(msg)

                    # Release the CPU for a short while to avoid busy-waiting
                    time.sleep(0.001)
                    
        except Exception as e:
            print(f"[ERROR] Error in MIDI listener thread: {e}")
        finally:
            if self.in_port:
                self.in_port.close()
            print("[INFO] Listener MIDI stopped.")



    # Process a single MIDI message: track note_on/note_off and calculate durations
    def _process_message(self, msg):

        with self._lock:  # Thread-safe access
            
            # Note pressed: record timestamp for duration calculation
            if msg.type == 'note_on' and msg.velocity > 0:
                
                current_time = time.time()
                self._pending_notes[msg.note] = current_time
                
                # Print when note is pressed
                note_name = self._get_note_name(msg.note)
                print(f"🎹 Pressed note: {note_name} (MIDI {msg.note})")
                
                # Initialize start_time on first note
                if self._start_time is None:
                    self._start_time = current_time
                    self._beat_position = 0.0
                    
            # Note released: calculate duration and add to window  
            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                
                if msg.note in self._pending_notes:
                    press_time = self._pending_notes.pop(msg.note)
                    release_time = time.time()
                    
                    # Calculate duration in beats
                    duration_seconds = release_time - press_time
                    duration_beats = duration_seconds / self.seconds_per_beat
                    
                    # Print when note is released with duration
                    note_name = self._get_note_name(msg.note)
                    print(f"🎼 Released note: {note_name} (MIDI {msg.note}) with duration: {duration_beats:.2f} beats ({duration_seconds:.2f}s)")
                    
                    # Add completed note to sliding window
                    self._note_window.append((msg.note, duration_beats))
                    
                    # Update beat position (cumulative)
                    if self._start_time is not None:
                        elapsed_seconds = release_time - self._start_time
                        self._beat_position = elapsed_seconds / self.seconds_per_beat
                        
      
      
    # ======================================= Helper Functions =========================================
                        
    # Converts MIDI note number to note name (e.g., 60 -> C4)
    def _get_note_name(self, midi_note: int) -> str:

        note_name = CHROMATIC_NOTES[midi_note % 12]
        octave = (midi_note // 12) - 1
        return f"{note_name}{octave}"
    
    # TODO: note to MIDI

    def get_note_window(self) -> List[Tuple[int, float]]:
        with self._lock:
            return list(self._note_window)  # Return copy
        
    def clear_note_window(self):
        with self._lock:
            self._note_window.clear()
    
    def get_beat_position(self) -> float:
        """
        Returns the current position in beats since the first note was played.
        Used for synchronization with the real-time pipeline's chord progression.
        """
        with self._lock:
            return self._beat_position
    
    # Resets beat position to 0.0 and start time to now
    def reset_beat_position(self):
        with self._lock:
            self._start_time = time.time()
            self._beat_position = 0.0
    
    # Updates tempo
    def set_tempo(self, bpm: float):
        with self._lock:
            self.bpm = bpm
            self.seconds_per_beat = 60.0 / bpm

    # Stops the listener thread
    def stop(self):
        self._stop_event.set()
        

        
# ==================================== Main Test Block ============================================        

if __name__ == "__main__":
    
    port = "IAC Piano OUT"
    port = "Digital Piano"

    listener = MidiInputListener(port, window_size=8, bpm=120)
    listener.start()

    print("🎹 Suona con VMPK! Press Ctrl+C to stop...\n")

    try:
        while True:
            time.sleep(0.1)  # Just keep alive
            
    except KeyboardInterrupt:
        print("\n[INFO] Stopping...")

    listener.stop()
    listener.join()