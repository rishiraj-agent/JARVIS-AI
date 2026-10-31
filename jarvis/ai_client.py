from __future__ import annotations

import hashlib
import json
import math
import os
import random
import sys
import time
from pathlib import Path
from threading import Event
from typing import Callable, Iterator


class AIError(Exception):
    """Safe, user-facing error from the local JARVIS language model."""


class LocalLanguageModel:
    """Small from-scratch byte-bigram neural LM (an educational first milestone).

    A trainable embedding for the previous byte feeds a softmax output layer.
    All parameters start from a local PRNG's Gaussian initialization. This is
    intentionally not described as a Transformer or a capable general LLM.
    """

    FORMAT_VERSION = 1
    BOS, EOS, UNK, PAD = 256, 257, 258, 259
    VOCAB_SIZE = 260
    EMBEDDING_DIM = 8
    MAX_CORPUS_BYTES = 512 * 1024
    MAX_TRAIN_PAIRS = 1024
    MAX_VALIDATION_PAIRS = 256
    DEMO_CORPUS = """Hello JARVIS. I am learning one character at a time.
Namaste, kaise ho? This is an original tiny training example.
Main apna chhota AI model bana raha hoon.
The CPU processes one small training example at a time.
Computer ki memory ko safe limit ke andar rakhna chahiye.
JARVIS can save a locally trained checkpoint.
Hindi text uses UTF-8 bytes in this first experiment.
Training changes randomly initialized neural network parameters.
This demo corpus tests the pipeline and is not broad knowledge.
Small educational models need more licensed training text to improve."""

    def __init__(self, checkpoint_path: Path, seed: int | None = None) -> None:
        self.checkpoint_path = Path(checkpoint_path)
        self.seed = int(seed if seed is not None else random.SystemRandom().getrandbits(32))
        self._rng = random.Random(self.seed)
        self.embedding_count = self.VOCAB_SIZE * self.EMBEDDING_DIM
        self.projection_count = self.EMBEDDING_DIM * self.VOCAB_SIZE
        self.parameter_count = self.embedding_count + self.projection_count + self.VOCAB_SIZE
        self.embedding: list[float] = []
        self.projection: list[float] = []
        self.bias: list[float] = []
        self.first_moment: list[float] = []
        self.second_moment: list[float] = []
        self.training_steps = 0
        self.epochs = 0
        self.tokens_processed = 0
        self.dataset_source = "not trained"
        self.dataset_sha256 = ""
        self.training_loss: float | None = None
        self.validation_loss: float | None = None
        self.learning_rate = 0.01
        self.history: list[dict[str, float | int | None]] = []
        self.load_error: str | None = None
        self._initialize_randomly()
        if self.checkpoint_path.is_file():
            try:
                self.load_checkpoint()
            except AIError as error:
                self.load_error = str(error)

    def _initialize_randomly(self) -> None:
        scale = 1.0 / math.sqrt(self.EMBEDDING_DIM)
        self.embedding = [self._rng.gauss(0.0, scale) for _ in range(self.embedding_count)]
        self.projection = [self._rng.gauss(0.0, scale) for _ in range(self.projection_count)]
        self.bias = [0.0] * self.VOCAB_SIZE
        self.first_moment = [0.0] * self.parameter_count
        self.second_moment = [0.0] * self.parameter_count

    @property
    def is_trained(self) -> bool:
        return self.training_steps > 0

    def status(self) -> dict[str, object]:
        return {
            "name": "JARVIS Byte-Bigram Neural LM · v1",
            "architecture": "previous-byte embedding → softmax; one-byte context; no Transformer",
            "vocabulary_size": self.VOCAB_SIZE,
            "embedding_dimension": self.EMBEDDING_DIM,
            "parameter_count": self.parameter_count,
            "training_steps": self.training_steps,
            "epochs": self.epochs,
            "tokens_processed": self.tokens_processed,
            "training_loss": self.training_loss,
            "validation_loss": self.validation_loss,
            "dataset_source": self.dataset_source,
            "dataset_sha256": self.dataset_sha256,
            "checkpoint": str(self.checkpoint_path) if self.is_trained else "not trained",
            "checkpoint_error": self.load_error,
            "estimated_parameter_bytes": self.parameter_count * 8 * 3,
        }

    def train_file(
        self,
        source_path: str | Path,
        epochs: int = 3,
        learning_rate: float = 0.01,
        stop_event: Event | None = None,
        progress: Callable[[dict[str, object]], None] | None = None,
    ) -> dict[str, object]:
        path = Path(source_path)
        if path.suffix.lower() not in {".txt", ".md", ".csv"}:
            raise AIError("Training data must be a user-approved TXT, Markdown, or CSV file.")
        try:
            size = path.stat().st_size
            if size <= 0:
                raise AIError("The selected training file is empty.")
            if size > self.MAX_CORPUS_BYTES:
                raise AIError("For low-memory safety, training files must be 512 KiB or smaller.")
            raw = path.read_bytes()
            if len(raw) > self.MAX_CORPUS_BYTES:
                raise AIError("The training file grew beyond the 512 KiB safety limit while reading.")
            text = raw.decode("utf-8-sig")
        except AIError:
            raise
        except (OSError, UnicodeDecodeError) as error:
            raise AIError(f"Could not read a UTF-8 training file: {error}") from None
        checksum = hashlib.sha256(raw).hexdigest()
        return self.train_text(
            text, path.name, checksum, epochs, learning_rate, stop_event, progress
        )

    def train_demo(
        self,
        epochs: int = 3,
        learning_rate: float = 0.01,
        stop_event: Event | None = None,
        progress: Callable[[dict[str, object]], None] | None = None,
    ) -> dict[str, object]:
        payload = self.DEMO_CORPUS.encode("utf-8")
        return self.train_text(
            self.DEMO_CORPUS, "synthetic educational demo (not a knowledge dataset)",
            hashlib.sha256(payload).hexdigest(), epochs, learning_rate,
            stop_event, progress,
        )

    def train_text(
        self,
        text: str,
        source: str,
        checksum: str,
        epochs: int = 3,
        learning_rate: float = 0.01,
        stop_event: Event | None = None,
        progress: Callable[[dict[str, object]], None] | None = None,
    ) -> dict[str, object]:
        if not 1 <= int(epochs) <= 100:
            raise AIError("Epochs must be from 1 to 100.")
        if not math.isfinite(learning_rate) or not 0.00001 <= learning_rate <= 0.1:
            raise AIError("Learning rate must be between 0.00001 and 0.1.")
        if len(text.encode("utf-8")) > self.MAX_CORPUS_BYTES:
            raise AIError("For low-memory safety, training text must be 512 KiB or smaller.")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) < 2:
            raise AIError("Training needs at least two non-empty text lines.")
        if len(lines) >= 10:
            validation_lines = [line for index, line in enumerate(lines) if index % 10 == 9]
            training_lines = [line for index, line in enumerate(lines) if index % 10 != 9]
        else:
            validation_lines = []
            training_lines = lines
        if not training_lines:
            raise AIError("The deterministic train/validation split left no training text.")

        training_sequences = [self._encode_line(line) for line in training_lines]
        validation_sequences = [self._encode_line(line) for line in validation_lines]
        total_pairs = sum(max(0, len(sequence) - 1) for sequence in training_sequences)
        if not total_pairs:
            raise AIError("Training text produced no byte-token predictions.")
        stride = max(1, math.ceil(total_pairs / self.MAX_TRAIN_PAIRS))
        validation_stride = max(
            1,
            math.ceil(
                max(1, sum(max(0, len(sequence) - 1) for sequence in validation_sequences))
                / self.MAX_VALIDATION_PAIRS
            ),
        )
        self.learning_rate = float(learning_rate)
        started = time.perf_counter()
        stopped = False
        for epoch_offset in range(int(epochs)):
            running_loss = 0.0
            used = 0
            pair_number = 0
            for sequence in training_sequences:
                for index in range(len(sequence) - 1):
                    if pair_number % stride == 0 and used < self.MAX_TRAIN_PAIRS:
                        if stop_event is not None and stop_event.is_set():
                            stopped = True
                            break
                        sample_loss = self._train_pair(
                            sequence[index], sequence[index + 1], self.learning_rate
                        )
                        running_loss += sample_loss
                        used += 1
                    pair_number += 1
                if stopped:
                    break
            if used:
                self.tokens_processed += used
                self.training_loss = running_loss / used
                self.epochs += 1
            if validation_sequences and not stopped:
                self.validation_loss = self._evaluate(validation_sequences, validation_stride)
            self.dataset_source = source[:255]
            self.dataset_sha256 = checksum
            elapsed = time.perf_counter() - started
            self.history.append({
                "epoch": self.epochs,
                "training_loss": self.training_loss,
                "validation_loss": self.validation_loss,
                "learning_rate": self.learning_rate,
                "tokens_processed": self.tokens_processed,
                "elapsed_seconds": elapsed,
            })
            self.history = self.history[-100:]
            self.save_checkpoint()
            report = {
                "epoch": self.epochs,
                "requested_epochs": int(epochs),
                "training_loss": self.training_loss,
                "validation_loss": self.validation_loss,
                "learning_rate": self.learning_rate,
                "tokens_processed": self.tokens_processed,
                "epoch_tokens": used,
                "elapsed_seconds": elapsed,
                "estimated_remaining_seconds": None,
                "memory_bytes": self.estimated_memory_bytes(),
                "parameter_count": self.parameter_count,
                "checkpoint": str(self.checkpoint_path),
                "stopped": stopped,
            }
            if progress is not None:
                progress(report)
            if stopped:
                break

        return self.status() | {
            "elapsed_seconds": time.perf_counter() - started,
            "stopped": stopped,
            "dataset_lines": len(lines),
            "training_lines": len(training_lines),
            "validation_lines": len(validation_lines),
            "sampled_training_pairs_per_epoch": min(self.MAX_TRAIN_PAIRS, math.ceil(total_pairs / stride)),
        }

    def _encode_line(self, line: str) -> list[int]:
        encoded = line.encode("utf-8")[:2048]
        return [self.BOS, *encoded, self.EOS]

    def _forward(self, context_id: int) -> tuple[list[float], list[float]]:
        start = context_id * self.EMBEDDING_DIM
        vector = self.embedding[start:start + self.EMBEDDING_DIM]
        logits = [self.bias[token] for token in range(self.VOCAB_SIZE)]
        for dim in range(self.EMBEDDING_DIM):
            weight_start = dim * self.VOCAB_SIZE
            value = vector[dim]
            for token in range(self.VOCAB_SIZE):
                logits[token] += value * self.projection[weight_start + token]
        maximum = max(logits)
        exp_logits = [math.exp(max(-60.0, value - maximum)) for value in logits]
        denominator = sum(exp_logits)
        return vector, [value / denominator for value in exp_logits]

    def _train_pair(self, context_id: int, target_id: int, learning_rate: float) -> float:
        vector, probabilities = self._forward(context_id)
        loss = -math.log(max(probabilities[target_id], 1e-12))
        grad_logits = probabilities[:]
        grad_logits[target_id] -= 1.0
        grad_embedding = [0.0] * self.EMBEDDING_DIM
        for dim in range(self.EMBEDDING_DIM):
            weight_start = dim * self.VOCAB_SIZE
            grad_embedding[dim] = sum(
                grad_logits[token] * self.projection[weight_start + token]
                for token in range(self.VOCAB_SIZE)
            )

        step = self.training_steps + 1
        for dim in range(self.EMBEDDING_DIM):
            weight_start = dim * self.VOCAB_SIZE
            for token in range(self.VOCAB_SIZE):
                weight_index = self.embedding_count + weight_start + token
                gradient = max(-5.0, min(5.0, vector[dim] * grad_logits[token]))
                self._adam_update(weight_index, gradient, learning_rate, step)
        bias_start = self.embedding_count + self.projection_count
        for token, gradient in enumerate(grad_logits):
            self._adam_update(
                bias_start + token, max(-5.0, min(5.0, gradient)), learning_rate, step
            )
        embedding_start = context_id * self.EMBEDDING_DIM
        for dim, gradient in enumerate(grad_embedding):
            self._adam_update(
                embedding_start + dim, max(-5.0, min(5.0, gradient)), learning_rate, step
            )
        self.training_steps = step
        return loss

    def _adam_update(self, index: int, gradient: float, learning_rate: float, step: int) -> None:
        beta1, beta2 = 0.9, 0.999
        first = beta1 * self.first_moment[index] + (1.0 - beta1) * gradient
        second = beta2 * self.second_moment[index] + (1.0 - beta2) * gradient * gradient
        self.first_moment[index] = first
        self.second_moment[index] = second
        corrected_first = first / (1.0 - beta1 ** step)
        corrected_second = second / (1.0 - beta2 ** step)
        update = learning_rate * corrected_first / (math.sqrt(corrected_second) + 1e-8)
        if index < self.embedding_count:
            self.embedding[index] -= update
        elif index < self.embedding_count + self.projection_count:
            self.projection[index - self.embedding_count] -= update
        else:
            self.bias[index - self.embedding_count - self.projection_count] -= update

    def _evaluate(self, sequences: list[list[int]], stride: int) -> float | None:
        total_loss = 0.0
        count = 0
        pair_number = 0
        for sequence in sequences:
            for index in range(len(sequence) - 1):
                if pair_number % stride == 0 and count < self.MAX_VALIDATION_PAIRS:
                    _, probabilities = self._forward(sequence[index])
                    total_loss -= math.log(max(probabilities[sequence[index + 1]], 1e-12))
                    count += 1
                pair_number += 1
        return total_loss / count if count else None

    def generate(
        self,
        prompt: str,
        max_tokens: int = 160,
        temperature: float = 0.85,
        top_k: int = 12,
        deterministic: bool = False,
        cancel_event: Event | None = None,
    ) -> str:
        if not self.is_trained:
            raise AIError(
                "The JARVIS model has not been trained yet. Open My AI Model and train "
                "the clearly labelled demo corpus or select your own UTF-8 TXT/MD/CSV data."
            )
        max_tokens = max(1, min(int(max_tokens), 512))
        if not math.isfinite(temperature) or not 0.05 <= temperature <= 2.0:
            raise AIError("Temperature must be between 0.05 and 2.0.")
        prompt_bytes = prompt.encode("utf-8")
        context_id = prompt_bytes[-1] if prompt_bytes else self.BOS
        generated = bytearray()
        rng = random.Random()
        for _ in range(max_tokens):
            if cancel_event is not None and cancel_event.is_set():
                break
            _, probabilities = self._forward(context_id)
            if deterministic:
                next_id = max(range(self.VOCAB_SIZE), key=probabilities.__getitem__)
            else:
                candidates = sorted(
                    range(self.VOCAB_SIZE), key=probabilities.__getitem__, reverse=True
                )[:max(1, min(int(top_k), self.VOCAB_SIZE))]
                weights = [probabilities[index] ** (1.0 / temperature) for index in candidates]
                total = sum(weights)
                needle = rng.random() * total
                next_id = candidates[-1]
                for candidate, weight in zip(candidates, weights):
                    needle -= weight
                    if needle <= 0:
                        next_id = candidate
                        break
            if next_id == self.EOS:
                break
            if next_id > 255:
                continue
            generated.append(next_id)
            context_id = next_id
        decoded = generated.decode("utf-8", errors="replace")
        return "".join(char for char in decoded if char in "\n\t" or ord(char) >= 32).strip()

    def chat_stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        user_message = next(
            (item.get("content", "") for item in reversed(messages) if item.get("role") == "user"),
            "",
        )
        response = self.generate(user_message)
        if response:
            yield response
        else:
            yield "The trained model generated an empty response for this prompt."

    def estimated_memory_bytes(self) -> int:
        arrays = (
            self.embedding, self.projection, self.bias,
            self.first_moment, self.second_moment,
        )
        return sum(sys.getsizeof(values) + sum(sys.getsizeof(value) for value in values) for values in arrays)

    def save_checkpoint(self) -> None:
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": "JARVIS_LOCAL_NEURAL_LM",
            "format_version": self.FORMAT_VERSION,
            "architecture": {
                "name": "byte_bigram_embedding_softmax",
                "vocabulary_size": self.VOCAB_SIZE,
                "embedding_dimension": self.EMBEDDING_DIM,
                "context_length_bytes": 1,
            },
            "initialization": {"method": "random Gaussian", "seed": self.seed},
            "optimizer": {"name": "Adam", "learning_rate": self.learning_rate},
            "embedding": self.embedding,
            "projection": self.projection,
            "bias": self.bias,
            "first_moment": self.first_moment,
            "second_moment": self.second_moment,
            "metadata": {
                "training_steps": self.training_steps,
                "epochs": self.epochs,
                "tokens_processed": self.tokens_processed,
                "dataset_source": self.dataset_source,
                "dataset_sha256": self.dataset_sha256,
                "training_loss": self.training_loss,
                "validation_loss": self.validation_loss,
                "history": self.history[-100:],
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            },
        }
        temporary = self.checkpoint_path.with_suffix(self.checkpoint_path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.checkpoint_path)
        except OSError as error:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise AIError(f"Could not save the local model checkpoint: {error}") from None

    def load_checkpoint(self) -> None:
        try:
            if self.checkpoint_path.stat().st_size > 16 * 1024 * 1024:
                raise AIError("The checkpoint exceeds the 16 MiB safety limit.")
            payload = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        except AIError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AIError(f"Could not read the JARVIS checkpoint: {error}") from None
        if not isinstance(payload, dict):
            raise AIError("The checkpoint root must be a JARVIS model object.")
        architecture = payload.get("architecture", {})
        if not isinstance(architecture, dict):
            raise AIError("Checkpoint architecture metadata is malformed.")
        if (
            payload.get("format") != "JARVIS_LOCAL_NEURAL_LM"
            or payload.get("format_version") != self.FORMAT_VERSION
            or architecture.get("name") != "byte_bigram_embedding_softmax"
            or architecture.get("vocabulary_size") != self.VOCAB_SIZE
            or architecture.get("embedding_dimension") != self.EMBEDDING_DIM
        ):
            raise AIError("Checkpoint format or architecture is not a JARVIS-owned model.")
        arrays = {
            "embedding": self.embedding_count,
            "projection": self.projection_count,
            "bias": self.VOCAB_SIZE,
            "first_moment": self.parameter_count,
            "second_moment": self.parameter_count,
        }
        loaded: dict[str, list[float]] = {}
        try:
            for name, expected in arrays.items():
                values = payload[name]
                if not isinstance(values, list) or len(values) != expected:
                    raise ValueError(f"invalid {name} size")
                converted = [float(value) for value in values]
                if not all(math.isfinite(value) for value in converted):
                    raise ValueError(f"non-finite {name} value")
                loaded[name] = converted
            metadata = payload["metadata"]
            if not isinstance(metadata, dict):
                raise ValueError("invalid training metadata")
            training_steps = int(metadata["training_steps"])
            epochs = int(metadata["epochs"])
            tokens_processed = int(metadata["tokens_processed"])
            if min(training_steps, epochs, tokens_processed) < 0:
                raise ValueError("negative training metadata")
            if not isinstance(metadata.get("history", []), list):
                raise ValueError("invalid training history")
            optimizer = payload.get("optimizer", {})
            if not isinstance(optimizer, dict):
                raise ValueError("invalid optimizer metadata")
            learning_rate = float(optimizer.get("learning_rate", 0.01))
            if not math.isfinite(learning_rate) or not 0.00001 <= learning_rate <= 0.1:
                raise ValueError("invalid learning rate")
            initialization = payload.get("initialization", {})
            if not isinstance(initialization, dict):
                raise ValueError("invalid initialization metadata")
            seed = int(initialization.get("seed", self.seed))
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            raise AIError(f"The JARVIS checkpoint failed validation: {error}") from None
        self.embedding = loaded["embedding"]
        self.projection = loaded["projection"]
        self.bias = loaded["bias"]
        self.first_moment = loaded["first_moment"]
        self.second_moment = loaded["second_moment"]
        self.seed = seed
        self.training_steps = training_steps
        self.epochs = epochs
        self.tokens_processed = tokens_processed
        self.dataset_source = str(metadata.get("dataset_source", "unknown"))[:255]
        self.dataset_sha256 = str(metadata.get("dataset_sha256", ""))[:64]
        self.training_loss = self._optional_finite_float(metadata.get("training_loss"))
        self.validation_loss = self._optional_finite_float(metadata.get("validation_loss"))
        self.learning_rate = learning_rate
        self.history = metadata.get("history", [])[-100:]

    @staticmethod
    def _optional_finite_float(value: object) -> float | None:
        if value is None:
            return None
        parsed = float(value)
        if not math.isfinite(parsed):
            raise AIError("Checkpoint metadata contains a non-finite loss value.")
        return parsed
