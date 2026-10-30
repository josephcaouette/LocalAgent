"""Maintain the Qdrant memory store.

    python reindex_memory.py --list           show what's stored
    python reindex_memory.py                  re-embed every entry with the embedding model in
                                              config.py (run once after changing EMBED_MODEL)
    python reindex_memory.py --drop NAME.py   delete the entry for a file, e.g. a fake-success script
    python reindex_memory.py --import FILE    rebuild entries from an export, such as
                                              memory_export/agent_solutions.json from the backup

Entries are exported to .history\\memory_backup_<time>.json before anything changes. If the new
model's vectors have a different size, the collection is rebuilt from that data.
"""
import argparse
import json
import os
import sys
import time

import config
from agent_common import embed, get_qdrant, memory_text


def all_points(client):
    points, offset = [], None
    while True:
        batch, offset = client.scroll(config.COLLECTION_NAME, limit=100, offset=offset,
                                      with_payload=True, with_vectors=False)
        points.extend(batch)
        if offset is None:
            return points


def backup(points):
    os.makedirs(config.HISTORY_DIR, exist_ok=True)
    path = os.path.join(config.HISTORY_DIR, f"memory_backup_{time.strftime('%Y%m%d-%H%M%S')}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump([{"id": str(p.id), "payload": p.payload} for p in points], f, indent=1)
    return path


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Maintain the Qdrant memory store.")
    ap.add_argument("--list", action="store_true", help="show stored entries")
    ap.add_argument("--drop", metavar="FILE.py", help="delete the entry for this file")
    ap.add_argument("--import", dest="import_file", metavar="FILE",
                    help="re-create entries from an export (embeds them with the current model)")
    args = ap.parse_args()

    from qdrant_client.http import models
    client = get_qdrant()

    if args.import_file:
        with open(args.import_file, encoding="utf-8") as f:
            entries = json.load(f)
        new_points = []
        for e in entries:
            pl = dict(e["payload"])
            text = memory_text(pl.get("filename", ""), pl.get("goal", ""),
                               pl.get("summary") or pl.get("description", ""), pl.get("tags"))
            pl.pop("embed_scheme", None)
            pl["embed_model"] = config.EMBED_MODEL
            new_points.append(models.PointStruct(id=e["id"], vector=embed(text, "document"), payload=pl))
        if not new_points:
            print("The export is empty; nothing to import.")
            return 0
        if not client.collection_exists(config.COLLECTION_NAME):
            client.create_collection(
                config.COLLECTION_NAME,
                vectors_config=models.VectorParams(size=len(new_points[0].vector),
                                                   distance=models.Distance.COSINE))
        client.upsert(collection_name=config.COLLECTION_NAME, points=new_points)
        print(f"Imported {len(new_points)} entries with {config.EMBED_MODEL}.")
        return 0

    if not client.collection_exists(config.COLLECTION_NAME):
        print(f"Collection '{config.COLLECTION_NAME}' doesn't exist yet; nothing to do.")
        return 0
    points = all_points(client)

    if args.list:
        for p in points:
            pl = p.payload or {}
            tags = ", ".join(str(t) for t in (pl.get("tags") or []))
            model = pl.get("embed_model") or pl.get("embed_scheme") or "nomic (original)"
            print(f"{pl.get('filename', '?'):<30} embedded with {model}  tags={tags}")
            print(f"    {str(pl.get('summary') or pl.get('description') or '')[:160]}")
        print(f"{len(points)} entries")
        return 0
    if not points:
        print("Memory is empty; nothing to do.")
        return 0

    if args.drop:
        doomed = [p for p in points if (p.payload or {}).get("filename") == args.drop]
        if not doomed:
            print(f"No entry for {args.drop}.")
            return 1
        path = backup(doomed)
        client.delete(config.COLLECTION_NAME,
                      points_selector=models.PointIdsList(points=[p.id for p in doomed]))
        print(f"Deleted {len(doomed)} entry/entries for {args.drop} (backup: {path}).")
        return 0

    path = backup(points)
    print(f"Backed up {len(points)} entries to {path}")

    # Embed everything first, so a failure leaves the collection untouched.
    new_points = []
    for p in points:
        pl = dict(p.payload or {})
        text = memory_text(pl.get("filename", ""), pl.get("goal", ""),
                           pl.get("summary") or pl.get("description", ""), pl.get("tags"))
        try:
            vector = embed(text, "document")
        except Exception as e:
            print(f"[!] {pl.get('filename')}: embedding failed ({e}). Nothing was changed.")
            return 1
        pl.pop("embed_scheme", None)
        pl["embed_model"] = config.EMBED_MODEL
        new_points.append(models.PointStruct(id=p.id, vector=vector, payload=pl))

    new_size = len(new_points[0].vector)
    old_size = client.get_collection(config.COLLECTION_NAME).config.params.vectors.size
    if new_size != old_size:
        print(f"Vector size changes from {old_size} to {new_size}; rebuilding the collection.")
        client.delete_collection(config.COLLECTION_NAME)
        client.create_collection(
            config.COLLECTION_NAME,
            vectors_config=models.VectorParams(size=new_size, distance=models.Distance.COSINE))
    client.upsert(collection_name=config.COLLECTION_NAME, points=new_points)
    for p in new_points:
        print(f"[+] Re-embedded {p.payload.get('filename')}")
    print(f"Done: {len(new_points)} entries re-embedded with {config.EMBED_MODEL}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
