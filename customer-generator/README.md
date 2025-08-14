# Customer Generator

Generate realistic synthetic customer records that **validate against a JSON Schema**, with optional **constraints** like `country=SG`.

## Structure
```
customer-generator/
├── README.md
├── requirements.txt
├── schema/
│   └── customer.schema.json
├── config/
│   └── example_constraints.json
└── src/
    └── generate_customers.py
```

## Install
Create a virtual environment (recommended), then:
```bash
pip install -r requirements.txt
```

## Quickstart
Generate 5 Singapore customers:
```bash
python src/generate_customers.py   --schema schema/customer.schema.json   --count 5000 --config config/generate_customer_config.json    --out gen_data_out/customers.jsonl   --seed 42
```
Generate NRIC HTML documents for these customers:
```
python src/render_nric.py   --customer_list gen_data_out/customers.jsonl   --schema schema/nric_schema.json   --render_templates_root .   --out render_docs_out/
```

Generate passport HTML documents for these customers 
```
python src/render_passport.py \
  --customer_list gen_data_out/customers.jsonl \
  --schema schema/passport_schema.json \
  --render_templates_root templates/ \
  --out render_docs_out/
```


Output is a **JSON Lines** file (`.jsonl`), one customer per line. 

## Constraints
You can control generation using a JSON constraints file. Example (already included):
```json
{
  "country": "SG",
  "currency": "SGD",
  "min_age": 0,
  "max_age": 90,
  "employment_distribution": {
    "Full-time": 0.55,
    "Part-time": 0.10,
    "Self-employed": 0.10,
    "Unemployed": 0.05,
    "Retired": 0.10,
    "Student": 0.10
  },
  "monthly_income_ranges": {
    "Full-time": [3000, 15000],
    "Part-time": [800, 4000],
    "Self-employed": [2000, 20000],
    "Unemployed": [0, 800],
    "Retired": [0, 5000],
    "Student": [0, 1500]
  }
}
```

## Validation
Every generated record is validated against `schema/customer.schema.json` using `jsonschema` (Draft 2020-12). If a record fails validation, generation aborts with a descriptive error.

## Notes
- Adults (age ≥ 18) include `financials`; minors do not.
- For `country=SG`, names use `Faker('en_SG')` and cities are chosen from common planning areas.
- Annual income ≈ monthly × 12 with ±5% noise for realism.
