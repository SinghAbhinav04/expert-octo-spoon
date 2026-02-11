"""
Memory Manager — Short-term (session) and long-term (user) memory

Stores interaction history in MongoDB for context-aware agent behavior.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid


class MemoryManager:
    """
    Manages agent memory:
    - Short-term: per-session conversation history
    - Long-term: per-user interaction patterns (future Phase 3)
    """

    COLLECTION = "agent_memory"

    async def get_session_context(
        self,
        db,
        session_id: str,
        limit: int = 10,
        max_chars: int = 3000,
    ) -> str:
        """
        Fetch recent conversation context for this session.

        Args:
            db: Database instance
            session_id: Session ID to fetch context for
            limit: Max number of exchanges to fetch
            max_chars: Max characters in returned context

        Returns:
            Formatted string of recent exchanges
        """
        try:
            cursor = db.db[self.COLLECTION].find(
                {"session_id": str(session_id)}
            ).sort("created_at", -1).limit(limit)

            exchanges = []
            async for doc in cursor:
                exchanges.append(doc)

            if not exchanges:
                return ""

            # Reverse to chronological order
            exchanges.reverse()

            # Format as context string
            lines = []
            total_chars = 0
            for ex in exchanges:
                user_line = f"User: {ex.get('prompt', '')[:500]}"
                ai_line = f"AI: {ex.get('response', '')[:500]}"
                block = f"{user_line}\n{ai_line}"

                if total_chars + len(block) > max_chars:
                    break
                lines.append(block)
                total_chars += len(block)

            return "\n---\n".join(lines)

        except Exception as e:
            print(f"⚠️ Memory fetch failed: {e}")
            return ""

    async def store_interaction(
        self,
        db,
        session_id: str,
        user_id: str,
        prompt: str,
        response: str,
        plan: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Store an interaction in memory.

        Args:
            db: Database instance
            session_id: Session ID
            user_id: User ID
            prompt: User's prompt
            response: Agent's response
            plan: Execution plan (optional)
        """
        try:
            doc = {
                "_id": str(uuid.uuid4()),
                "session_id": str(session_id),
                "user_id": str(user_id),
                "prompt": prompt[:5000],
                "response": response[:10000],
                "plan_summary": {
                    "complexity": plan.get("complexity", "unknown") if plan else "unknown",
                    "steps_count": len(plan.get("steps", [])) if plan else 0,
                } if plan else None,
                "created_at": datetime.now(timezone.utc),
            }
            await db.db[self.COLLECTION].insert_one(doc)
        except Exception as e:
            print(f"⚠️ Memory store failed: {e}")

    async def get_user_history(
        self,
        db,
        user_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Fetch user's interaction history across all sessions.
        Used for long-term memory and pattern analysis (Phase 3).
        """
        try:
            cursor = db.db[self.COLLECTION].find(
                {"user_id": str(user_id)}
            ).sort("created_at", -1).limit(limit)

            results = []
            async for doc in cursor:
                doc["id"] = doc.pop("_id")
                results.append(doc)
            return results
        except Exception:
            return []

    async def get_session_memory(
        self,
        db,
        session_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all memory entries for a session (for API response).
        """
        try:
            cursor = db.db[self.COLLECTION].find(
                {"session_id": str(session_id)}
            ).sort("created_at", 1)

            results = []
            async for doc in cursor:
                doc["id"] = doc.pop("_id")
                results.append(doc)
            return results
        except Exception:
            return []


# ─── Singleton ───────────────────────────────────────────────────────────────

_memory: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    """Get or create the global memory manager"""
    global _memory
    if _memory is None:
        _memory = MemoryManager()
    return _memory
