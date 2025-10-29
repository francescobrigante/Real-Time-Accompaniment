# ==================================================================================================================
# Real-Time Accompaniment Generation Pipeline
# Based on different threads:
#   - Timing thread: predicts and schedules chords
#                    Chord-based Prediction: based on a sliding window of previous chords and HarmonyRules
#                    Note-based Refinement: based on recent played notes from MIDI input and NotesHarmonyRules
#                    scheduled chords are stored in a list for playback that contains all chords as objects
#   - Playback thread: plays chords by reading from the scheduled list at the right time
#   - (Optional) Metronome thread: plays metronome clicks on each beat
# ==================================================================================================================

# TODO
# migliorare pipeline predizione da accordi
# implementare basic predizione con note:
    # collegare distribuzione accordi alla distribuzione note per predizione finale
    
# TODO gestire caso in cui input delle note viene missato perchè una nota è premuta ma non rilasciata a fine accordo

import time
import threading
from typing import List, Optional
from collections import deque

# custom modules
from chord import Chord
from harmony_rules import HarmonyRules
from notes_harmony_rules import NotesHarmonyRules
from utils import play_chord, chord_to_roman
from midi_listener import MidiInputListener
from metronome import metronome_thread, EMPTY_BARS_COUNT
from metronome import init_metronome, metronome_thread_synth

OUTPUT_PORT = 'IAC Piano IN' # vmpk virtual piano for playback
INPUT_PORT = 'IAC Piano OUT' # vmpk virtual piano for notes input
# INPUT_PORT = 'Digital Piano' # yamaha physical keyboard

# Delay configuration
DELAY_START_SECONDS = 2.0  # Fixed delay when metronome is disabled


# ================================= Main Pipeline Class =======================================

class RealTimePipeline:
    
    def __init__(self, key: str = 'C', chord_type: str = 'major', bpm: int = 120, beats_per_chord: float = 4.0, window_size: int = 4, 
                 max_sequence_length: int = 10, output_port: str = OUTPUT_PORT, input_port: Optional[str] = None, enable_input_listener: bool = False, enable_metronome: bool = True, empty_bars_count: int = EMPTY_BARS_COUNT):
        
        # Internal configuration
        self.key = key
        self.bpm = bpm
        self.beats_per_chord = beats_per_chord
        self.chord_duration_seconds = (beats_per_chord * 60.0) / bpm
        self.window_size = window_size                                          # number of previous chords to consider for prediction
        self.max_sequence_length = max_sequence_length                          # maximum number of chords to generate
        self.output_port = output_port                                          # MIDI output port name: sends MIDI event for playback
        self.input_port = input_port                                            # MIDI input port name: receives MIDI events for real-time input
        self.enable_input_listener = enable_input_listener                      # Flag to enable MIDI input listener
        self.enable_metronome = enable_metronome                                # Flag to enable metronome
        self.empty_bars_count = empty_bars_count                                # Number of empty bars before chords start
        
        # Calculate delay: use dynamic bars if metronome enabled, else fixed delay
        if self.enable_metronome:
            self.delay_seconds = empty_bars_count * beats_per_chord * (60.0 / bpm)
        else:
            self.delay_seconds = DELAY_START_SECONDS
        
        # MIDI Input listener
        if self.enable_input_listener and self.input_port:
            self.midi_listener = MidiInputListener(port_name=self.input_port, window_size=8, bpm=self.bpm)
        else:
            self.midi_listener = None
        
        # Harmony rules engine for prediction
        self.harmony = HarmonyRules(key)                                        # First pipeline: chord based
        self.notes_harmony = NotesHarmonyRules(key)                             # Second pipeline: note based
        
        # Real-time state data
        self.chord_window = deque(maxlen=window_size)                           # window of last window_size chords as roman numerals
        self.chord_objects = []                                                 # full chord objects sequence for final playback
        self.current_chord_idx = 0                                              # current index in chord sequence
        self.is_running = False                                                 # flag to control the threads
        self.start_time = None                                                  # start time tracker for scheduling
        
        # Pre-generate starting chord with correct duration
        self.starting_chord = Chord(key, chord_type, bpm, beats_per_chord)
        
        # NEW
        self.metronome_synth = init_metronome()
        
    # ================================= Main thread functions =======================================
    
    
    # Core prediction logic - called when we need next chord
    def _predict_next_chord(self):

        if len(self.chord_window) == 0:
            return None
        
        # Predict next chord using harmony rules
        chord_tuple, _ = self.harmony.get_next_chord_distribution(self.chord_window)
        if chord_tuple is None:
            # Fallback to tonic chord in current key
            print(f"[DEBUG] Warning: Prediction returned None, using fallback to tonic ({self.key} major)")
            chord_tuple = (self.key, 'major')

        # Convert to Chord object
        root, chord_type = chord_tuple
        next_chord = Chord(root, chord_type, self.bpm, self.beats_per_chord)
        
        return next_chord
    
    # TODO: add probability distribution output input
    def _refine_prediction(self, scheduled_chord: Chord) -> Chord:
        
        if not self.midi_listener:
            return scheduled_chord
        
        # Get last played notes from listener
        note_window = self.midi_listener.get_note_window()
        
        # No notes played
        if not note_window:
            return None
        
        predicted_chord_tuple, _, _, _ = self.notes_harmony.predict_with_scores(note_window)
        
        if predicted_chord_tuple is None:
            return None
        
        # Create new Chord object from prediction
        root, chord_type = predicted_chord_tuple
        predicted_chord = Chord(root, chord_type, self.bpm, self.beats_per_chord)
        
        print(f"[INFO] CHORD PREDICTION: {scheduled_chord} -> NOTE PREDICTION: {predicted_chord}")
        
        return predicted_chord


    # Real time thread: it predicts and schedules chords for playback
    def _timing_thread(self):

        self.start_time = time.time()
        
        # Wait for empty bars with metronome
        time.sleep(self.delay_seconds)

        # Play starting chord by adding it to sequence and add to window
        self.chord_objects.append(self.starting_chord)
        self.chord_window.append('I')  # Starting chord is always tonic TODO: generalize
        self.current_chord_idx = 1
        
        print(f"\n[{time.time() - self.start_time:.1f}s] Scheduling chord 1: {self.starting_chord}")
        
        # Schedule following chords
        while self.is_running and self.current_chord_idx < self.max_sequence_length:
            # Calculate when next chord should start
            next_chord_time = self.start_time + self.delay_seconds + (self.current_chord_idx * self.chord_duration_seconds)
            current_time = time.time()
            
            # Sleep until next chord time
            wait_time = next_chord_time - current_time
            if wait_time > 0:
                time.sleep(wait_time)
            
            # CHORD PIPELINE Prediction
            predicted_chord = self._predict_next_chord()
            if not predicted_chord:
                print("[DEBUG] No predicted chord, ending sequence")
                break
            
            # NOTES PIPELINE Refinement (returns None if no notes played)
            refined_chord = self._refine_prediction(predicted_chord)
            
            # If no notes played, skip prediction and wait for next beat
            if not refined_chord:
                print(f"[{time.time() - self.start_time:.1f}s] No notes played, waiting for input...")
                self.current_chord_idx += 1
                
                # Clear window and continue timing
                if self.midi_listener:
                    self.midi_listener.clear_note_window()
                continue
            
            # Notes were played - use refined chord
            # TODO: combine both predictions
            final_chord = refined_chord
            
            # Add final chord to sequence (used for playback)
            self.chord_objects.append(final_chord)
            
            # Update window with final chord's roman numeral
            final_roman = chord_to_roman(self.key, final_chord.root, final_chord.chord_type)
            self.chord_window.append(final_roman)
            
            self.current_chord_idx += 1
            print(f"\n[{time.time() - self.start_time:.1f}s] Final chord {self.current_chord_idx}: {final_chord}")
            print(f"\tWindow: {' -> '.join(list(self.chord_window))}")
            
            # Clear note window after each prediction cycle
            if self.midi_listener:
                self.midi_listener.clear_note_window()
        
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
                play_time = self.start_time + self.delay_seconds + (chord_idx * self.chord_duration_seconds)

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
        
        if self.enable_metronome:
            print(f"[INFO] Metronome enabled at {self.bpm} BPM")
            print(f"[INFO] Starting with {self.empty_bars_count} empty bar(s) of metronome ({self.delay_seconds:.1f}s)")
        else:
            print(f"[INFO] Waiting {self.delay_seconds:.1f}s before starting...")
        

        # Start MIDI listener if enabled
        if self.midi_listener:
            print(f"[INFO] Starting MIDI input listener on port: {self.input_port}")
            self.midi_listener.start()
            # time.sleep(0.2)  # Give listener time to initialize

        self.is_running = True
        
        # Start metronome thread if enabled
        # if self.enable_metronome:
        #     metro_thread = threading.Thread(
        #         target=metronome_thread, 
        #         args=(lambda: self.start_time, self.bpm, self.beats_per_chord, 
        #               self.max_sequence_length, self.output_port, 
        #               lambda: self.is_running, self.empty_bars_count),
        #         daemon=True
        #     )
        #     metro_thread.start()
            
            
        # NEW
        if self.enable_metronome:
            metro_thread = threading.Thread(
                target=metronome_thread_synth, 
                args=(lambda: self.start_time, self.bpm, self.beats_per_chord, 
                      self.max_sequence_length,
                      self.metronome_synth,
                      lambda: self.is_running, self.empty_bars_count),
                daemon=True
            )
            metro_thread.start()
        
        # Start timing thread: predicts and schedules chords
        timing_thread = threading.Thread(target=self._timing_thread, daemon=True)
        timing_thread.start()
        
        # Start MIDI playback thread: plays chords as they're generated in the list, at the right time 
        playback_thread = threading.Thread(target=self._playback_thread, daemon=True)
        playback_thread.start()
        
        try:
            # Wait for completion
            timing_thread.join()
            playback_thread.join()
            
        except KeyboardInterrupt as e:
            
            print(f"[\n\nWARNING] KeyboardInterrupt occurred, stopping pipeline: {e}")
            self.stop() 
            # Give threads time to clean up
            print("[INFO] Waiting for threads to finish...\n\n")
            timing_thread.join(timeout=2.0)
            playback_thread.join(timeout=2.0)
            
        finally:
            
            # Stopping MIDI listener if running after other threads finish
            if self.midi_listener:
                print("[INFO] Stopping MIDI input listener...")
                self.midi_listener.stop()
                self.midi_listener.join(timeout=1.0)
                
            # NEW
            if self.metronome_synth:
                self.metronome_synth.delete()
                self.metronome_synth = None
        
        return self.chord_objects
    
    
    # Stops the pipeline
    def stop(self):
        self.is_running = False
        
        if self.midi_listener:
            self.midi_listener.stop()
            
        # NEW
        if self.metronome_synth:
            self.metronome_synth.delete()
            self.metronome_synth = None
    
    
    
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
    KEY = 'C'
    BEATS_PER_CHORD = 4.0
    SEQUENCE_LENGTH = 10
    
    try:
        pipeline = RealTimePipeline(key=KEY, bpm=BPM, beats_per_chord=BEATS_PER_CHORD, window_size=4, max_sequence_length=SEQUENCE_LENGTH, 
                                   output_port=OUTPUT_PORT, input_port=INPUT_PORT, enable_input_listener=True, enable_metronome=True)
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
    
    # battuta a vuoto metronomo