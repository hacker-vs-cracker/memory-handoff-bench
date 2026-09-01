from __future__ import annotations

import re
from typing import Any

from qdrant_client import QdrantClient, models

from .hashing import short_hash


class VectorStore:
    def __init__(self, url: str, collection_prefix: str) -> None:
        self.client = QdrantClient(url=url, timeout=30)
        self.collection_prefix = collection_prefix

    def health(self) -> bool:
        self.client.get_collections()
        return True

    def collection_name(self, encoder: str, encoder_digest: str | None, dimension: int) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", encoder).strip("_").lower()
        identity = encoder_digest or short_hash(encoder)
        return f"{self.collection_prefix}_{normalized}_{identity[:12]}_{dimension}"

    def ensure_collection(self, name: str, dimension: int) -> None:
        if self.client.collection_exists(name):
            info = self.client.get_collection(name)
            vectors = info.config.params.vectors
            configured_size = getattr(vectors, "size", None)
            if configured_size is not None and configured_size != dimension:
                raise ValueError(
                    f"Collection {name} has dimension {configured_size}, expected {dimension}"
                )
            return
        self.client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE),
        )
        for key in ("trial_id", "run_id", "case_id"):
            self.client.create_payload_index(
                collection_name=name,
                field_name=key,
                field_schema=models.PayloadSchemaType.KEYWORD,
                wait=True,
            )

    def upsert(
        self,
        collection: str,
        point_id: str,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        self.client.upsert(
            collection_name=collection,
            points=[models.PointStruct(id=point_id, vector=vector, payload=payload)],
            wait=True,
        )

    def query(
        self,
        collection: str,
        vector: list[float],
        trial_id: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        result = self.client.query_points(
            collection_name=collection,
            query=vector,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(key="trial_id", match=models.MatchValue(value=trial_id))
                ]
            ),
            limit=top_k,
            with_payload=True,
            with_vectors=True,
        )
        return [
            {
                "id": str(point.id),
                "score": float(point.score),
                "payload": point.payload or {},
                "vector": point.vector,
            }
            for point in result.points
        ]

    def delete_trial_points(self, collection: str, trial_id: str) -> None:
        self.client.delete(
            collection_name=collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="trial_id", match=models.MatchValue(value=trial_id)
                        )
                    ]
                )
            ),
            wait=True,
        )
