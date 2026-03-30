#!/usr/bin/env python3
"""
update_gold_results.py
======================
Actualiza la tabla whale_signals en Supabase con los resultados
resueltos del dataset gold_enriched.csv.

Solo toca filas donde result/pnl_teorico/resolved_at estaban NULL
y ahora tienen valor en el CSV enriquecido.

Uso:
    python update_gold_results.py                          # usa gold_enriched.csv por defecto
    python update_gold_results.py --csv mi_archivo.csv    # CSV personalizado
    python update_gold_results.py --dry-run               # muestra cambios sin aplicarlos
    python update_gold_results.py --id 42                 # actualizar solo un id específico
"""

import os
import sys
import csv
import argparse
import math
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from supabase import create_client
except ImportError:
    print("❌ Supabase no instalado. Ejecuta: pip install supabase")
    sys.exit(1)


# ── Configuración ──────────────────────────────────────────────────────────────

DEFAULT_CSV = Path(__file__).parent / "gold_enriched.csv"

SUPABASE_URL = os.getenv("SUPA_GOLD_URL")
SUPABASE_KEY = os.getenv("SUPA_GOLD_KEY")

# Columnas que se actualizan (solo si CSV tiene valor y Supabase tiene NULL)
UPDATE_COLS = ["result", "pnl_teorico", "resolved_at"]


# ── Helpers ────────────────────────────────────────────────────────────────────

def is_empty(val) -> bool:
    """True si el valor está vacío/nulo."""
    if val is None:
        return True
    if isinstance(val, float) and math.isnan(val):
        return True
    return str(val).strip() in ("", "None", "nan", "NaN", "NULL", "null")


def parse_float(val):
    """Convierte a float o None."""
    if is_empty(val):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def normalize_row(row: dict) -> dict:
    """Extrae solo las columnas relevantes de una fila del CSV."""
    return {
        "id":          int(row["id"]),
        "result":      None if is_empty(row.get("result"))      else str(row["result"]).strip(),
        "pnl_teorico": parse_float(row.get("pnl_teorico")),
        "resolved_at": None if is_empty(row.get("resolved_at")) else str(row["resolved_at"]).strip(),
    }


def load_csv(path: Path) -> list[dict]:
    """Carga el CSV y devuelve lista de filas normalizadas con resolución."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            r = normalize_row(raw)
            # Solo interesan filas que tienen resultado
            if r["result"] is not None:
                rows.append(r)
    return rows


# ── Lógica principal ───────────────────────────────────────────────────────────

def run(csv_path: Path, dry_run: bool, target_id: int | None, batch_size: int = 50):
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Variables SUPA_GOLD_URL / SUPA_GOLD_KEY no encontradas en .env")
        sys.exit(1)

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    print(f"📂 CSV: {csv_path}")
    rows = load_csv(csv_path)

    if target_id is not None:
        rows = [r for r in rows if r["id"] == target_id]
        if not rows:
            print(f"⚠️  ID {target_id} no encontrado en CSV o no tiene resultado.")
            return

    print(f"📊 Filas con resultado en CSV: {len(rows)}")

    # Consultar estado actual en Supabase para esos IDs
    ids = [r["id"] for r in rows]

    # Supabase acepta máx ~1000 ids por query con .in_()
    # Dividir en batches de 200 para seguridad
    sb_data = {}
    for i in range(0, len(ids), 200):
        chunk = ids[i:i+200]
        resp = sb.table("whale_signals").select("id,result,pnl_teorico,resolved_at").in_("id", chunk).execute()
        for row in (resp.data or []):
            sb_data[row["id"]] = row

    print(f"🔍 Filas encontradas en Supabase: {len(sb_data)}")

    # Determinar cuáles necesitan actualización
    to_update = []
    skipped_already_set  = 0
    skipped_not_in_db    = 0

    for r in rows:
        rid = r["id"]

        if rid not in sb_data:
            skipped_not_in_db += 1
            continue

        current = sb_data[rid]

        # Solo actualizar si Supabase tiene NULL en result
        if not is_empty(current.get("result")):
            skipped_already_set += 1
            continue

        payload = {}
        for col in UPDATE_COLS:
            new_val = r.get(col)
            if not is_empty(new_val):
                payload[col] = new_val

        if payload:
            to_update.append({"id": rid, "payload": payload})

    print(f"\n📋 RESUMEN:")
    print(f"   A actualizar:        {len(to_update)}")
    print(f"   Ya resueltos en DB:  {skipped_already_set}")
    print(f"   No encontrados en DB:{skipped_not_in_db}")

    if not to_update:
        print("\n✅ Nada que actualizar.")
        return

    # Preview
    print(f"\n{'─'*60}")
    print(f"{'ID':>6}  {'result':>6}  {'pnl_teorico':>12}  resolved_at")
    print(f"{'─'*60}")
    for item in to_update[:20]:
        p = item["payload"]
        print(f"{item['id']:>6}  "
              f"{p.get('result','—'):>6}  "
              f"{str(p.get('pnl_teorico','—')):>12}  "
              f"{p.get('resolved_at','—')}")
    if len(to_update) > 20:
        print(f"  ... y {len(to_update)-20} más")
    print(f"{'─'*60}")

    if dry_run:
        print("\n🔵 DRY RUN — no se aplicaron cambios.")
        return

    # Aplicar en batches
    confirm = input(f"\n¿Aplicar {len(to_update)} actualizaciones? (s/n): ").strip().lower()
    if confirm != "s":
        print("Cancelado.")
        return

    updated = 0
    errors  = 0

    for i in range(0, len(to_update), batch_size):
        batch = to_update[i:i+batch_size]
        for item in batch:
            try:
                sb.table("whale_signals").update(item["payload"]).eq("id", item["id"]).execute()
                updated += 1
            except Exception as e:
                print(f"  ❌ Error en id={item['id']}: {e}")
                errors += 1

        pct = min(100, (i + len(batch)) / len(to_update) * 100)
        print(f"  Progreso: {i+len(batch)}/{len(to_update)} ({pct:.0f}%) — {errors} errores")

    print(f"\n✅ Completado: {updated} actualizados, {errors} errores.")
    print(f"   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Actualiza whale_signals en Supabase con resultados del CSV enriquecido.")
    parser.add_argument("--csv",     type=str, default=str(DEFAULT_CSV), help="Ruta al CSV (default: gold_enriched.csv)")
    parser.add_argument("--dry-run", action="store_true",                help="Mostrar cambios sin aplicarlos")
    parser.add_argument("--id",      type=int, default=None,             help="Actualizar solo un ID específico")
    parser.add_argument("--batch",   type=int, default=50,               help="Tamaño de batch (default: 50)")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"❌ CSV no encontrado: {csv_path}")
        sys.exit(1)

    run(csv_path, dry_run=args.dry_run, target_id=args.id, batch_size=args.batch)


if __name__ == "__main__":
    main()