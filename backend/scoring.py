def clamp(value, low, high):
    return max(low, min(high, int(round(value))))

def calculate_score(fundamentals, insider, valuation, sentiment):
    return clamp(fundamentals + insider + valuation + sentiment, 0, 100)

def signal_label(score):
    if score >= 85:
        return "Strong"
    if score >= 75:
        return "Watch"
    if score >= 60:
        return "Neutral"
    return "Risk"
