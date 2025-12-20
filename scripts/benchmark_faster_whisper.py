#!/usr/bin/env python3
"""Benchmark script to compare OpenAI Whisper vs faster-whisper transcription performance.

This script measures:
- Model load time
- Transcription time per file
- Realtime factor (transcription time / audio duration)
- Transcript similarity between the two methods

faster-whisper uses CTranslate2, providing up to 4x faster inference than OpenAI Whisper.

Usage:
    python scripts/benchmark_faster_whisper.py --audio-file /path/to/audio.mp3
    python scripts/benchmark_faster_whisper.py --audio-dir /path/to/podcasts/ --limit 5
    python scripts/benchmark_faster_whisper.py --audio-file audio.mp3 --models large-v3,medium
"""

import argparse
import gc
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def check_dependencies() -> None:
    """Check that required dependencies are installed."""
    missing = []

    try:
        import whisper  # Used to check if installed
    except ImportError:
        missing.append("openai-whisper")

    try:
        from faster_whisper import WhisperModel  # Used to check if installed
    except ImportError:
        missing.append("faster-whisper")

    if missing:
        print("Missing required dependencies:", ", ".join(missing))
        print()
        print("To install dependencies, run:")
        print("  uv sync --group encoding --extra benchmark")
        print("  # or")
        print("  pip install openai-whisper faster-whisper")
        sys.exit(1)


@dataclass
class TranscriptionResult:
    """Result of a single transcription."""

    transcript: str
    transcription_time: float
    word_count: int


@dataclass
class BenchmarkResult:
    """Result of benchmarking a single file."""

    file: str
    duration_seconds: float
    whisper: Optional[dict] = None
    faster_whisper: Optional[dict] = None
    comparison: Optional[dict] = None


@dataclass
class BenchmarkReport:
    """Full benchmark report."""

    config: dict
    model_load_times: dict = field(default_factory=dict)
    results: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class TranscriptionBenchmark:
    """Benchmark whisper vs faster-whisper transcription."""

    def __init__(
        self,
        model_sizes: list[str],
        device: str = "cuda",
        compute_type: str = "float16",
    ):
        """Initialize benchmark.

        Args:
            model_sizes: List of model sizes to test (e.g., ["large-v3", "medium"])
            device: Device to use ("cuda" or "cpu")
            compute_type: Compute type for faster-whisper ("float16", "int8", etc.)
        """
        self.model_sizes = model_sizes
        self.device = device

        # CPU doesn't support float16 efficiently, use int8 instead
        if device == "cpu" and compute_type == "float16":
            logger.info("CPU device: switching compute_type from float16 to int8")
            compute_type = "int8"

        self.compute_type = compute_type

    def get_audio_duration(self, audio_path: str) -> float:
        """Get audio duration in seconds using ffprobe.

        Args:
            audio_path: Path to audio file.

        Returns:
            Duration in seconds.
        """
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    audio_path,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError) as e:
            logger.warning(f"Could not get duration for {audio_path}: {e}")
            return 0.0

    def load_whisper(self, model_size: str) -> tuple[Any, float]:
        """Load OpenAI Whisper model.

        Args:
            model_size: Model size (e.g., "large-v3", "medium", "small")

        Returns:
            Tuple of (model, load_time_seconds)
        """
        import whisper

        logger.info(f"Loading OpenAI Whisper model: {model_size}")
        start = time.perf_counter()
        model = whisper.load_model(model_size, device=self.device)
        load_time = time.perf_counter() - start
        logger.info(f"Whisper model loaded in {load_time:.2f}s")
        return model, load_time

    def load_faster_whisper(self, model_size: str) -> tuple[Any, float]:
        """Load faster-whisper model.

        Args:
            model_size: Model size (e.g., "large-v3", "medium", "small")

        Returns:
            Tuple of (model, load_time_seconds)
        """
        from faster_whisper import WhisperModel

        logger.info(f"Loading faster-whisper model: {model_size}")
        start = time.perf_counter()
        model = WhisperModel(
            model_size,
            device=self.device,
            compute_type=self.compute_type,
        )
        load_time = time.perf_counter() - start
        logger.info(f"faster-whisper model loaded in {load_time:.2f}s")
        return model, load_time

    def transcribe_whisper(
        self, model: Any, audio_path: str
    ) -> TranscriptionResult:
        """Transcribe with OpenAI Whisper.

        Args:
            model: Loaded Whisper model.
            audio_path: Path to audio file.

        Returns:
            TranscriptionResult with transcript and timing.
        """
        logger.info(f"Transcribing with Whisper: {os.path.basename(audio_path)}")
        start = time.perf_counter()
        result = model.transcribe(
            audio=audio_path,
            language="en",
            verbose=None,
        )
        transcription_time = time.perf_counter() - start

        transcript = result["text"]
        word_count = len(transcript.split())

        logger.info(f"Whisper transcription completed in {transcription_time:.2f}s")
        return TranscriptionResult(
            transcript=transcript,
            transcription_time=transcription_time,
            word_count=word_count,
        )

    def transcribe_faster_whisper(
        self, model: Any, audio_path: str
    ) -> TranscriptionResult:
        """Transcribe with faster-whisper.

        Args:
            model: Loaded faster-whisper model.
            audio_path: Path to audio file.

        Returns:
            TranscriptionResult with transcript and timing.
        """
        logger.info(f"Transcribing with faster-whisper: {os.path.basename(audio_path)}")
        start = time.perf_counter()

        # Transcribe - segments is a generator
        segments, _info = model.transcribe(
            audio_path,
            beam_size=5,
            language="en",
            vad_filter=True,  # Filter out silence
        )

        # Collect all segment texts
        segment_texts = [segment.text.strip() for segment in segments]
        transcript = " ".join(segment_texts)
        transcription_time = time.perf_counter() - start

        word_count = len(transcript.split())

        logger.info(f"faster-whisper transcription completed in {transcription_time:.2f}s")
        return TranscriptionResult(
            transcript=transcript,
            transcription_time=transcription_time,
            word_count=word_count,
        )

    def compare_transcripts(self, t1: str, t2: str) -> dict:
        """Compare two transcripts for similarity.

        Args:
            t1: First transcript.
            t2: Second transcript.

        Returns:
            Dict with similarity metrics.
        """
        # Normalize whitespace
        t1_normalized = " ".join(t1.split())
        t2_normalized = " ".join(t2.split())

        # Character-level similarity
        char_similarity = SequenceMatcher(None, t1_normalized, t2_normalized).ratio()

        # Word-level similarity
        words1 = t1_normalized.lower().split()
        words2 = t2_normalized.lower().split()
        word_similarity = SequenceMatcher(None, words1, words2).ratio()

        # Word count difference
        word_count_diff = abs(len(words1) - len(words2))

        return {
            "char_similarity": round(char_similarity, 4),
            "word_similarity": round(word_similarity, 4),
            "word_count_diff": word_count_diff,
        }

    def release_model(self) -> None:
        """Release GPU memory."""
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass  # torch not installed, skip CUDA cache clearing

    def benchmark_file(
        self,
        audio_path: str,
        whisper_model: Any,
        faster_whisper_model: Any,
        runs: int = 1,
    ) -> tuple[BenchmarkResult, str, str]:
        """Benchmark a single audio file.

        Args:
            audio_path: Path to audio file.
            whisper_model: Loaded Whisper model.
            faster_whisper_model: Loaded faster-whisper model.
            runs: Number of runs for averaging.

        Returns:
            Tuple of (BenchmarkResult, whisper_transcript, faster_whisper_transcript).

        Raises:
            ValueError: If runs is less than 1.
        """
        if runs < 1:
            raise ValueError("runs must be a positive integer (>= 1)")

        duration = self.get_audio_duration(audio_path)
        logger.info(f"Audio duration: {duration:.1f}s ({duration/60:.1f} min)")

        result = BenchmarkResult(
            file=os.path.basename(audio_path),
            duration_seconds=duration,
        )

        # Benchmark Whisper
        whisper_times = []
        whisper_result = None
        for i in range(runs):
            if runs > 1:
                logger.info(f"Whisper run {i+1}/{runs}")
            whisper_result = self.transcribe_whisper(whisper_model, audio_path)
            whisper_times.append(whisper_result.transcription_time)

        avg_whisper_time = sum(whisper_times) / len(whisper_times)
        result.whisper = {
            "transcription_time": round(avg_whisper_time, 2),
            "realtime_factor": round(avg_whisper_time / duration, 4) if duration else 0,
            "word_count": whisper_result.word_count,
        }

        # Benchmark faster-whisper
        faster_whisper_times = []
        faster_whisper_result = None
        for i in range(runs):
            if runs > 1:
                logger.info(f"faster-whisper run {i+1}/{runs}")
            faster_whisper_result = self.transcribe_faster_whisper(
                faster_whisper_model, audio_path
            )
            faster_whisper_times.append(faster_whisper_result.transcription_time)

        avg_faster_whisper_time = sum(faster_whisper_times) / len(faster_whisper_times)
        result.faster_whisper = {
            "transcription_time": round(avg_faster_whisper_time, 2),
            "realtime_factor": (
                round(avg_faster_whisper_time / duration, 4) if duration else 0
            ),
            "word_count": faster_whisper_result.word_count,
        }

        # Compare transcripts
        comparison = self.compare_transcripts(
            whisper_result.transcript,
            faster_whisper_result.transcript,
        )
        if avg_faster_whisper_time > 0:
            comparison["speedup"] = round(avg_whisper_time / avg_faster_whisper_time, 2)
        else:
            logger.warning("faster-whisper time is zero, cannot calculate speedup")
            comparison["speedup"] = float("inf")
        result.comparison = comparison

        return result, whisper_result.transcript, faster_whisper_result.transcript

    def run_benchmark(
        self,
        audio_files: list[str],
        runs: int = 1,
        output_dir: Optional[str] = None,
    ) -> BenchmarkReport:
        """Run full benchmark on audio files.

        Args:
            audio_files: List of audio file paths.
            runs: Number of runs per file for averaging.
            output_dir: Directory to save transcripts (optional).

        Returns:
            BenchmarkReport with all results.
        """
        report = BenchmarkReport(
            config={
                "model_sizes": self.model_sizes,
                "device": self.device,
                "compute_type": self.compute_type,
                "runs_per_file": runs,
                "num_files": len(audio_files),
            }
        )

        for model_size in self.model_sizes:
            logger.info(f"\n{'='*60}")
            logger.info(f"Testing model size: {model_size}")
            logger.info(f"{'='*60}")

            # Load models
            whisper_model, whisper_load_time = self.load_whisper(model_size)
            self.release_model()  # Clear some memory before loading next

            faster_whisper_model, faster_whisper_load_time = self.load_faster_whisper(
                model_size
            )

            report.model_load_times[model_size] = {
                "whisper": round(whisper_load_time, 2),
                "faster_whisper": round(faster_whisper_load_time, 2),
            }

            # Benchmark each file
            model_results = []
            total_speedup = 0

            for audio_path in audio_files:
                logger.info(f"\n--- Processing: {os.path.basename(audio_path)} ---")

                try:
                    result, whisper_transcript, faster_whisper_transcript = (
                        self.benchmark_file(
                            audio_path,
                            whisper_model,
                            faster_whisper_model,
                            runs=runs,
                        )
                    )
                    result_dict = {
                        "model_size": model_size,
                        "file": result.file,
                        "duration_seconds": result.duration_seconds,
                        "whisper": result.whisper,
                        "faster_whisper": result.faster_whisper,
                        "comparison": result.comparison,
                    }
                    model_results.append(result_dict)
                    report.results.append(result_dict)
                    total_speedup += result.comparison["speedup"]

                    # Save transcripts if output_dir specified
                    if output_dir:
                        self._save_transcripts(
                            output_dir,
                            model_size,
                            result.file,
                            whisper_transcript,
                            faster_whisper_transcript,
                        )

                except Exception:
                    logger.exception(f"Error processing {audio_path}")
                    continue

            # Calculate summary for this model size
            if model_results:
                avg_speedup = total_speedup / len(model_results)
                avg_char_sim = sum(
                    r["comparison"]["char_similarity"] for r in model_results
                ) / len(model_results)
                avg_word_sim = sum(
                    r["comparison"]["word_similarity"] for r in model_results
                ) / len(model_results)

                report.summary[model_size] = {
                    "avg_speedup": round(avg_speedup, 2),
                    "avg_char_similarity": round(avg_char_sim, 4),
                    "avg_word_similarity": round(avg_word_sim, 4),
                    "files_processed": len(model_results),
                }

            # Release models before loading next size
            del whisper_model
            del faster_whisper_model
            self.release_model()

        return report

    def _save_transcripts(
        self,
        output_dir: str,
        model_size: str,
        filename: str,
        whisper_transcript: str,
        faster_whisper_transcript: str,
    ) -> None:
        """Save transcripts to files for manual review.

        Args:
            output_dir: Directory to save transcripts.
            model_size: Model size used.
            filename: Original audio filename.
            whisper_transcript: Transcript from Whisper.
            faster_whisper_transcript: Transcript from faster-whisper.
        """
        base_name = os.path.splitext(filename)[0]
        model_dir = os.path.join(output_dir, model_size)
        os.makedirs(model_dir, exist_ok=True)

        whisper_path = os.path.join(model_dir, f"{base_name}_whisper.txt")
        with open(whisper_path, "w", encoding="utf-8") as f:
            f.write(whisper_transcript)

        faster_whisper_path = os.path.join(model_dir, f"{base_name}_faster_whisper.txt")
        with open(faster_whisper_path, "w", encoding="utf-8") as f:
            f.write(faster_whisper_transcript)

        logger.info(f"Saved transcripts to {model_dir}/")


def find_audio_files(
    path: str,
    extensions: tuple[str, ...] = (".mp3", ".wav", ".m4a", ".flac"),
    limit: Optional[int] = None,
) -> list[str]:
    """Find audio files in a directory or return single file.

    Args:
        path: File or directory path.
        extensions: Tuple of valid audio extensions.
        limit: Maximum number of files to return.

    Returns:
        List of audio file paths.
    """
    path = os.path.abspath(path)

    if os.path.isfile(path):
        return [path]

    if os.path.isdir(path):
        files = []
        for root, _, filenames in os.walk(path):
            for filename in filenames:
                if filename.lower().endswith(extensions):
                    files.append(os.path.join(root, filename))
                    if limit and len(files) >= limit:
                        return files
        return files

    raise ValueError(f"Path not found: {path}")


def main():
    """Main entry point."""
    check_dependencies()

    parser = argparse.ArgumentParser(
        description="Benchmark OpenAI Whisper vs faster-whisper transcription performance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Single file, all model sizes
    python scripts/benchmark_faster_whisper.py --audio-file /path/to/episode.mp3

    # Directory with limit
    python scripts/benchmark_faster_whisper.py --audio-dir /path/to/podcasts/ --limit 3

    # Specific models only
    python scripts/benchmark_faster_whisper.py --audio-file ep.mp3 --models large-v3,medium

    # Multiple runs for averaging
    python scripts/benchmark_faster_whisper.py --audio-file ep.mp3 --runs 3
        """,
    )
    parser.add_argument(
        "--audio-file",
        help="Single audio file to benchmark",
    )
    parser.add_argument(
        "--audio-dir",
        help="Directory of audio files to benchmark",
    )
    parser.add_argument(
        "--models",
        default="large-v3,medium,small",
        help="Comma-separated model sizes to test (default: large-v3,medium,small)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of runs per file for averaging (default: 1)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of files to process from directory",
    )
    parser.add_argument(
        "--output",
        default="benchmark_results.json",
        help="Output JSON file for results (default: benchmark_results.json)",
    )
    parser.add_argument(
        "--save-transcripts",
        help="Directory to save transcripts for manual review",
    )
    parser.add_argument(
        "--device",
        default="cuda",
        choices=["cuda", "cpu"],
        help="Device to use (default: cuda)",
    )
    parser.add_argument(
        "--compute-type",
        default="float16",
        help="Compute type for faster-whisper (default: float16)",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.audio_file and not args.audio_dir:
        parser.error("Must specify either --audio-file or --audio-dir")

    # Find audio files
    path = args.audio_file or args.audio_dir
    try:
        audio_files = find_audio_files(path, limit=args.limit)
    except ValueError:
        logger.exception("Invalid path provided")
        sys.exit(1)

    if not audio_files:
        logger.error(f"No audio files found in {path}")
        sys.exit(1)

    logger.info(f"Found {len(audio_files)} audio file(s) to benchmark")

    # Parse model sizes
    model_sizes = [m.strip() for m in args.models.split(",")]
    logger.info(f"Testing model sizes: {model_sizes}")

    # Check for GPU
    try:
        import torch

        if args.device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA requested but not available, falling back to CPU")
            args.device = "cpu"
        elif args.device == "cuda":
            logger.info(f"Using GPU: {torch.cuda.get_device_name(0)}")
    except ImportError:
        logger.warning("PyTorch not found, using CPU")
        args.device = "cpu"

    # Run benchmark
    benchmark = TranscriptionBenchmark(
        model_sizes=model_sizes,
        device=args.device,
        compute_type=args.compute_type,
    )

    report = benchmark.run_benchmark(
        audio_files=audio_files,
        runs=args.runs,
        output_dir=args.save_transcripts,
    )

    # Print summary
    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY")
    print("=" * 60)

    for model_size, summary in report.summary.items():
        print(f"\nModel: {model_size}")
        print(f"  Files processed: {summary['files_processed']}")
        print(f"  Average speedup: {summary['avg_speedup']}x")
        print(f"  Average char similarity: {summary['avg_char_similarity']:.2%}")
        print(f"  Average word similarity: {summary['avg_word_similarity']:.2%}")

        load_times = report.model_load_times.get(model_size, {})
        print("  Model load times:")
        print(f"    Whisper: {load_times.get('whisper', 'N/A')}s")
        print(f"    faster-whisper: {load_times.get('faster_whisper', 'N/A')}s")

    # Save results
    output_path = args.output
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "config": report.config,
                "model_load_times": report.model_load_times,
                "results": report.results,
                "summary": report.summary,
                "timestamp": report.timestamp,
            },
            f,
            indent=2,
        )

    logger.info(f"\nResults saved to {output_path}")

    if args.save_transcripts:
        logger.info(f"Transcripts saved to {args.save_transcripts}/")


if __name__ == "__main__":
    main()
