#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional, List
from jinja2 import Environment, FileSystemLoader, select_autoescape
import traceback

def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def _resolve_pointer(doc: Dict[str, Any], pointer: str) -> Any:
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
    from datetime import datetime
    if not fmt or not isinstance(value, str):
        return value
    if fmt.startswith("date:"):
        try:
            dt = datetime.fromisoformat(value)
            return dt.strftime(fmt.split("date:", 1)[1].strip())
        except Exception:
            return value
    return value

def _compute_func(name: str) -> Any:
    from datetime import datetime
    if name == "today":
        return datetime.today().date().isoformat()
    raise ValueError(f"Unknown func: {name}")

def render_passport_html(customer: Dict[str, Any],
                         schema_path: Path,
                         render_templates_root: Optional[Path],
                         out_dir: Path) -> Path:
    passport = customer.get("id_documents", {}).get("passport")
    if not passport:
        # No passport for this customer, skip rendering
        return None
    cfg = load_json(schema_path)
    template_rel = cfg["template"]
    output_pattern = cfg.get("output_pattern", "passport_{customer_id}.html")
    fields_decl: List[Dict[str, Any]] = cfg["fields"]

    fields: Dict[str, Any] = {}
    for fld in fields_decl:
        key = fld["key"]
        source = fld.get("source")
        fmt = fld.get("format")

        if source.startswith("/"):
            val = _resolve_pointer(customer, source)
        elif source.startswith("func:"):
            val = _compute_func(source.split("func:", 1)[1])
        else:
            raise ValueError(f"Unsupported source: {source}")

        fields[key] = _apply_format(val, fmt)

    # Choose passport template based on nationality/country
    nationality = fields.get("nationality") or fields.get("country") or customer.get("demographics", {}).get("country")
    passport_country = nationality if nationality in {"SG", "MY", "CN", "IN"} else "SG"
    # e.g. templates/passport_SG.html, templates/passport_MY.html, etc.
    passport_template = f"passport_{passport_country}.html"
    try:
        env = Environment(
            loader=FileSystemLoader(str(render_templates_root or ".")),
            autoescape=select_autoescape(["html", "xml"])
        )
        template = env.get_template(passport_template)
    except Exception:
        # fallback to generic template if specific not found
        env = Environment(
            loader=FileSystemLoader(str(render_templates_root or ".")),
            autoescape=select_autoescape(["html", "xml"])
        )
        template = env.get_template(template_rel)

    html = template.render(fields=fields, customer=customer)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / output_pattern.format(customer_id=customer["customer_id"])
    out_path.write_text(html, encoding="utf-8")
    return out_path

def main():
    ap = argparse.ArgumentParser(description="Render Passport HTML for customers from JSONL.")
    ap.add_argument("--customer_list", type=Path, required=True, help="Input JSONL file with customers")
    ap.add_argument("--schema", type=Path, required=True, help="Path to passport field-declaration JSON")
    ap.add_argument("--render_templates_root", type=Path, default=Path("."), help="Root folder for HTML templates")
    ap.add_argument("--out", type=Path, default=Path("render_docs_out/"), help="Output folder for rendered documents")

    args = ap.parse_args()

    with args.customer_list.open("r", encoding="utf-8") as f:
        for line in f:
            customer = json.loads(line)
            try:
                out_path = render_passport_html(
                    customer=customer,
                    schema_path=args.schema,
                    render_templates_root=args.render_templates_root,
                    out_dir=args.out,
                )
            except Exception as e:
                print(f"[warn] Failed to render passport for {customer.get('customer_id', '?')}: {e}")
                traceback.print_exc()

            if (out_path is None): 
                print(f"No passport details for customer {customer.get('customer_id', '?')}, skipping.")
            else:
                print(f"Rendered passport for customer {customer.get('customer_id', '?')}. HTML documents to {args.out}")

if __name__ == "__main__":
    main()