# ==================================================================================================================
# Note-Based Harmony Prediction Engine
# Analyzes played notes to predict next chord using functional harmony theory (T-S-D roles)
# Uses exponential weighting to prioritize recent notes over older ones
# Steps:
#   1. Classify each note by harmonic role (Tonic, Subdominant, Dominant)
#   2. Compute weighted scores for each role (recent notes = higher weight)
#   3. Determine current dominant role from scores
#   4. Predict next role using static transition matrix
#   5. Select random chord from predicted role's chord pool
# ==================================================================================================================

import random
from typing import List, Tuple, Dict, Optional
from math import exp

from utils import CHROMATIC_NOTES, roman_to_chord, chord_to_roman, compact_chord

# =============================== Static Data ===========================================

# Maps each note degree (0-11) to harmonic role
DEGREE_TO_ROLE = {
    0: 'T',   # 1st - Tonic
    1: 'S',   # b2 - Subdominant
    2: 'T',   # 2nd - Tonic
    3: 'S',   # b3 - Subdominant
    4: 'T',   # 3rd - Tonic
    5: 'S',   # 4th - Subdominant
    6: 'D',   # b5/#4 - Dominant
    7: 'D',   # 5th - Dominant
    8: 'D',   # b6/#5 - Dominant
    9: 'T',   # 6th - Tonic
    10: 'D',  # b7 - Dominant
    11: 'D'   # 7th (major)
}

# TODO: add more chords
# Chord classification by role
TONIC_CHORDS = ['I', 'vi', 'iii']
# SUBDOMINANT_CHORDS = ['IV', 'ii', 'iv', 'II']
SUBDOMINANT_CHORDS = ['IV', 'ii']
# DOMINANT_CHORDS = ['V', 'vii°', 'III']
DOMINANT_CHORDS = ['V', 'vii°']

# All chord options grouped by role
CHORD_ROLES = {
    'T': TONIC_CHORDS,
    'S': SUBDOMINANT_CHORDS,
    'D': DOMINANT_CHORDS
}

# Role transition rules with weights (probabilities)
ROLE_TRANSITIONS = {
    'T': [('S', 0.45), ('D', 0.35), ('T', 0.20)],  # From Tonic: often to Subdominant or Dominant
    'S': [('D', 0.50), ('T', 0.30), ('S', 0.20)],  # From Subdominant: often to Dominant, sometimes back to Tonic
    'D': [('T', 0.65), ('S', 0.25), ('D', 0.10)]   # From Dominant: strong resolution to Tonic, rarely stays on Dominant
}


# =============================== Class Definition ===========================================

# Note-based Harmony Prediction Engine
# Based on roles T (tonic), S (subdominant), D (dominant) for prediction
# Uses exponential weighting for recency of notes played
class NotesHarmonyRules:
    
    # TODO: handle key type 
    def __init__(self, key: str = 'C'):
        try:
            self.key = key
            self.key_index = CHROMATIC_NOTES.index(key)
            
        except ValueError:
            print(f"[WARNING] Key '{key}' not recognized. Defaulting to 'C'.")
            self.key = 'C'
            self.key_index = 0
    
    
    # Classify a single MIDI note as T (tonic), S (subdominant), or D (dominant)
    def _classify_note(self, midi_note: int) -> str:
        """
        Args:
            midi_note: MIDI note number (0-127)
            
        Returns:
            'T', 'S', or 'D'
        """
        # Get note relative to key (scale degree 0-11)
        note_in_scale = midi_note % 12
        degree = (note_in_scale - self.key_index) % 12
        
        return DEGREE_TO_ROLE[degree]
    
    
    def _compute_exponential_weights(self, window_size: int) -> List[float]:
        """
        Generate exponential weights for note window: recent notes get higher weight.
        Uses exponential decay formula: weight[i] = exp(alpha * i)
        where i goes from 0 (oldest) to window_size-1 (newest)
        
        Args:
            window_size: Number of notes in window
            
        Returns:
            List of weights (normalized to sum to 1.0)
        """
        if window_size == 0:
            return []
        
        if window_size == 1:
            return [1.0]
        
        # Exponential growth factor: higher = more emphasis on recent notes and less on old ones
        # e.g. alpha=0.3 for 8 notes -> oldest≈0.05, newest≈0.25
        alpha = 0.2
        
        weights = []
        for i in range(window_size):
            weight = exp(alpha * i)  # e^(alpha * i)
            weights.append(weight)
        
        # Normalize
        total = sum(weights)
        normalized = [w / total for w in weights]
        
        return normalized
    
    
    # Given window of notes, compute weighted scores for T, S, D, giving more weight to recent notes
    def _compute_window_scores(self, note_window: List[Tuple[int, float]]) -> Dict[str, float]:
        """
        Returns:
            Dictionary {'T': score, 'S': score, 'D': score}
        """
        scores = {'T': 0.0, 'S': 0.0, 'D': 0.0}
        
        if not note_window:
            return scores
        
        # Get exponential weights
        weights = self._compute_exponential_weights(len(note_window))
        
        # Classify each note and add weighted score
        # TODO: use duration as well?
        for i, (midi_note, duration) in enumerate(note_window):
            role = self._classify_note(midi_note)
            scores[role] += weights[i]
        
        return scores
    
    
    
    def predict_with_scores(self, note_window: List[Tuple[int, float]]) -> Tuple[Optional[Tuple[str, str]], Dict[str, float], str, str]:
        """
        Given a window of played notes, predicts the next chord based on T, S, D roles.
        Steps:
            1. Compute role scores from note window to understand how much T, S, D are present
            2. Compute next role using transition matrix defined statically
            3. Use next role to pick a chord belonging to that role
        
        Args:
            note_window: List of (midi_note, duration_beats) tuples
            
        Returns:
            Tuple of:
                - Predicted chord as (root, chord_type) or None
                - Role scores dictionary {'T': score, 'S': score, 'D': score} for debugging/visualization
                - Current max role detected from notes ('T', 'S', or 'D') for debugging/visualization since it could be deterministic or sampled
                - Next Role chosen by transition matrix ('T', 'S', or 'D') for debugging/visualization since it could be deterministic or sampled
        """
        if not note_window:
            return None, {'T': 0.0, 'S': 0.0, 'D': 0.0}, None, None
        
        # ----= Step 1: Compute role scores from note window to understand how much T, S, D are present
        
        window_scores = self._compute_window_scores(note_window)
        
        if max(window_scores.values()) == 0:
            return None, window_scores, None, None
        
        # Deterministic choice: get role with highest score
        max_window_role = max(window_scores, key=window_scores.get)
        
        # Weighted sampling
        # max_window_role = random.choices(list(window_scores.keys()), weights=list(window_scores.values()))[0]
        
        # ----= Step 2: Compute next role using transition matrix defined statically
        
        # Check if role has transitions
        if max_window_role in ROLE_TRANSITIONS:
            
            transitions = ROLE_TRANSITIONS[max_window_role]
            roles, weights = zip(*transitions)
            
            # Deterministic choice: get next role with highest probability defined STATICALLY
            next_role = max(transitions, key=lambda x: x[1])[0]
            
            # Weighted sampling among possible next roles
            # next_role = random.choices(roles, weights=weights)[0]
            
        else:
            print("[WARNING] No transitions defined for Role '{max_window_role}'. Defaulting to 'T'.")
            next_role = 'T'
            
        # ----= Step 3: Use next role to pick a chord
        
        chord_pool = CHORD_ROLES[next_role]
        
        # SIMPLE LOGIC: random choice among chords of that role
        selected_roman = random.choice(chord_pool)
        
        root, chord_type = roman_to_chord(self.key, selected_roman)
        predicted_chord = (root, chord_type)
        
        return predicted_chord, window_scores, max_window_role, next_role
    
# ================================= Helper Functions =========================================

def get_chord_role(chord_tuple):
    """Helper to determine which Role a chord belongs to"""
    roman = chord_to_roman(key, chord_tuple[0], chord_tuple[1])
    for role, chords in CHORD_ROLES.items():
        if roman in chords:
            return role
    print(f"[WARNING] Chord '{chord_tuple}' not found in any role category.")
    return '?'


# ==================================== Test Block ============================================

if __name__ == "__main__":
    
    key = 'C'
    predictor = NotesHarmonyRules(key)

    # Test cases: (description, note_window)
    test_cases = [
        (
            "Test 1: Mixed sequence (T -> S -> D)",
            [
                (60, 1.0),  # C (T) - oldest
                (64, 1.0),  # E (T)
                (62, 1.0),  # D (S)
                (65, 1.0),  # F (S)
                (67, 1.5),  # G (D) - newest, highest weight
                (71, 1.5),  # B (D) - newest, highest weight
            ]
        ),
        (
            "Test 2: I chord (C major: C, E, G) -> should go to S or D",
            [(60, 1.0), (64, 1.0), (67, 1.0)]  # C, E, G
        ),
        (
            "Test 3: IV chord (F major: F, A, C) -> should often go to V or I",
            [(65, 1.0), (69, 1.0), (60, 1.0)]  # F, A, C
        ),
        (
            "Test 4: V chord (G major: G, B, D) -> should strongly resolve to I",
            [(67, 1.0), (71, 1.0), (62, 1.0)]  # G, B, D
        ),
        (
            "Test 5: ii chord (D minor: D, F, A) -> should go to V",
            [(62, 1.0), (65, 1.0), (69, 1.0)]  # D, F, A
        ),
        (
            "Test 6: vi chord (A minor: A, C, E) -> should go to IV or ii",
            [(69, 1.0), (60, 1.0), (64, 1.0)]  # A, C, E
        )
    ]
    
    # Run all tests
    for description, note_window in test_cases:
        print(f"\n\n====== {description}")
        predicted, scores, max_role, next_role = predictor.predict_with_scores(note_window)
        chord_role = get_chord_role(predicted)
        print(f"[INFO] Note window: {[(n, d) for n, d in note_window]}")
        print(f"[INFO] Window role scores: {scores}")
        print(f"[INFO] Chosen representative role: {max_role}")
        print(f"[INFO] Next Role predicted: {next_role}")
        print(f"[INFO] Next Predicted chord: {predicted} (belongs to {chord_role}) -> correct ✓" if chord_role == next_role 
              else f"[ERROR] Next Predicted chord: {predicted} (belongs to {chord_role}) -> MISMATCH ✗")
    
    # Test exponential weights for different window sizes
    print("\n\n====== Exponential Weights Test")
    for size in [4, 8, 12]:
        weights = predictor._compute_exponential_weights(size)
        print(f"\nWindow size {size}:")
        print(f"  Weights: {[f'{w:.4f}' for w in weights]}")
        print(f"  Sum: {sum(weights):.6f}")
        print(f"  Ratio (newest/oldest): {weights[-1]/weights[0]:.2f}x")