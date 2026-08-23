from dataclasses import dataclass

@dataclass
class Stock:
    ticker: str
    name: str
    sector: str
    price: float
    change_pct: float
    score: int
    fundamentals: int
    insider: int
    valuation: int
    sentiment: int
    short_score: int
