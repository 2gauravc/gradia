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

def render_nric_html(customer: Dict[str, Any],
                     schema_path: Path,
                     templates_root: Optional[Path],
                     out_dir: Path) -> Path:
    schema = load_json(schema_path)
    template_rel = schema["template"]
    output_pattern = schema.get("output_pattern", "nric_{customer_id}.html")
    fields_decl: List[Dict[str, Any]] = schema["fields"]

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

def main():
    ap = argparse.ArgumentParser(description="Render NRIC HTML for customers from JSONL.")
    ap.add_argument("--customer_list", type=Path, required=True, help="Input JSONL file with customers")
    ap.add_argument("--schema", type=Path, required=True, help="Path to NRIC schema JSON")
    ap.add_argument("--render_templates_root", type=Path, default=Path("."), help="Root folder for HTML templates")
    ap.add_argument("--out", type=Path, default=Path("render_docs_out/"), help="Output folder for rendered documents")

    args = ap.parse_args()

    with args.customer_list.open("r", encoding="utf-8") as f:
        for line in f:
            customer = json.loads(line)
            try:
                render_nric_html(
                    customer=customer,
                    schema_path=args.schema,
                    templates_root=args.render_templates_root,
                    out_dir=args.out,
                )
            except Exception as e:
                print(f"[warn] Failed to render NRIC for {customer.get('customer_id', '?')}: {e}")
                traceback.print_exc()

    print(f"Rendered NRIC HTML documents to {args.out}")

if __name__ == "__main__":
    main()