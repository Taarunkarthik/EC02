"""Participant-safe feedback derived only from saved scoring components."""

ANSWER_FIELDS = (
    ("error_location", "Error location", "error_loc_score", 0.10),
    ("error_type", "Error type", "error_type_score", 0.15),
    ("expected_output", "Expected output", "output_score", 0.20),
    ("cause", "Root cause", "cause_score", 0.25),
    ("correction", "Correction / fix", "correction_score", 0.30),
)


def answer_field_results(scores, base_points):
    """Describe automated credit before penalties, multipliers or total overrides.

    Accept component scores, never reference answers, so old submissions can be
    reviewed without regrading them against a newer question bank.
    """
    results = []
    for key, label, score_key, weight in ANSWER_FIELDS:
        score = round(float(scores.get(score_key) or 0), 2)
        maximum = round(max(0, float(base_points)) * weight, 2)
        status = "correct" if maximum > 0 and score >= maximum else "partial" if score > 0 else "incorrect"
        results.append({"key": key, "label": label, "status": status,
                        "score": score, "max_score": maximum})
    return results
