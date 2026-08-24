def clamp(value, low, high):
    return max(low, min(high, int(round(value))))

def calculate_score(fundamentals, insider, valuation, sentiment):
    return clamp(fundamentals + insider + valuation + sentiment, 0, 100)

def signal_label(score):
    """Human-readable signal band for the 0–100 model score."""
    score = float(score or 0)
    if score >= 80:
        return "Strong"
    if score >= 70:
        return "Watch"
    if score >= 60:
        return "Neutral"
    return "Risk"
