def clamp(value, low, high):
    return max(low, min(high, value))

def calculate_score(fundamentals, insider, valuation, sentiment):
    # Current model: 40 + 25 + 20 + 15 = 100
    return clamp(round(fundamentals + insider + valuation + sentiment), 0, 100)

def signal_label(score):
    if score >= 85:
        return "Strong"
    if score >= 75:
        return "Watch"
    if score >= 60:
        return "Neutral"
    return "Risk"
