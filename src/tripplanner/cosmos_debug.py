"""Point-read one user's trip with a separately authorized Azure CLI identity."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urlparse

from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.identity import AzureCliCredential


def read_trip(database, user_id: str, trip_id: str, *, include_chat: bool = False) -> dict:
    if not user_id.strip() or not trip_id.strip():
        raise ValueError("An exact application user ID and trip ID are required")
    result = {}
    targets = [("trip", "trips", trip_id)]
    if include_chat:
        targets.append(("chat", "users", f"chat_{trip_id}"))
    for label, container_name, item_id in targets:
        container = database.get_container_client(container_name)
        try:
            result[label] = container.read_item(item=item_id, partition_key=user_id)
        except CosmosResourceNotFoundError:
            result[label] = None
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--user-id", required=True, help="Stored application user_id, not an email")
    parser.add_argument("--trip-id", required=True)
    parser.add_argument("--include-chat", action="store_true")
    args = parser.parse_args(argv)
    try:
        endpoint = urlparse(args.endpoint)
        port = endpoint.port
    except ValueError:
        parser.error("Invalid Cosmos endpoint")
    if (
        endpoint.scheme != "https"
        or not endpoint.hostname
        or not endpoint.hostname.endswith(".documents.azure.com")
        or endpoint.username
        or endpoint.password
        or endpoint.query
        or endpoint.fragment
        or endpoint.path not in {"", "/"}
        or port not in {None, 443}
    ):
        parser.error("Use the Azure public-cloud Cosmos HTTPS account endpoint")
    if any(
        not value.strip() for value in (args.database, args.tenant_id, args.user_id, args.trip_id)
    ):
        parser.error("Database, tenant, user and trip IDs must not be blank")
    try:
        with AzureCliCredential(tenant_id=args.tenant_id) as credential:
            with CosmosClient(args.endpoint, credential=credential) as client:
                result = read_trip(
                    client.get_database_client(args.database),
                    args.user_id,
                    args.trip_id,
                    include_chat=args.include_chat,
                )
    except Exception as exc:
        # SDK exception text can contain request details or credential diagnostics.
        print(
            f"Read failed ({type(exc).__name__}); check CLI sign-in, Reader roles, "
            "endpoint and database. No key fallback is used.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["trip"] is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
