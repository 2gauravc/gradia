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

def _resolve_pointer(doc: Dict[str, Any], pointer: str) -> Any:
    """
    Resolve a very small subset of JSON Pointer: /a/b/c
    """
    if not pointer or pointer[0] != "/":
        raise ValueError(f"Invalid JSON pointer: {pointer}")
    cur = doc
    for part in pointer.strip("/").split("/"):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(f"Path not found: {pointer}")
    return cur

def _apply_format(value: Any, fmt: Optional[str]) -> Any:
    if not fmt or not isinstance(value, str):
        return value
    if fmt.startswith("date:"):
        try:
            # value expected ISO date (YYYY-MM-DD)
            dt = datetime.fromisoformat(value)
            return dt.strftime(fmt.split("date:", 1)[1].strip())
        except Exception:
            return value
    return value

def _compute_func(name: str) -> Any:
    if name == "today":
        return datetime.today().date().isoformat()
    raise ValueError(f"Unknown func: {name}")

def render_nric_html(customer: Dict[str, Any],
                     cfg_path: Path,
                     templates_root: Optional[Path],
                     out_dir: Path) -> Path:
    cfg = load_json(cfg_path)
    template_rel = cfg["template"]
    output_pattern = cfg.get("output_pattern", "nric_{customer_id}.html")
    fields_decl: List[Dict[str, Any]] = cfg["fields"]

    # Build data context for template from field declarations
    fields: Dict[str, Any] = {}
    for fld in fields_decl:
        key = fld["key"]
        source = fld.get("source")
        fmt = fld.get("format")

        if source.startswith("/"):  # JSON pointer
            val = _resolve_pointer(customer, source)
        elif source.startswith("func:"):
            val = _compute_func(source.split("func:", 1)[1])
        else:
            raise ValueError(f"Unsupported source: {source}")

        fields[key] = _apply_format(val, fmt)

    # Jinja2 env
    if templates_root is None:
        templates_root = Path(".")
    env = Environment(
        loader=FileSystemLoader(str(templates_root)),
        autoescape=select_autoescape(["html", "xml"])
    )
    template = env.get_template(template_rel)
    html = template.render(fields=fields, customer=customer)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / output_pattern.format(customer_id=customer["customer_id"])
    out_path.write_text(html, encoding="utf-8")
    return out_path


# -------- Core generator --------

def gen_customer(schema: Dict[str, Any], constraints: Dict[str, Any]) -> Dict[str, Any]:
    # Constraints
    min_age = int(constraints.get("min_age", 0))
    max_age = int(constraints.get("max_age", 90))
    fixed_country = constraints.get("country")  # e.g., "SG"
    fixed_currency = constraints.get("currency")  # e.g., "SGD"

    # Demographics base from constraints/country
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

    nationality = constraints.get("nationality") or country
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
            "expiry_date": fake.date_between(start_date="+1y", end_date="+10y").isoformat(),
            "issuing_country": country
        }

    if id_documents:
        customer["id_documents"] = id_documents

    # Financials for adults only
    if age >= 18:
        emp_dist = constraints.get("employment_distribution", DEFAULT_EMPLOY_DIST)
        total = sum(max(0.0, v) for v in emp_dist.values()) or 1.0
        emp_dist = {k: max(0.0, v) / total for k, v in emp_dist.items()}

        emp_type = weighted_choice(emp_dist)

        rngs_cfg_in = constraints.get("monthly_income_ranges", {})
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
    ap.add_argument("--constraints", type=Path, help="Path to constraints JSON")
    ap.add_argument("--out", type=Path, default=Path("customers.jsonl"), help="Output JSONL file")
    ap.add_argument("--seed", type=int, default=None, help="Random seed")
    ap.add_argument("--nric-config", type=Path, help="Path to NRIC field-declaration JSON (e.g., config/nric_fields.json)")
    ap.add_argument("--templates-root", type=Path, default=Path("."), help="Root folder for HTML templates")
    ap.add_argument("--doc-out", type=Path, default=Path("docs_out"), help="Output folder for rendered documents")

    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    schema = load_json(args.schema)
    constraints: Dict[str, Any] = load_json(args.constraints) if args.constraints else {}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for _ in range(args.count):
            record = gen_customer(schema, constraints)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

            # Render NRIC HTML if config is provided
            if args.nric_config:
                try:
                    render_nric_html(
                        customer=record,
                        cfg_path=args.nric_config,
                        templates_root=args.templates_root,
                        out_dir=args.doc_out,
                    )
                except Exception as e:
                    # Do not abort batch; log and continue
                    print(f"[warn] Failed to render NRIC for {record['customer_id']}: {e}")

    print(f"Wrote {args.count} customers to {args.out}")

if __name__ == "__main__":
    main()
