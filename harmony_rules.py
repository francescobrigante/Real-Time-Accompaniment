
import random
from typing import List
from utils import roman_to_chord, progression_to_chords, compact_chord


# Static data
CHROMATIC_NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# Transition rules with weights (probabilities)
TRANSITION_RULES = {
    'I': [('vi', 0.3), ('IV', 0.25), ('V', 0.2), ('ii', 0.15), ('iii', 0.1)],
    'ii': [('V', 0.6), ('vii°', 0.2), ('IV', 0.15), ('I', 0.05)],
    'iii': [('vi', 0.4), ('IV', 0.3), ('ii', 0.2), ('V', 0.1)],
    'IV': [('I', 0.3), ('V', 0.25), ('ii', 0.2), ('vi', 0.15), ('iii', 0.1)],
    'V': [('I', 0.5), ('vi', 0.3), ('IV', 0.15), ('ii', 0.05)],  # V -> I very strong
    'vi': [('IV', 0.35), ('ii', 0.25), ('V', 0.2), ('iii', 0.15), ('I', 0.05)],
    'vii°': [('I', 0.7), ('iii', 0.2), ('V', 0.1)]
}

# TODO: what if we start with C7 or Cm?
class HarmonyRules:
    def __init__(self, key: str = 'C'):
        
        try:
            # tonic key string
            self.key = key
            # its index in CHROMATIC_NOTES
            self.key_index = CHROMATIC_NOTES.index(key)
            
        except ValueError:
            print(f"[EXCEPTION] Key '{key}' not recognized. Defaulting to 'C'.")
            self.key = 'C'
            self.key_index = 0
    
    
    # Predicts next degree based on rules
    def predict_next_degree(self, current_degree: str, method: str = 'deterministic') -> str:
        """
        Args:
            current_degree: Current degree ('I', 'V', etc.)
            method: 'deterministic' (always the most likely) or 'sample' (randomly based on weights)
        """
        if current_degree not in TRANSITION_RULES:
            return 'I'  # Fallback
            
        possible_transitions = TRANSITION_RULES[current_degree]

        if method == 'deterministic':
            # Choose most probable
            return max(possible_transitions, key=lambda x: x[1])[0]
        
        elif method == 'sample':
            # Sample based on weights
            degrees, weights = zip(*possible_transitions)
            return random.choices(degrees, weights=weights)[0]
    
    
    # Generates a chord progression given length and starting degree
    def generate_progression(self, length: int, starting_degree: str = 'I', method: str = 'deterministic') -> List[str]:

        progression = [starting_degree]
        current = starting_degree
        
        for _ in range(length - 1):
            next_degree = self.predict_next_degree(current, method)
            progression.append(next_degree)
            current = next_degree
            
        return progression
    
    
    # Given a chord progression, returns tuple (next_chord, probability distribution)
    def get_next_chord_distribution(self, chord_progression: List[str], return_roman: bool = False) -> tuple:
        
        if not chord_progression:
            return None, {}
        
        last_chord = chord_progression[-1]
        
        if last_chord not in TRANSITION_RULES:
            return None, {}
        
        # for now it uses a simple logic based on last chord only<---------
        next_chord_candidates = TRANSITION_RULES[last_chord]
        total_weight = sum(weight for _, weight in next_chord_candidates)
        probabilities_roman = {chord: weight / total_weight for chord, weight in next_chord_candidates}
        
        # Sample next chord based on probabilities (work with romans first)
        next_roman = random.choices(list(probabilities_roman.keys()), weights=list(probabilities_roman.values()))[0]
        
        if return_roman:
            return next_roman, probabilities_roman
        else:
            # Convert to (root, chord_type) tuple and string distribution
            root, chord_type = roman_to_chord(self.key, next_roman)
            
            # Convert probabilities to string notation
            probabilities_string = {}
            for roman, prob in probabilities_roman.items():
                chord_root, chord_quality = roman_to_chord(self.key, roman)
                chord_string = compact_chord(chord_root, chord_quality)
                probabilities_string[chord_string] = prob
            
            return (root, chord_type), probabilities_string


if __name__ == "__main__":
    
    key = 'C'
    harmony = HarmonyRules(key)
    
    print("\n====== Next chord prediction:")
    test_progression = ['I', 'vi', 'ii', 'V']
    print(f"Given progression: {' - '.join(test_progression)}")
    next_chord, distribution = harmony.get_next_chord_distribution(test_progression)
    print(f"Predicted next chord: {next_chord}")
    # creating chord object
    from chord import Chord
    next_chord_obj = Chord(next_chord[0], next_chord[1], bpm=80)
    print(f"Chord object: {next_chord_obj}")
    print("Probability distribution for next chords:")
    for chord, prob in distribution.items():
        print(f"\t{chord}: {prob:.2f}")