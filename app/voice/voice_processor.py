"""
Voice processing module for speaker verification and enrollment.
Based on Resemblyzer embeddings and cosine similarity.
"""
import numpy as np
from pathlib import Path
import logging

try:
    from resemblyzer import VoiceEncoder, preprocess_wav
    import soundfile as sf
    HAS_RESEMBLYZER = True
except ImportError:
    HAS_RESEMBLYZER = False

logger = logging.getLogger(__name__)


class VoiceProcessor:
    """
    Handle voice enrollment and verification using Resemblyzer embeddings.
    """
    
    def __init__(self, sample_rate: int = 16000):
        """
        Initialize voice processor.
        
        Args:
            sample_rate: Audio sample rate in Hz (default 16000)
        """
        if not HAS_RESEMBLYZER:
            raise ImportError(
                "Resemblyzer not installed. Install with: pip install resemblyzer"
            )
        
        self.sample_rate = sample_rate
        self.encoder = VoiceEncoder()
        logger.info("VoiceProcessor initialized with Resemblyzer")
    
    def create_embedding(self, audio_path: str) -> np.ndarray:
        """
        Generate voice embedding from audio file.
        
        Args:
            audio_path: Path to audio file (WAV, MP3, etc.)
            
        Returns:
            np.ndarray: Voice embedding vector (256 dimensions)
        """
        try:
            # Load audio file
            audio, sr = sf.read(audio_path)
            
            # Convert stereo to mono if needed
            if len(audio.shape) > 1:
                audio = np.mean(audio, axis=1)
            
            # Resample if needed (Resemblyzer expects 16kHz)
            if sr != self.sample_rate:
                import librosa
                audio = librosa.resample(audio, orig_sr=sr, target_sr=self.sample_rate)
            
            # Preprocess and generate embedding
            wav_processed = preprocess_wav(audio, self.sample_rate)
            embedding = self.encoder.embed_utterance(wav_processed)
            
            logger.info(f"Created embedding from {audio_path}: shape={embedding.shape}")
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to create embedding: {e}")
            raise
    
    def compare_embeddings(
        self, 
        embedding1: np.ndarray, 
        embedding2: np.ndarray
    ) -> float:
        """
        Calculate cosine similarity between two embeddings.
        
        Args:
            embedding1: First voice embedding
            embedding2: Second voice embedding
            
        Returns:
            float: Similarity score between 0 and 1
        """
        try:
            # Normalize vectors
            norm1 = np.linalg.norm(embedding1)
            norm2 = np.linalg.norm(embedding2)
            
            if norm1 == 0 or norm2 == 0:
                logger.warning("Zero-norm embedding encountered")
                return 0.0
            
            # Cosine similarity
            similarity = float(np.dot(embedding1, embedding2) / (norm1 * norm2))
            
            # Clamp to [0, 1] range
            similarity = max(0.0, min(1.0, similarity))
            
            logger.debug(f"Similarity: {similarity:.3f}")
            return similarity
            
        except Exception as e:
            logger.error(f"Failed to compare embeddings: {e}")
            return 0.0
    
    def verify_speaker(
        self,
        test_audio_path: str,
        enrolled_embedding: np.ndarray,
        threshold: float = 0.85
    ) -> tuple[bool, float]:
        """
        Verify if test audio matches enrolled speaker.
        
        Args:
            test_audio_path: Path to test audio file
            enrolled_embedding: Previously enrolled voice embedding
            threshold: Similarity threshold for match (default 0.85)
            
        Returns:
            tuple[bool, float]: (is_match, similarity_score)
        """
        try:
            # Generate embedding from test audio
            test_embedding = self.create_embedding(test_audio_path)
            
            # Compare with enrolled embedding
            similarity = self.compare_embeddings(enrolled_embedding, test_embedding)
            
            # Determine if match
            is_match = similarity >= threshold
            
            logger.info(
                f"Verification: {'MATCH' if is_match else 'NO MATCH'} "
                f"(similarity={similarity:.3f}, threshold={threshold:.2f})"
            )
            
            return is_match, similarity
            
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return False, 0.0


# Singleton instance
_voice_processor: "Optional[VoiceProcessor]" = None


def get_voice_processor() -> "VoiceProcessor":
    """Get or create VoiceProcessor singleton instance."""
    global _voice_processor
    if _voice_processor is None:
        _voice_processor = VoiceProcessor()
    return _voice_processor

