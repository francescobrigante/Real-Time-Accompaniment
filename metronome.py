# ==================================================================================================================
# Metronome Module
# Plays metronome clicks on each beat with an accent on the first beat of each bar
# ==================================================================================================================

import time
import mido
import fluidsynth

# Metronome configuration
METRONOME_NOTE = 76  # MIDI note for metronome click (E5)
METRONOME_VELOCITY = 100
METRONOME_DURATION = 0.05  # Short click duration in seconds
EMPTY_BARS_COUNT = 1  # Number of empty bars with metronome before starting chords

# Synth-based metronome configuration
METRONOME_SOUNDFONT = "playback/GeneralUser-GS.sf2"
METRONOME_PROGRAM = 115  # Woodblock (perfect for metronome)
METRONOME_CHANNEL = 9  # MIDI channel 9 is typically for percussion
METRONOME_GAIN = 0.8  # Volume level for metronome


def metronome_thread(start_time, bpm, beats_per_chord, max_sequence_length, output_port, is_running_flag, empty_bars_count):
    """
    Plays metronome clicks on each beat.
    
    Args:
        start_time: Lambda function returning the start time (or None if not yet set)
        bpm: Beats per minute
        beats_per_chord: Number of beats per chord
        max_sequence_length: Maximum number of chords in sequence
        output_port: MIDI output port name
        is_running_flag: Lambda function returning running state
        empty_bars_count: Number of empty bars before chords start
    """
    
    if not output_port:
        return
        
    try:
        outport = mido.open_output(output_port)
    except Exception as e:
        print(f"[DEBUG] Could not open metronome output port: {e}")
        return
    
    beat_duration = 60.0 / bpm  # Duration of one beat in seconds
    
    # Wait for start time to be set from main thread
    while start_time() is None and is_running_flag():
        time.sleep(0.01)
    
    if not is_running_flag():
        outport.close()
        return
    
    # Get the actual start_time value by calling the lambda
    start_time_value = start_time()
    
    # Calculate total beats: empty bars + chord sequence
    delay_beats = int(empty_bars_count * beats_per_chord)
    total_beats = delay_beats + int(max_sequence_length * beats_per_chord)
    
    beat_count = 0
    while is_running_flag() and beat_count < total_beats:

        # Calculate when the next beat should occur (timing starts immediately from start_time)
        beat_time = start_time_value + (beat_count * beat_duration)
        current_time = time.time()
        
        # Sleep until the next beat time
        wait_time = beat_time - current_time
        if wait_time > 0:
            time.sleep(wait_time)
        
        # Accent to first beat of each measure
        velocity = METRONOME_VELOCITY + 20 if beat_count % beats_per_chord == 0 else METRONOME_VELOCITY
        
        # Play click
        try:
            outport.send(mido.Message('note_on', note=METRONOME_NOTE, velocity=velocity))
            time.sleep(METRONOME_DURATION)
            outport.send(mido.Message('note_off', note=METRONOME_NOTE))
            
        except Exception as e:
            print(f"[DEBUG] Metronome playback error: {e}")
        
        beat_count += 1
    
    outport.close()


# ================================= Synth-based Metronome Functions =======================================

def init_metronome(soundfont_path: str = METRONOME_SOUNDFONT, 
                   program: int = METRONOME_PROGRAM,
                   channel: int = METRONOME_CHANNEL,
                   gain: float = METRONOME_GAIN):
    """
    Initialize FluidSynth for metronome playback.
    
    Args:
        soundfont_path: Path to .sf2 SoundFont file
        program: MIDI program number (115 = Woodblock, 116 = Taiko Drum)
        channel: MIDI channel (9 is percussion)
        gain: Audio gain/volume (0.0 to 1.0)
    
    Returns:
        Initialized fluidsynth.Synth instance, or None if initialization fails
    """
    try:
        # Create synth instance
        synth = fluidsynth.Synth(gain=gain, samplerate=44100.0, audio_periods=2, audio_period_size=64)
        
        # Start audio driver (auto-detect platform)
        import sys
        audio_drivers = {
            'darwin': 'coreaudio',   # macOS
            'linux': 'alsa',         # Linux
            'win32': 'dsound'        # Windows
        }
        driver = audio_drivers.get(sys.platform, 'coreaudio')
        synth.start(driver=driver)
        
        # Load SoundFont
        sfid = synth.sfload(soundfont_path)
        if sfid == -1:
            raise FileNotFoundError(f"Cannot load SoundFont: {soundfont_path}")
        
        # Select metronome sound
        synth.program_select(channel, sfid, 0, program)
        
        print(f"[METRONOME] Synth initialized with program {program} on channel {channel}")
        
        return synth
        
    except Exception as e:
        print(f"[METRONOME ERROR] Initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def metronome_thread_synth(start_time, bpm, beats_per_chord, max_sequence_length, 
                           synth, is_running_flag, empty_bars_count,
                           channel: int = METRONOME_CHANNEL,
                           note: int = METRONOME_NOTE,
                           velocity: int = METRONOME_VELOCITY,
                           duration: float = METRONOME_DURATION):
    """
    Plays metronome clicks using FluidSynth for better sound quality.
    
    Args:
        start_time: Lambda function returning the start time (or None if not yet set)
        bpm: Beats per minute
        beats_per_chord: Number of beats per chord
        max_sequence_length: Maximum number of chords in sequence
        synth: FluidSynth instance (from init_metronome)
        is_running_flag: Lambda function returning running state
        empty_bars_count: Number of empty bars before chords start
        channel: MIDI channel for metronome
        note: MIDI note number for click
        velocity: Base velocity for clicks
        duration: Click duration in seconds
    """
    
    if not synth:
        print("[METRONOME ERROR] Synth not initialized")
        return
    
    beat_duration = 60.0 / bpm  # Duration of one beat in seconds
    
    # Wait for start time to be set from main thread
    while start_time() is None and is_running_flag():
        time.sleep(0.01)
    
    if not is_running_flag():
        return
    
    # Get the actual start_time value by calling the lambda
    start_time_value = start_time()
    
    # Calculate total beats: empty bars + chord sequence
    delay_beats = int(empty_bars_count * beats_per_chord)
    total_beats = delay_beats + int(max_sequence_length * beats_per_chord)
    
    beat_count = 0
    while is_running_flag() and beat_count < total_beats:

        # Calculate when the next beat should occur
        beat_time = start_time_value + (beat_count * beat_duration)
        current_time = time.time()
        
        # Sleep until the next beat time
        wait_time = beat_time - current_time
        if wait_time > 0:
            time.sleep(wait_time)
        
        # Accent first beat of each measure
        click_velocity = velocity + 20 if beat_count % beats_per_chord == 0 else velocity
        
        # Play click using synth
        try:
            synth.noteon(channel, note, click_velocity)
            time.sleep(duration)
            synth.noteoff(channel, note)
            
        except Exception as e:
            print(f"[METRONOME ERROR] Playback error: {e}")
        
        beat_count += 1
    
    print("[METRONOME] Playback complete")

