import mido
import time

# Generates a MIDI file for a given chord sequence
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
        abs_time += int(chord.duration_beats * ticks_per_beat)
        
    midi_file.save(filename)
    print("File MIDI saved:", filename, "with BPM:", bpm)
    return filename

# Play chord sequence live on MIDI output port   
def play_chord_sequence_live(chord_sequence, output_port_name):

    with mido.open_output(output_port_name) as outport:
        start_time = time.time()
        absolute_time = 0.0  # continuous time relative to start_time
        
        for i, chord in enumerate(chord_sequence):
            
            print(f"Playing chord {i+1}/{len(chord_sequence)}: {chord}")
            
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

        print(f"Playback finished on port: {output_port_name}")