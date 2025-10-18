# =============================================================================
# Main class for representing chords and generating MIDI messages
# =============================================================================

from mido import Message
from typing import List

# Static data
# Maps notes to MIDI numbers
NOTE_TO_MIDI_MAP = {
    'C': 0, 'C#': 1, 'Db': 1,
    'D': 2, 'D#': 3, 'Eb': 3,
    'E': 4, 'F': 5, 'F#': 6, 'Gb': 6,
    'G': 7, 'G#': 8, 'Ab': 8,
    'A': 9, 'A#': 10, 'Bb': 10,
    'B': 11
}

# Maps intervals strings to intervals numbers
INTERVALS_MAP = {
    'major': [0, 4, 7],        # Major Triad          <-> Triade Maggiore
    'minor': [0, 3, 7],        # Minor Triad          <-> Triade Minore
    '7': [0, 4, 7, 10],        # Dominant 7th         <-> Settima Dominante
    'minor7': [0, 3, 7, 10],   # Minor 7th            <-> Settima Minore
    'maj7': [0, 4, 7, 11],     # Major 7th            <-> Settima Maggiore
    'dim': [0, 3, 6],          # Diminished Triad     <-> Triade Diminuita
    'aug': [0, 4, 8],          # Augmented Triad      <-> Triade Aumentata
    'sus2': [0, 2, 7],         # Suspended 2nd        <-> Sospesa di Seconda
    'sus4': [0, 5, 7],         # Suspended 4th        <-> Sospesa di Quarta
    '6': [0, 4, 7, 9],         # Major 6th            <-> Sesta Maggiore
    'minor6': [0, 3, 7, 9],    # Minor 6th            <-> Sesta Minore
    '9': [0, 4, 7, 10, 14],    # Dominant 9th         <-> Nona Dominante
    'add9': [0, 4, 7, 14],     # Add 9th              <-> Aggiunta di Nona
    'dim7': [0, 3, 6, 9],      # Diminished 7th       <-> Settima Diminuita
    'half_dim7': [0, 3, 6, 10] # Half-Diminished 7th  <-> Settima Semi-Diminuita
}


class Chord:
    def __init__(self, root: str, chord_type: str = 'major', bpm: int = 120, beats_per_chord: float = 4.0, velocity: int = 80, channel: int = 0):
        """
        Chord class
        
        Args:
            root: Root note ('C', 'F#', Bb, ...)
            chord_type: Chord type ('major', 'minor', '7', etc.)
            bpm: Beats per minute
            beats_per_chord: Duration in beats (4.0 = one bar in 4/4)
            velocity: MIDI velocity (0-127)
            channel: MIDI channel (0-15)
        """
        self.root = root
        self.chord_type = chord_type
        self.bpm = bpm
        self.beats_per_chord = beats_per_chord
        self.velocity = velocity
        self.channel = channel
        
        # Timing calculations
        self.beat_duration = 60.0 / self.bpm
        self.duration_seconds = self.beats_per_chord * self.beat_duration
        
        # Generate MIDI notes
        self.midi_notes = self._generate_midi_notes()
        # Pre-compute MIDI messages for performance optimization
        self.midi_messages = self._generate_midi_messages()
      
        
    # Generates list of MIDI notes for the chord
    def _generate_midi_notes(self, octave: int = 4) -> List[int]:
        # MIDI value for root
        root_midi = octave * 12 + NOTE_TO_MIDI_MAP[self.root]
        # Get intervals by chord type, default = major
        intervals = INTERVALS_MAP.get(self.chord_type, INTERVALS_MAP['major'])
        
        return [root_midi + interval for interval in intervals]

    # Pre-generates MIDI messages for performance optimization using relative timing (start_time=0)
    def _generate_midi_messages(self) -> List[tuple]:
        
        messages = []
        
        for note in self.midi_notes:
            # Note ON message at start
            messages.append((0.0, Message('note_on', channel=self.channel, note=note, velocity=self.velocity)))
            
            # Note OFF message at end of duration
            messages.append((self.duration_seconds, Message('note_off', channel=self.channel, note=note, velocity=0)))
            
        return sorted(messages, key=lambda x: x[0])  # Sort by time
    
    # Update BPM and thus beats and bars - regenerate messages if timing changes
    def update_timing(self, new_bpm: int):
        self.bpm = new_bpm
        self.beat_duration = 60.0 / new_bpm
        self.duration_seconds = self.beats_per_chord * self.beat_duration
        # Regenerate MIDI events with new timing
        self.midi_messages = self._generate_midi_messages()
    
    def __str__(self):
        return f"{self.root}{self.chord_type} ({self.beats_per_chord} beats @ {self.bpm} BPM)"
    
    
# Testing audio playback   
if __name__ == '__main__':
    from utils import save_chords_to_midi, play_chord_sequence_live
    
    bpm = 80
    progression = [
        Chord('A', bpm=bpm), 
        Chord('F#', 'minor', bpm=bpm), 
        Chord('B', 'minor', bpm=bpm), 
        Chord('E', '7', bpm=bpm)
    ]
    print("Testing chord progression")
    save_chords_to_midi(progression, 'test_progression.mid', bpm=bpm)

    play_chord_sequence_live(progression, 'Driver IAC Bus 1')