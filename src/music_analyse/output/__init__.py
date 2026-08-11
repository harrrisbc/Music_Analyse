"""Output package."""

from music_analyse.output.midi_out import MidiOutput, list_midi_output_names
from music_analyse.output.osc_out import OscOutput

__all__ = ["MidiOutput", "OscOutput", "list_midi_output_names"]
