#!/usr/bin/env python3
import argparse
import json
import random
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List
from jinja2 import Environment, FileSystemLoader, select_autoescape

from faker import Faker
from jsonschema import Draft202012Validator

# -------- Helpers & constants --------

SG_CITIES = [
    "Central Area", "Bukit Timah", "Jurong East", "Jurong West", "Tampines",
    "Bedok", "Hougang", "Yishun", "Punggol", "Sengkang", "Toa Payoh",
    "Ang Mo Kio", "Woodlands", "Bukit Panjang", "Queenstown", "Clementi",
    "Marine Parade", "Serangoon", "Pasir Ris", "Choa Chu Kang"
]

DEFAULT_EMPLOY_DIST = {
    "Full-time": 0.60,
    "Part-time": 0.10,
    "Self-employed": 0.10,
    "Unemployed": 0.05,
    "Retired": 0.10,
    "Student": 0.05,
}

DEFAULT_MONTHLY_RANGES = {
    "Full-time": (3000, 15000),
    "Part-time": (800, 4000),
    "Self-employed": (2000, 20000),
    "Unemployed": (0, 800),
    "Retired": (0, 5000),
    "Student": (0, 1500),
}

fake = Faker("en_GB")  # generic English names; avoid unsupported locales

def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def weighted_choice(weights: Dict[str, float]) -> str:
    items = list(weights.items())
    choices, probs = zip(*items)
    return random.choices(list(choices), weights=list(probs), k=1)[0]

def triangular(lo: float, hi: float, mode_frac: float = 0.35) -> float:
    mode = lo + mode_frac * (hi - lo)
    return random.triangular(lo, hi, mode)

def random_dob(age_min: int, age_max: int) -> date:
    """Generate DOB so that age is between [age_min, age_max]."""
    today = date.today()
    # Convert age range to DOB range
    latest_dob = today.replace(year=today.year - age_min)
    earliest_dob = today.replace(year=today.year - age_max) - timedelta(days=365)
    span_days = (latest_dob - earliest_dob).days
    return earliest_dob + timedelta(days=random.randint(0, span_days))

def age_from_dob(dob: date) -> int:
    today = date.today()
    years = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        years -= 1
    return years

def gen_passport_number() -> str:
    # Synthetic: two letters + 7 digits
    return f"{fake.random_uppercase_letter()}{fake.random_uppercase_letter()}{random.randint(1000000, 9999999)}"

def gen_sg_nric_number() -> str:
    # Synthetic NRIC-like format: prefix + 7 digits + checksum (fake)
    prefix = random.choice(["S", "T", "F", "G"])
    digits = [random.randint(0, 9) for _ in range(7)]
    checksum = random.choice(list("ABCDEFGHIZJKLMN"))  # not real; just looks valid
    return prefix + "".join(str(d) for d in digits) + checksum

def compute_income(emp_type: str,
                   ranges_cfg: Dict[str, Tuple[float, float]]) -> Tuple[float, float]:
    lo, hi = ranges_cfg.get(emp_type, (2000, 10000))
    monthly = round(triangular(lo, hi), 2)
    if emp_type in ("Unemployed", "Student"):
        monthly = max(0.0, monthly)
    annual = round(monthly * 12 * (1 + random.uniform(-0.05, 0.05)), 2)  # ±5%
    return monthly, annual


# -------- Core generator --------

def gen_customer(schema: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    # Config parameters
    min_age = int(config.get("min_age", 0))
    max_age = int(config.get("max_age", 90))
    fixed_country = config.get("country")  # e.g., "SG"
    fixed_currency = config.get("currency")  # e.g., "SGD"

    # Demographics base from config/country
    if fixed_country == "SG":
        country = "SG"
        city = random.choice(SG_CITIES)
    else:
        country = fixed_country or fake.current_country_code()
        city = fake.city()

    # Personal details
    first_name = fake.first_name()
    last_name = fake.last_name()
    full_name = f"{first_name} {last_name}"

    nationality = config.get("nationality") or country
    address = fake.address().replace("\n", ", ")

    dob = random_dob(min_age, max_age)
    age = age_from_dob(dob)

    personal_details = {
        "name": full_name,
        "nationality": nationality,
        "date_of_birth": dob.isoformat(),
        "address": address
    }

    gender = random.choice(["Male", "Female", "Other", "Prefer not to say"])
    demographics = {
        "age": age,
        "gender": gender,
        "country": country,
        "city": city
    }

    customer: Dict[str, Any] = {
        "customer_id": str(uuid.uuid4()),
        "personal_details": personal_details,
        "demographics": demographics
    }

    # ID documents (copy nationality/address from personal_details)
    id_documents: Dict[str, Any] = {}

    if country == "SG":
        id_documents["nric"] = {
            "nric_number": gen_sg_nric_number(),
            "nationality": personal_details["nationality"],
            "address": personal_details["address"]
        }

    # Give most adults a passport; minors too (optional) but less likely
    have_passport = random.random() < (0.95 if age >= 18 else 0.6)
    if have_passport:
        id_documents["passport"] = {
            "passport_number": gen_passport_number(),
            "nationality": personal_details["nationality"],
            "issue_date": fake.date_between(start_date="-10y", end_date="today").isoformat(),
            "expiry_date": fake.date_between(start_date="+1y", end_date="+10y").isoformat(),
            "issuing_country": country,
            "place_of_issue": city
        }

    if id_documents:
        customer["id_documents"] = id_documents

    # Financials for adults only
    if age >= 18:
        emp_dist = config.get("employment_distribution", DEFAULT_EMPLOY_DIST)
        total = sum(max(0.0, v) for v in emp_dist.values()) or 1.0
        emp_dist = {k: max(0.0, v) / total for k, v in emp_dist.items()}

        emp_type = weighted_choice(emp_dist)

        rngs_cfg_in = config.get("monthly_income_ranges", {})
        ranges_cfg: Dict[str, Tuple[float, float]] = {}
        for k, default in DEFAULT_MONTHLY_RANGES.items():
            if k in rngs_cfg_in:
                lo, hi = rngs_cfg_in[k]
                ranges_cfg[k] = (float(lo), float(hi))
            else:
                ranges_cfg[k] = default

        monthly, annual = compute_income(emp_type, ranges_cfg)
        currency = fixed_currency or ("SGD" if country == "SG" else "USD")

        customer["financials"] = {
            "employment_type": emp_type,
            "monthly_income": monthly,
            "annual_income": annual,
            "currency": currency
        }

    # Validate
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(customer), key=lambda e: e.path)
    if errors:
        msgs = "\n".join(f"- {'/'.join(map(str, e.path))}: {e.message}" for e in errors)
        raise ValueError(f"Generated customer failed schema validation:\n{msgs}")

    return customer

# -------- CLI --------

def main():
    ap = argparse.ArgumentParser(description="Generate synthetic customers for the Customer schema.")
    ap.add_argument("--schema", type=Path, required=True, help="Path to customer.schema.json")
    ap.add_argument("--count", type=int, default=10, help="Number of records")
    ap.add_argument("--config", type=Path, help="Path to customer config JSON")
    ap.add_argument("--out", type=Path, default=Path("gen_data_out/customers.jsonl"), help="Output JSONL file")
    ap.add_argument("--seed", type=int, default=None, help="Random seed")

    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    schema = load_json(args.schema)
    config: Dict[str, Any] = load_json(args.config) if args.config else {}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for _ in range(args.count):
            record = gen_customer(schema, config)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Wrote {args.count} customers to {args.out}")

if __name__ == "__main__":
    main()
