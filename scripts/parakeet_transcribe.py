#!/usr/bin/env python3
"""
Parakeet TDT V2 INT8 Transcription Script
Based on transcribe-rs implementation: https://github.com/cjpais/transcribe-rs
"""

import argparse
import json
import time
import re
import numpy as np
from pathlib import Path

import onnxruntime as ort
import librosa


class ParakeetTDT:
    """Parakeet TDT V2 INT8 transcriber using ONNX Runtime."""
    
    # Constants from transcribe-rs
    SUBSAMPLING_FACTOR = 8
    WINDOW_SIZE = 0.01
    MAX_TOKENS_PER_STEP = 10
    
    def __init__(self, model_dir: str):
        model_dir = Path(model_dir)
        
        # Load config
        config_path = model_dir / "config.json"
        with open(config_path) as f:
            self.config = json.load(f)
        
        # Load vocabulary
        self.vocab, self.blank_idx = self._load_vocab(model_dir / "vocab.txt")
        self.vocab_size = len(self.vocab)
        print(f"Loaded vocabulary: {self.vocab_size} tokens, blank_idx={self.blank_idx}")
        
        self.sample_rate = 16000
        
        # Create ONNX sessions
        sess_options = ort.SessionOptions()
        sess_options.intra_op_num_threads = 4
        sess_options.inter_op_num_threads = 4
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        
        print(f"Loading preprocessor...")
        start = time.time()
        self.preprocessor = ort.InferenceSession(
            str(model_dir / "nemo128.onnx"), sess_options)
        print(f"Preprocessor loaded in {time.time() - start:.2f}s")
        
        print(f"Loading encoder...")
        start = time.time()
        self.encoder = ort.InferenceSession(
            str(model_dir / "encoder-model.int8.onnx"), sess_options)
        print(f"Encoder loaded in {time.time() - start:.2f}s")
        
        print(f"Loading decoder...")
        start = time.time()
        self.decoder = ort.InferenceSession(
            str(model_dir / "decoder_joint-model.int8.onnx"), sess_options)
        print(f"Decoder loaded in {time.time() - start:.2f}s")
    
    def _load_vocab(self, vocab_path: Path) -> tuple:
        """Load vocabulary from vocab.txt file."""
        vocab = {}
        blank_idx = 0
        
        with open(vocab_path) as f:
            for line in f:
                parts = line.rstrip().split(' ')
                if len(parts) >= 2:
                    token = parts[0]
                    # Replace SentencePiece space marker with actual space
                    token = token.replace('\u2581', ' ')
                    idx = int(parts[1])
                    vocab[idx] = token
                    if token.strip() == '<blk>':
                        blank_idx = idx
        
        return vocab, blank_idx
    
    def load_audio(self, audio_path: str) -> np.ndarray:
        """Load audio file and convert to 16kHz mono float32."""
        audio, sr = librosa.load(audio_path, sr=self.sample_rate, mono=True)
        return audio.astype(np.float32)
    
    def transcribe(self, audio: np.ndarray) -> tuple:
        """Transcribe audio using Parakeet TDT model."""
        # Prepare audio
        waveforms = audio.reshape(1, -1)
        waveforms_lens = np.array([audio.shape[0]], dtype=np.int64)
        
        # Preprocess (mel spectrogram)
        start = time.time()
        prep_out = self.preprocessor.run(
            None,
            {'waveforms': waveforms, 'waveforms_lens': waveforms_lens}
        )
        features, features_lens = prep_out[0], prep_out[1]
        print(f"Preprocessor: {time.time() - start:.3f}s, features shape: {features.shape}")
        
        # Encode
        start = time.time()
        enc_out = self.encoder.run(
            None,
            {'audio_signal': features, 'length': features_lens}
        )
        encoder_out = enc_out[0]  # [1, 1024, time]
        encoder_out_lens = enc_out[1]
        # Transpose to [1, time, 1024] like transcribe-rs
        encoder_out = encoder_out.transpose(0, 2, 1)
        print(f"Encoder: {time.time() - start:.3f}s, encoded shape: {encoder_out.shape}")
        
        # Decode
        start = time.time()
        tokens, timestamps = self._decode_sequence(
            encoder_out[0], int(encoder_out_lens[0]))
        decode_time = time.time() - start
        print(f"Decode: {decode_time:.3f}s")
        
        # Convert to text
        text = self._decode_tokens(tokens)
        
        return text, tokens, timestamps
    
    def _create_decoder_state(self) -> tuple:
        """Create initial decoder state (LSTM hidden states)."""
        # Shape: [2, 1, 640] for batch_size=1
        state1 = np.zeros((2, 1, 640), dtype=np.float32)
        state2 = np.zeros((2, 1, 640), dtype=np.float32)
        return state1, state2
    
    def _decode_step(self, prev_tokens: list, prev_state: tuple, 
                     encoder_step: np.ndarray) -> tuple:
        """Run one decoder step.
        
        Args:
            prev_tokens: Previously emitted tokens
            prev_state: Previous decoder state (state1, state2)
            encoder_step: Encoder output for current frame [1024]
        
        Returns:
            (logits, new_state)
        """
        # Get last token or blank if empty
        target_token = prev_tokens[-1] if prev_tokens else self.blank_idx
        
        # Prepare inputs
        # encoder_outputs: [1, 1024, 1] (batch, dim, time) - matches ONNX input shape
        encoder_outputs = encoder_step.reshape(1, -1, 1).astype(np.float32)
        targets = np.array([[target_token]], dtype=np.int32)
        target_length = np.array([1], dtype=np.int32)  # Must be int32 for this model
        state1, state2 = prev_state
        
        outputs = self.decoder.run(
            None,
            {
                'encoder_outputs': encoder_outputs,
                'targets': targets,
                'target_length': target_length,
                'input_states_1': state1,
                'input_states_2': state2,
            }
        )
        
        logits = outputs[0]  # [1, 1, vocab_size + duration]
        new_state1 = outputs[2]
        new_state2 = outputs[3]
        
        return logits[0, 0], (new_state1, new_state2)
    
    def _decode_sequence(self, encodings: np.ndarray, 
                         encodings_len: int) -> tuple:
        """Decode encoded sequence using greedy algorithm.
        
        Implements TDT decoding with MAX_TOKENS_PER_STEP limit.
        """
        prev_state = self._create_decoder_state()
        tokens = []
        timestamps = []
        
        t = 0
        emitted_tokens = 0
        
        while t < encodings_len:
            encoder_step = encodings[t]  # [1024]
            logits, new_state = self._decode_step(tokens, prev_state, encoder_step)
            
            # For TDT: split into vocab logits and duration logits
            if len(logits) > self.vocab_size:
                vocab_logits = logits[:self.vocab_size]
                # Duration logits not used in basic greedy decoding
            else:
                vocab_logits = logits
            
            # Get argmax token
            token = int(np.argmax(vocab_logits))
            
            # Process non-blank token
            if token != self.blank_idx:
                prev_state = new_state
                tokens.append(token)
                timestamps.append(t)
                emitted_tokens += 1
            
            # Advance frame on blank OR after max tokens per step
            if token == self.blank_idx or emitted_tokens == self.MAX_TOKENS_PER_STEP:
                t += 1
                emitted_tokens = 0
        
        return tokens, timestamps
    
    def _decode_tokens(self, ids: list) -> str:
        """Convert token IDs to text."""
        tokens = []
        for token_id in ids:
            if token_id < len(self.vocab):
                token = self.vocab[token_id]
                # SentencePiece uses '▁' (U+2581) to mark word starts
                # Replace with space for proper word separation
                if token.startswith(' '):
                    tokens.append(token)  # Already has leading space
                else:
                    tokens.append(token)
        
        # Join all tokens - spaces are already embedded
        text = ''.join(tokens)
        
        # Clean up multiple spaces
        text = re.sub(r' +', ' ', text)
        
        return text.strip()


def main():
    parser = argparse.ArgumentParser(description='Parakeet TDT V2 INT8 Transcription')
    parser.add_argument('audio', help='Path to audio file')
    parser.add_argument('--model', default='~/.openclaw/models/parakeet-tdt-0.6b-v2-int8',
                       help='Path to model directory')
    args = parser.parse_args()
    
    model_path = Path(args.model).expanduser()
    audio_path = args.audio
    
    print(f"Loading model from {model_path}...")
    transcriber = ParakeetTDT(model_path)
    
    print(f"\nLoading audio from {audio_path}...")
    audio = transcriber.load_audio(audio_path)
    duration = len(audio) / transcriber.sample_rate
    print(f"Audio duration: {duration:.2f}s")
    
    print("\nTranscribing...")
    start = time.time()
    text, tokens, timestamps = transcriber.transcribe(audio)
    total_time = time.time() - start
    
    print(f"\n{'='*60}")
    print(f"TRANSCRIPTION:")
    print(f"{text}")
    print(f"{'='*60}")
    print(f"\nPerformance:")
    print(f"  Total time: {total_time:.3f}s")
    print(f"  Real-time factor: {total_time / duration:.2f}x")


if __name__ == '__main__':
    main()
