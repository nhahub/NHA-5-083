"""Local Hugging Face ONNX semantic matcher for zero-cost NLP fallback."""

from __future__ import annotations

import logging
import threading
from typing import Any, Protocol

import numpy as np
from huggingface_hub import hf_hub_download
from numpy.typing import NDArray

from web.backend.constants import (
    DEFAULT_SEMANTIC_CUISINE_THRESHOLD,
    DEFAULT_SEMANTIC_MODEL_ID,
    DEFAULT_SEMANTIC_PRICE_MARGIN,
    DEFAULT_SEMANTIC_PRICE_THRESHOLD,
    PRICE_RANGE_TIER_FOUR,
    PRICE_RANGE_TIER_ONE,
    PRICE_RANGE_TIER_THREE,
    PRICE_RANGE_TIER_TWO,
)
from web.backend.repositories.meta_repository import VocabularySnapshot
from web.backend.settings import BackendSettings, settings

logger = logging.getLogger(__name__)

_MAX_SEQ_LENGTH = 64
_INIT_BATCH_SIZE = 32
_OFF_TOPIC_THRESHOLD = 0.36
_OFF_TOPIC_MARGIN = 0.06

_DINING_PROTOTYPES: tuple[str, ...] = (
    "restaurants dining food cuisine eat meal menu dish",
    "cafe coffee brunch dinner lunch breakfast delivery reservation",
    "spicy curry sushi pizza pasta tacos burger steak bakery",
)

_OFF_TOPIC_PROTOTYPES: tuple[str, ...] = (
    "hotels accommodation resort airbnb room stay check-in",
    "flights airline tickets airport travel booking",
    "laptops smartphones electronics computers gadgets shopping",
    "weather forecast temperature rain sunny climate",
    "programming python javascript code software debugging script",
    "sports football soccer basketball world cup match score",
    "car engine repair mechanic automotive oil change",
    "tell me a joke movies music books entertainment",
)

_CUISINE_DESCRIPTORS: dict[str, str] = {
    "North Indian": (
        "North Indian curry tandoori biryani butter chicken naan tikka masala"
    ),
    "South Indian": "South Indian dosa idli sambar uttapam filter coffee",
    "Indian": "Indian curry masala tandoor thali biryani",
    "Japanese": "Japanese sushi sashimi ramen tempura udon teriyaki izakaya",
    "Italian": "Italian pasta pizza risotto lasagna gnocchi trattoria",
    "Pizza": "Pizza wood-fired flatbread margherita pepperoni",
    "Mexican": "Mexican tacos burritos quesadilla nachos guacamole salsa",
    "Chinese": "Chinese dim sum noodles dumplings fried rice stir fry",
    "Thai": "Thai pad thai green curry red curry tom yum",
    "Cafe": "Cafe coffee espresso cappuccino latte brunch pastry",
    "Bakery": "Bakery bread croissant pastry cake muffin",
    "Desserts": "Desserts ice cream gelato cake pastry sweets",
    "American": "American burger steakhouse fries diner bbq wings",
    "Burger": "Burger cheeseburger smash burger fries",
    "Mediterranean": "Mediterranean hummus falafel kebab mezze pita grilled",
    "Middle Eastern": "Middle Eastern shawarma falafel hummus mezze kebab",
    "Seafood": "Seafood fish oysters lobster crab shrimp prawns",
    "Korean": "Korean bbq kimchi bibimbap bulgogi",
    "Vietnamese": "Vietnamese pho banh mi spring rolls",
    "Steak": "Steakhouse grilled ribeye sirloin fillet",
    "Healthy Food": "Healthy salad grain bowl smoothie vegan",
    "Fast Food": "Fast food quick bite burger fries wrap sandwich",
    "Mughlai": "Mughlai kebab biryani korma rich gravy",
    "Asian": "Asian noodles wok stir fry dumplings",
    "Continental": "Continental European bistro steak pasta soup",
}

_PRICE_TIER_PROFILES: tuple[tuple[int, str], ...] = (
    (
        PRICE_RANGE_TIER_ONE,
        "cheap eats budget street food inexpensive low cost quick bite",
    ),
    (
        PRICE_RANGE_TIER_TWO,
        "affordable moderate mid-range reasonable casual everyday dining",
    ),
    (
        PRICE_RANGE_TIER_THREE,
        "upscale nice classy pricey date spot elevated dining",
    ),
    (
        PRICE_RANGE_TIER_FOUR,
        "fine dining luxury Michelin tasting menu romantic fancy expensive",
    ),
)


class SemanticMatcher(Protocol):
    """Protocol for semantic cuisine, price-tier, and domain matching."""

    def is_ready(self) -> bool:
        """Return True if the semantic model and index are ready."""
        ...

    def is_off_topic(self, query: str) -> bool:
        """Return True when the query is clearly unrelated to dining/restaurants."""
        ...

    def match_cuisines(self, query: str, top_k: int = 2) -> list[str]:
        """Return canonical cuisines semantically matching the query."""
        ...

    def match_price_range(self, query: str) -> int | None:
        """Return inferred price tier (1-4) when confidence and margin pass."""
        ...


class HFOnnxSemanticMatcher:
    """In-process Hugging Face ONNX encoder using ``all-MiniLM-L6-v2``."""

    def __init__(
        self,
        vocabulary: VocabularySnapshot,
        *,
        model_id: str = DEFAULT_SEMANTIC_MODEL_ID,
        cuisine_threshold: float = DEFAULT_SEMANTIC_CUISINE_THRESHOLD,
        price_threshold: float = DEFAULT_SEMANTIC_PRICE_THRESHOLD,
        price_margin: float = DEFAULT_SEMANTIC_PRICE_MARGIN,
    ) -> None:
        """Load ONNX session and pre-embed canonical cuisines and price tiers."""
        self._model_id = model_id
        self._cuisine_threshold = cuisine_threshold
        self._price_threshold = price_threshold
        self._price_margin = price_margin
        self._ready = False
        self._session: Any = None
        self._tokenizer: Any = None
        self._input_names: set[str] = set()
        self._cuisines: tuple[str, ...] = vocabulary.cuisines
        self._cuisine_matrix: NDArray[np.float32] | None = None
        self._price_tiers: tuple[int, ...] = tuple(
            tier for tier, _ in _PRICE_TIER_PROFILES
        )
        self._price_matrix: NDArray[np.float32] | None = None
        self._dining_matrix: NDArray[np.float32] | None = None
        self._off_topic_matrix: NDArray[np.float32] | None = None

        self._initialize()

    def _initialize(self) -> None:
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer

            model_path = hf_hub_download(
                repo_id=self._model_id,
                filename="onnx/model.onnx",
            )
            tokenizer_path = hf_hub_download(
                repo_id=self._model_id,
                filename="tokenizer.json",
            )
            tokenizer = Tokenizer.from_file(tokenizer_path)
            tokenizer.enable_truncation(max_length=_MAX_SEQ_LENGTH)
            tokenizer.enable_padding()

            # Disable ONNX Runtime's pre-allocated CPU memory arena and cap threads
            # to keep RSS overhead under ~200 MB on Azure B1 / 1 GiB Container Apps.
            sess_options = ort.SessionOptions()
            sess_options.enable_cpu_mem_arena = False
            sess_options.intra_op_num_threads = 2
            session = ort.InferenceSession(
                model_path,
                sess_options=sess_options,
                providers=["CPUExecutionProvider"],
            )
            self._tokenizer = tokenizer
            self._session = session
            self._input_names = {inp.name for inp in session.get_inputs()}

            if self._cuisines:
                cuisine_texts = [
                    _CUISINE_DESCRIPTORS.get(cuisine, f"{cuisine} restaurant cuisine")
                    for cuisine in self._cuisines
                ]
                # Mini-batch vocabulary encoding avoids a single large activation spike.
                batches = [
                    self._encode(cuisine_texts[i : i + _INIT_BATCH_SIZE])
                    for i in range(0, len(cuisine_texts), _INIT_BATCH_SIZE)
                ]
                self._cuisine_matrix = np.vstack(batches)
            price_texts = [desc for _, desc in _PRICE_TIER_PROFILES]
            self._price_matrix = self._encode(price_texts)
            self._dining_matrix = self._encode(list(_DINING_PROTOTYPES))
            self._off_topic_matrix = self._encode(list(_OFF_TOPIC_PROTOTYPES))
            self._ready = True
        except (OSError, RuntimeError, ValueError, ImportError) as exc:
            logger.warning(
                "Hugging Face ONNX semantic matcher unavailable; using regex only",
                extra={"details": f"{type(exc).__name__}: {exc}"},
            )
            self._ready = False

    def _encode(self, texts: list[str]) -> NDArray[np.float32]:
        """Encode input texts into L2-normalized mean-pooled embeddings.

        Args:
            texts: Non-empty batch of strings to embed.

        Returns:
            Float32 array of shape ``(len(texts), hidden_dim)`` with unit-norm
            rows so dot products equal cosine similarity.
        """
        encodings = self._tokenizer.encode_batch(texts)
        input_ids = np.array([enc.ids for enc in encodings], dtype=np.int64)
        attention_mask = np.array(
            [enc.attention_mask for enc in encodings], dtype=np.int64
        )
        feeds: dict[str, NDArray[np.int64]] = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }
        if "token_type_ids" in self._input_names:
            feeds["token_type_ids"] = np.zeros_like(input_ids, dtype=np.int64)

        outputs = self._session.run(None, feeds)
        token_embeddings = np.asarray(outputs[0], dtype=np.float32)
        # Attention-masked mean pooling matches sentence-transformers' MiniLM head.
        mask_expanded = np.expand_dims(attention_mask.astype(np.float32), axis=-1)
        summed = np.sum(token_embeddings * mask_expanded, axis=1)
        counts = np.clip(np.sum(mask_expanded, axis=1), a_min=1e-9, a_max=None)
        pooled = summed / counts
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        norms = np.clip(norms, a_min=1e-9, a_max=None)
        return np.asarray(pooled / norms, dtype=np.float32)

    def is_ready(self) -> bool:
        """Return True if ONNX session and vocabulary embeddings initialized."""
        return self._ready

    def is_off_topic(self, query: str) -> bool:
        """Return True if the query aligns much closer to off-topic domains."""
        if (
            not self._ready
            or self._dining_matrix is None
            or self._off_topic_matrix is None
            or not query.strip()
        ):
            return False
        query_vec = self._encode([query])[0]
        dining_score = float(np.max(self._dining_matrix @ query_vec))
        off_topic_score = float(np.max(self._off_topic_matrix @ query_vec))
        return (
            off_topic_score >= _OFF_TOPIC_THRESHOLD
            and (off_topic_score - dining_score) >= _OFF_TOPIC_MARGIN
        )

    def match_cuisines(self, query: str, top_k: int = 2) -> list[str]:
        """Return top canonical cuisines above the similarity threshold."""
        if not self._ready or self._cuisine_matrix is None or not query.strip():
            return []
        query_vec = self._encode([query])[0]
        scores = self._cuisine_matrix @ query_vec
        ranked_indices = np.argsort(-scores)
        matches: list[str] = []
        for idx in ranked_indices[:top_k]:
            if float(scores[idx]) >= self._cuisine_threshold:
                matches.append(self._cuisines[int(idx)])
        return matches

    def match_price_range(self, query: str) -> int | None:
        """Return inferred price tier (1-4) if top score and margin pass."""
        if not self._ready or self._price_matrix is None or not query.strip():
            return None
        query_vec = self._encode([query])[0]
        scores = self._price_matrix @ query_vec
        ranked = np.argsort(-scores)
        best_idx = int(ranked[0])
        second_idx = int(ranked[1])
        best_score = float(scores[best_idx])
        second_score = float(scores[second_idx])
        if (
            best_score >= self._price_threshold
            and (best_score - second_score) >= self._price_margin
        ):
            return self._price_tiers[best_idx]
        return None


_MATCHER_LOCK = threading.Lock()
_MATCHER_CACHE: dict[
    tuple[str, tuple[str, ...], float, float], HFOnnxSemanticMatcher
] = {}


def get_cached_semantic_matcher(
    vocabulary: VocabularySnapshot,
    app_settings: BackendSettings | None = None,
) -> HFOnnxSemanticMatcher | None:
    """Return a process-cached ``HFOnnxSemanticMatcher`` when enabled."""
    cfg = app_settings or settings
    if not cfg.nlp_semantic_enabled:
        return None
    cache_key = (
        cfg.nlp_semantic_model_id,
        vocabulary.cuisines,
        cfg.nlp_semantic_cuisine_threshold,
        cfg.nlp_semantic_price_threshold,
    )
    with _MATCHER_LOCK:
        cached = _MATCHER_CACHE.get(cache_key)
        if cached is not None:
            return cached
        matcher = HFOnnxSemanticMatcher(
            vocabulary=vocabulary,
            model_id=cfg.nlp_semantic_model_id,
            cuisine_threshold=cfg.nlp_semantic_cuisine_threshold,
            price_threshold=cfg.nlp_semantic_price_threshold,
        )
        _MATCHER_CACHE[cache_key] = matcher
        return matcher
