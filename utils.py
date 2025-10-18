import mido
import time
from typing import List


# Static data
CHROMATIC_NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
MAJOR_SCALE_INTERVALS = [0, 2, 4, 5, 7, 9, 11]  # W-W-H-W-W-W-H
CHORD_QUALITIES = ['major', 'minor', 'minor', 'major', 'major', 'minor', 'dim']
ROMAN_NUMERALS = ['I', 'ii', 'iii', 'IV', 'V', 'vi', 'vii°']
ROMAN_TO_INDEX = { 'I': 0, 'ii': 1, 'iii': 2, 'IV': 3, 'V': 4, 'vi': 5, 'vii°': 6}


# ================================= Chord Handling Utilities =======================================

# Converts a roman numeral to (root_note, chord_type) given a MAJOR tonic key as string TODO: support minor keys, 7, etc. with harmonizer
def roman_to_chord(tonic: str, roman_numeral: str) -> tuple:

    if roman_numeral not in ROMAN_TO_INDEX:
        return (tonic, 'major')  # Fallback to tonic
        
    # Direct array access using index
    degree_index = ROMAN_TO_INDEX[roman_numeral]
    interval = MAJOR_SCALE_INTERVALS[degree_index]
    chord_quality = CHORD_QUALITIES[degree_index]
        
    # Calculate note index with key offset
    tonic_index = CHROMATIC_NOTES.index(tonic)
    note_index = (tonic_index + interval) % 12
    note_name = CHROMATIC_NOTES[note_index]
        
    return (note_name, chord_quality)

# Converts a chord (root, chord_type) back to roman numeral given a tonic key
# TODO: possibili check di errori nella pipeline se prediciamo IVmaj7 che non appartiene alla lista, check dove viene usata la function
def chord_to_roman(tonic: str, target_root: str, target_type: str) -> str:
    """
    Examples:
        chord_to_roman('C', 'C', 'major') -> 'I'
        chord_to_roman('C', 'A', 'minor') -> 'vi'  
        chord_to_roman('C', 'C', '7') -> 'I7'
        chord_to_roman('C', 'F', 'major') -> 'IV'
    """
    
    try:
        tonic_index = CHROMATIC_NOTES.index(tonic)
        target_index = CHROMATIC_NOTES.index(target_root)
    except ValueError:
        print(f"[EXCEPTION] chord_to_roman: Unrecognized note in '{tonic}' or '{target_root}'. Fallbacking to 'I'.")
        return 'I'  # Fallback if invalid notes
    
    # Calculate interval (semitones from tonic)
    interval = (target_index - tonic_index) % 12
    
    # Find degree using direct array lookup
    try:
        degree_index = MAJOR_SCALE_INTERVALS.index(interval)
        base_roman = ROMAN_NUMERALS[degree_index]
        expected_quality = CHORD_QUALITIES[degree_index]
    except ValueError:
        return 'I'  # Fallback if interval not in major scale
    
    # Handle chord type casing and extensions
    
    if target_type == 'major':
        # Major chords: use uppercase roman
        if expected_quality == 'major':
            return base_roman  # Natural major degree
        else:
            # Borrowed major chord 
            return base_roman.upper().replace('°', '')
    
    elif target_type == 'minor':
        # Minor chords: use lowercase roman
        if expected_quality == 'minor':
            return base_roman  # Natural minor degree
        else:
            # Borrowed minor chord
            return base_roman.lower().replace('°', '')
    
    elif target_type == 'dim':
        # Diminished: use lowercase with °
        return base_roman.lower().replace('°', '') + '°'
    
    elif target_type == '7':
        # Dominant 7th: preserve case, add 7
        return base_roman + '7'
    
    elif target_type == 'maj7':
        # Major 7th: uppercase, add maj7
        return base_roman.upper().replace('°', '') + 'maj7'
    
    elif target_type == 'm7':
        # Minor 7th: lowercase, add 7
        return base_roman.lower().replace('°', '') + '7'
    
    else:
        # Other types: preserve natural case, add extension
        return base_roman + target_type.replace('major', '').replace('minor', 'm')
    
    
    
# Converts list of roman numerals to list of (root, chord_type) tuples
def progression_to_chords(tonic: str, progression: List[str]) -> List[tuple]:
    return [roman_to_chord(tonic, numeral) for numeral in progression]
    
# Converts a (root, chord_type) tuple to compact notation chord name
def compact_chord(root: str, chord_type: str) -> str:
    """
    Examples: compact_chord('C', 'major') -> 'C', compact_chord('A', 'minor') -> 'Am'
    """
    # Start with root note
    compact = root
        
    # Process chord_type: remove 'major', replace 'minor' with 'm', replace 'dim' with '°'
    if chord_type != 'major':
        chord_suffix = chord_type.replace('minor', 'm').replace('dim', '°')
        compact += chord_suffix
            
    return compact

# Converts a compact chord name back to (root, chord_type) tuple
def parse_compact_chord(chord_string: str) -> tuple:

    if chord_string.endswith('m') and not chord_string.endswith('maj'):
        return chord_string[:-1], 'minor'
    elif chord_string.endswith('°'):
        return chord_string[:-1], 'dim'
    else:
        return chord_string, 'major'




# ================================= Midi Handling Functions =======================================

# Generates a MIDI file for a given chord sequence and BPM
def save_chords_to_midi(chord_sequence, filename='output.mid', bpm=120):
    midi_file = mido.MidiFile()
    track = mido.MidiTrack()
    midi_file.tracks.append(track)
    
    # Adding BPM meta information
    # Formula: microsec_per_beat = 60_000_000 / bpm
    microsec_per_beat = int(60000000 / bpm)
    tempo_msg = mido.MetaMessage('set_tempo', tempo=microsec_per_beat, time=0)
    track.append(tempo_msg)
        
    abs_time = 0
    ticks_per_beat = midi_file.ticks_per_beat
        
    for chord in chord_sequence:
        # Use pre-computed messages directly, just adjust timing for MIDI file 
        for relative_time, msg in chord.midi_messages:
            # converting seconds to ticks
            ticks = int(relative_time * ticks_per_beat / chord.beat_duration)
            msg.time = max(0, ticks - abs_time)
            abs_time = ticks                
            track.append(msg)
            
        # increment absolute time for next chord (in ticks)
        abs_time += int(chord.beats_per_chord * ticks_per_beat)
        
    midi_file.save(filename)
    print("File MIDI saved:", filename, "with BPM:", bpm)
    return filename

# Play chord sequence live on MIDI output port   
def play_chord_sequence(chord_sequence, output_port_name):

    with mido.open_output(output_port_name) as outport:
        start_time = time.time()
        absolute_time = 0.0  # continuous time relative to start_time
        
        for i, chord in enumerate(chord_sequence):
            
            print(f"[🎵PLAYING🎵] Playing chord {i+1}/{len(chord_sequence)}: {chord}")
            
            # Use pre-computed messages
            for relative_time, msg in chord.midi_messages:
                adjusted_time = absolute_time + relative_time
                real_now = time.time()
                wait = (start_time + adjusted_time) - real_now
                if wait > 0:
                    time.sleep(wait)
                outport.send(msg)
                
            # Update absolute time for next chord (using chord duration)
            absolute_time += chord.duration_seconds

        print(f"[🎵PLAYING🎵] Playback finished on port: {output_port_name}")

# Play a single chord live on MIDI output port with proper timing
def play_chord(chord, output_port_name):
    """
    Play a single chord with proper timing management.
    Uses the same timing logic as play_chord_sequence for consistency.
    """
    try:
        with mido.open_output(output_port_name) as outport:
            print(f"[🎵PLAYING🎵] Playing chord: {chord}")
            
            start_time = time.time()
            
            # Send pre-computed MIDI messages with proper timing
            for relative_time, msg in chord.midi_messages:
                # Calculate when this message should be sent
                target_time = start_time + relative_time
                current_time = time.time()
                wait_time = target_time - current_time
                
                # Wait until it's time to send the message
                if wait_time > 0:
                    time.sleep(wait_time)
                    
                outport.send(msg)
                
    except Exception as e:
        print(f"MIDI playback error: {e}")
        print(f"Would play: {chord}")