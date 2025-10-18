# ==================================================================================================================
# Real-Time Accompaniment Generation Pipeline
# Based on 2 threads:
#   - Timing thread: predicts and schedules chords
#                    prediction is based on a sliding window of previous chords and HarmonyRules
#                    scheduled chords are stored in a list for playback that contains all chords as objects
#   - Playback thread: plays chords by reading from the scheduled list at the right time
# ==================================================================================================================


import time
import threading
from typing import List, Optional
from collections import deque

# custom modules
from chord import Chord
from harmony_rules import HarmonyRules
from utils import play_chord, chord_to_roman, play_chord_sequence

OUTPUT_PORT = 'Driver IAC Bus 1'
DELAY_START_SECONDS = 2.0  # Delay before starting the first chord


class RealTimePipeline:
    
    def __init__(self, key: str = 'C', chord_type: str = 'major', bpm: int = 120, beats_per_chord: float = 4.0, 
                 window_size: int = 4, max_sequence_length: int = 10, output_port: str = OUTPUT_PORT):
        
        # Internal configuration
        self.key = key
        self.bpm = bpm
        self.beats_per_chord = beats_per_chord
        self.chord_duration_seconds = (beats_per_chord * 60.0) / bpm
        self.window_size = window_size                                          # number of previous chords to consider for prediction
        self.max_sequence_length = max_sequence_length                          # maximum number of chords to generate
        self.output_port = output_port                                          # MIDI output port name
        
        # Harmony rules engine for prediction
        self.harmony = HarmonyRules(key)
        
        # Real-time state data
        self.chord_window = deque(maxlen=window_size)                           # window of last window_size chords as roman numerals
        self.chord_objects = []                                                 # full chord objects sequence for final playback
        self.current_chord_idx = 0                                              # current index in chord sequence
        self.is_running = False                                                 # flag to control the threads
        self.start_time = None                                                  # start time tracker for scheduling
        
        # Pre-generate starting chord with correct duration
        self.starting_chord = Chord(key, chord_type, bpm, beats_per_chord)
        
        
    # ================================= Main thread functions =======================================
    
    
    # Core prediction logic - called when we need next chord
    def _predict_and_schedule_next(self):

        if len(self.chord_window) == 0:
            return None
        
        # Predict next chord using harmony rules
        chord_tuple, _ = self.harmony.get_next_chord_distribution(self.chord_window)
        if chord_tuple is None:
            print("[DEBUG] Warning: Prediction returned None, using fallback C major")
            chord_tuple = ('C', 'major')

        # Convert to Chord object
        root, chord_type = chord_tuple
        next_chord = Chord(root, chord_type, self.bpm, self.beats_per_chord)
        
        # Add to sequence for playback
        self.chord_objects.append(next_chord)
        # next_roman = self._chord_string_to_roman(next_chord_string)
        next_roman = chord_to_roman(self.key, root, chord_type)
        # Update chord window adding roman chord
        self.chord_window.append(next_roman)
        
        return next_chord
    
    
    
    # Real time thread: it predicts and schedules chords for playback
    def _timing_thread(self):

        self.start_time = time.time()
        
        # ADD START DELAY HERE
        time.sleep(DELAY_START_SECONDS)

        # Play starting chord by adding it to sequence and add to window
        self.chord_objects.append(self.starting_chord)
        self.chord_window.append('I')  # Starting chord is always tonic TODO: generalize
        self.current_chord_idx = 1
        
        print(f"\n[{time.time() - self.start_time:.1f}s] Scheduling chord 1: {self.starting_chord}")
        
        # Schedule following chords
        while self.is_running and len(self.chord_objects) < self.max_sequence_length:
            # Calculate when next chord should start
            next_chord_time = self.start_time + DELAY_START_SECONDS + (self.current_chord_idx * self.chord_duration_seconds)
            current_time = time.time()
            
            # Sleep until next chord time
            wait_time = next_chord_time - current_time
            if wait_time > 0:
                time.sleep(wait_time)
            
            # Predict and add next chord
            next_chord = self._predict_and_schedule_next()
            if next_chord:
                self.current_chord_idx += 1
                print(f"\n[{time.time() - self.start_time:.1f}s] Scheduling next chord {self.current_chord_idx}: {next_chord}")
                print(f"\tWindow: {' -> '.join(list(self.chord_window))}")
            else:
                break
        
        print(f"[{time.time() - self.start_time:.1f}s] Sequence complete!")
        self.is_running = False
    
    
    
    # MIDI playback thread - plays chords as they're generated in the list, at the right time
    def _playback_thread(self):

        last_played_idx = -1
        
        while self.is_running or last_played_idx < len(self.chord_objects) - 1:
            
            # Check if new chords are available to play
            if len(self.chord_objects) > last_played_idx + 1:
                chord_to_play = self.chord_objects[last_played_idx + 1]
                
                # Calculate timing for this chord
                chord_idx = last_played_idx + 1
                play_time = self.start_time + DELAY_START_SECONDS + (chord_idx * self.chord_duration_seconds)

                # Wait until it's time to play
                current_time = time.time()
                wait_time = play_time - current_time
                if wait_time > 0:
                    time.sleep(wait_time)
                
                # Play chord
                try:
                    if self.output_port:
                        play_chord(chord_to_play, self.output_port)
                        # play_chord_sequence([chord_to_play], self.output_port)
                    else:
                        print("[DEBUG] Playback port not available, skipping MIDI playback")
                        
                except Exception as e:
                    print(f"[DEBUG] MIDI playback error: {e}")
                    print(f"[DEBUG] Would play: {chord_to_play}")
                
                last_played_idx += 1
                
            # No new chords, sleep briefly               
            else:
                time.sleep(0.01)
    
    
    
    # Starts the real-time pipeline
    def start(self):
        
        if self.is_running:
            print("[INFO] Pipeline already running!")
            return
            
        print(f"[INFO] Starting real-time pipeline in key {self.key} @ {self.bpm} BPM")
        print(f"[INFO] Chord duration: {self.chord_duration_seconds:.1f}s ({self.beats_per_chord} beats)")
        print(f"[INFO] Will generate {self.max_sequence_length} chords total")
        print(f"[INFO] Waiting {DELAY_START_SECONDS} seconds before starting...\n")

        self.is_running = True
        
        # Start timing thread: predicts and schedules chords
        timing_thread = threading.Thread(target=self._timing_thread, daemon=True)
        timing_thread.start()
        
        # Start MIDI playback thread: plays chords as they're generated in the list, at the right time 
        playback_thread = threading.Thread(target=self._playback_thread, daemon=True)
        playback_thread.start()
        
        # Wait for completion
        timing_thread.join()
        playback_thread.join()
        
        return self.chord_objects
    
    
    # Stops the pipeline
    def stop(self):
        self.is_running = False
    
    
    
    # ================================= Helper functions =======================================
        
        
    def get_current_sequence(self) -> List[str]:
        """Get current sequence as compact chord names"""
        from utils import compact_chord
        
        if not self.chord_objects:
            return []
        
        # Convert each chord to compact notation individually
        compact_names = []
        for chord in self.chord_objects:
            compact_name = compact_chord(chord.root, chord.chord_type)
            compact_names.append(compact_name)
        
        return compact_names


# ================================= Main test =======================================

if __name__ == "__main__":
    # Test the pipeline
    BPM = 120
    KEY = 'A'
    BEATS_PER_CHORD = 4.0
    
    try:
        pipeline = RealTimePipeline(key=KEY, bpm=BPM, beats_per_chord=BEATS_PER_CHORD, 
                                   window_size=4, max_sequence_length=8, 
                                   output_port=OUTPUT_PORT)
    except:
        print("Warning: No MIDI port found")
        exit(1)
    
    print("=" * 50)
    print("REAL-TIME ACCOMPANIMENT PIPELINE")
    print("=" * 50)
    
    # Start pipeline
    final_sequence = pipeline.start()
    
    # Show final results
    print("\n" + "=" * 50)
    print("FINAL SEQUENCE:")
    print("=" * 50)
    sequence_names = pipeline.get_current_sequence()
    for i, (chord_obj, chord_name) in enumerate(zip(final_sequence, sequence_names)):
        print(f"Chord {i+1}: {chord_name} ({chord_obj.root} {chord_obj.chord_type})")
    
    print(f"\nTotal duration: {len(final_sequence) * pipeline.chord_duration_seconds:.1f} seconds")