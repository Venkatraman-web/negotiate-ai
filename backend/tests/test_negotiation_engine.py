import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.negotiation_engine import (  # noqa: E402
    _SESSIONS,
    calculate_next_offer,
    create_session,
    get_session,
    update_session_state,
)


class NegotiationEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        _SESSIONS.clear()

    def test_calculate_next_offer_increases_conservatively(self) -> None:
        session = create_session("Salary Negotiation", "Logical", current_offer=9, target_offer=12, minimum_offer=8, maximum_offer=12)
        session["trust"] = 80
        session["patience"] = 70
        session["round"] = 3

        analysis = {
            "politeness": 8,
            "confidence": 8,
            "reasoning_quality": 9,
            "aggression": 1,
            "flexibility": 7,
        }

        self.assertEqual(calculate_next_offer(session, analysis), 10)

    def test_update_session_state_ends_when_patience_hits_zero(self) -> None:
        session = create_session("Salary Negotiation", "Aggressive", current_offer=10, target_offer=12, minimum_offer=8, maximum_offer=12)
        session["patience"] = 1
        session["round"] = 7

        analysis = {
            "politeness": 2,
            "confidence": 5,
            "reasoning_quality": 4,
            "aggression": 9,
            "flexibility": 1,
        }

        updated = update_session_state(session["session_id"], analysis)

        self.assertEqual(updated["patience"], 0)
        self.assertEqual(updated["status"], "completed")


if __name__ == "__main__":
    unittest.main()
