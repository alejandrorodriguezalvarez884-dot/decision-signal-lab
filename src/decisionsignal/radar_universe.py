"""The companies the radar covers: the study's S&P 100 list of December 2020, with the name and
sector shown on the site.

Sectors are GICS sectors as of 2026, assigned by hand. The SIC-based map in ``config.py`` is too
coarse to publish (it files UnitedHealth under finance and Nike under industrials). CIKs are the
ones the filings were downloaded with.
"""

from __future__ import annotations

from typing import NamedTuple


class Company(NamedTuple):
    name: str
    sector: str
    cik: int


IT, HEALTH, FIN, COMM = "Information Technology", "Health Care", "Financials", "Communication Services"
DISC, STAPLES, INDUS, ENERGY = "Consumer Discretionary", "Consumer Staples", "Industrials", "Energy"
UTIL, MATERIALS, REAL_ESTATE = "Utilities", "Materials", "Real Estate"

# Keyed by the ticker used across the project (``price_ticker``).
COMPANIES: dict[str, Company] = {
    "AAPL": Company("Apple", IT, 320193),
    "ABBV": Company("AbbVie", HEALTH, 1551152),
    "ABT": Company("Abbott Laboratories", HEALTH, 1800),
    "ACN": Company("Accenture", IT, 1467373),
    "ADBE": Company("Adobe", IT, 796343),
    "AIG": Company("American International Group", FIN, 5272),
    "ALL": Company("Allstate", FIN, 899051),
    "AMGN": Company("Amgen", HEALTH, 318154),
    "AMT": Company("American Tower", REAL_ESTATE, 1053507),
    "AMZN": Company("Amazon", DISC, 1018724),
    "AXP": Company("American Express", FIN, 4962),
    "BA": Company("Boeing", INDUS, 12927),
    "BAC": Company("Bank of America", FIN, 70858),
    "BIIB": Company("Biogen", HEALTH, 875045),
    "BKNG": Company("Booking Holdings", DISC, 1075531),
    "BLK": Company("BlackRock", FIN, 2012383),
    "BMY": Company("Bristol Myers Squibb", HEALTH, 14272),
    "BNY": Company("BNY", FIN, 1390777),
    "BRK-B": Company("Berkshire Hathaway", FIN, 1067983),
    "C": Company("Citigroup", FIN, 831001),
    "CAT": Company("Caterpillar", INDUS, 18230),
    "CHTR": Company("Charter Communications", COMM, 1091667),
    "CL": Company("Colgate-Palmolive", STAPLES, 21665),
    "CMCSA": Company("Comcast", COMM, 1166691),
    "COF": Company("Capital One", FIN, 927628),
    "COP": Company("ConocoPhillips", ENERGY, 1163165),
    "COST": Company("Costco", STAPLES, 909832),
    "CRM": Company("Salesforce", IT, 1108524),
    "CSCO": Company("Cisco", IT, 858877),
    "CVS": Company("CVS Health", HEALTH, 64803),
    "CVX": Company("Chevron", ENERGY, 93410),
    "DD": Company("DuPont", MATERIALS, 1666700),
    "DHR": Company("Danaher", HEALTH, 313616),
    "DIS": Company("Walt Disney", COMM, 1744489),
    "DOW": Company("Dow", MATERIALS, 1751788),
    "DUK": Company("Duke Energy", UTIL, 1326160),
    "EMR": Company("Emerson Electric", INDUS, 32604),
    "EXC": Company("Exelon", UTIL, 1109357),
    "F": Company("Ford", DISC, 37996),
    "FDX": Company("FedEx", INDUS, 1048911),
    "GD": Company("General Dynamics", INDUS, 40533),
    "GE": Company("GE Aerospace", INDUS, 40545),
    "GILD": Company("Gilead Sciences", HEALTH, 882095),
    "GM": Company("General Motors", DISC, 1467858),
    "GOOG": Company("Alphabet", COMM, 1652044),
    "GS": Company("Goldman Sachs", FIN, 886982),
    "HD": Company("Home Depot", DISC, 354950),
    "HON": Company("Honeywell", INDUS, 773840),
    "IBM": Company("IBM", IT, 51143),
    "INTC": Company("Intel", IT, 50863),
    "JNJ": Company("Johnson & Johnson", HEALTH, 200406),
    "JPM": Company("JPMorgan Chase", FIN, 19617),
    "KHC": Company("Kraft Heinz", STAPLES, 1637459),
    "KMI": Company("Kinder Morgan", ENERGY, 1506307),
    "KO": Company("Coca-Cola", STAPLES, 21344),
    "LLY": Company("Eli Lilly", HEALTH, 59478),
    "LMT": Company("Lockheed Martin", INDUS, 936468),
    "LOW": Company("Lowe's", DISC, 60667),
    "MA": Company("Mastercard", FIN, 1141391),
    "MCD": Company("McDonald's", DISC, 63908),
    "MDLZ": Company("Mondelez", STAPLES, 1103982),
    "MDT": Company("Medtronic", HEALTH, 1613103),
    "MET": Company("MetLife", FIN, 1099219),
    "META": Company("Meta Platforms", COMM, 1326801),
    "MMM": Company("3M", INDUS, 66740),
    "MO": Company("Altria", STAPLES, 764180),
    "MRK": Company("Merck", HEALTH, 310158),
    "MS": Company("Morgan Stanley", FIN, 895421),
    "MSFT": Company("Microsoft", IT, 789019),
    "NEE": Company("NextEra Energy", UTIL, 753308),
    "NFLX": Company("Netflix", COMM, 1065280),
    "NKE": Company("Nike", DISC, 320187),
    "NVDA": Company("Nvidia", IT, 1045810),
    "ORCL": Company("Oracle", IT, 1341439),
    "PEP": Company("PepsiCo", STAPLES, 77476),
    "PFE": Company("Pfizer", HEALTH, 78003),
    "PG": Company("Procter & Gamble", STAPLES, 80424),
    "PM": Company("Philip Morris International", STAPLES, 1413329),
    "PYPL": Company("PayPal", FIN, 1633917),
    "QCOM": Company("Qualcomm", IT, 804328),
    "RTX": Company("RTX", INDUS, 101829),
    "SBUX": Company("Starbucks", DISC, 829224),
    "SLB": Company("SLB", ENERGY, 87347),
    "SO": Company("Southern Company", UTIL, 92122),
    "SPG": Company("Simon Property Group", REAL_ESTATE, 1063761),
    "T": Company("AT&T", COMM, 732717),
    "TGT": Company("Target", STAPLES, 27419),
    "TMO": Company("Thermo Fisher Scientific", HEALTH, 97745),
    "TSLA": Company("Tesla", DISC, 1318605),
    "TXN": Company("Texas Instruments", IT, 97476),
    "UNH": Company("UnitedHealth Group", HEALTH, 731766),
    "UNP": Company("Union Pacific", INDUS, 100885),
    "UPS": Company("UPS", INDUS, 1090727),
    "USB": Company("U.S. Bancorp", FIN, 36104),
    "V": Company("Visa", FIN, 1403161),
    "VZ": Company("Verizon", COMM, 732712),
    "WFC": Company("Wells Fargo", FIN, 72971),
    "WMT": Company("Walmart", STAPLES, 104169),
    "XOM": Company("ExxonMobil", ENERGY, 2115436),
}

TICKER_BY_CIK: dict[int, str] = {c.cik: t for t, c in COMPANIES.items()}
