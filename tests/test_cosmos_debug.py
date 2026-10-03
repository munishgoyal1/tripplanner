from types import SimpleNamespace

import pytest
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from tripplanner import cosmos_debug


@pytest.mark.parametrize("include_chat", [False, True])
def test_only_exact_point_reads_are_available(include_chat):
    calls = []

    def container(name):
        def read_item(**kwargs):
            calls.append((name, kwargs))
            return {"id": kwargs["item"], "user_id": kwargs["partition_key"]}

        return SimpleNamespace(read_item=read_item)

    result = cosmos_debug.read_trip(
        SimpleNamespace(get_container_client=container),
        "user-a",
        "trip-a",
        include_chat=include_chat,
    )
    expected = [("trips", {"item": "trip-a", "partition_key": "user-a"})]
    if include_chat:
        expected.append(("users", {"item": "chat_trip-a", "partition_key": "user-a"}))
    assert calls == expected
    assert result["trip"]["id"] == "trip-a"
    assert ("chat" in result) == include_chat


def test_missing_item_does_not_list_or_query():
    def missing(**kwargs):
        raise CosmosResourceNotFoundError(status_code=404)

    database = SimpleNamespace(get_container_client=lambda name: SimpleNamespace(read_item=missing))
    assert cosmos_debug.read_trip(database, "user", "trip") == {"trip": None}


@pytest.mark.parametrize("user,trip", [("", "trip"), ("user", " ")])
def test_blank_scope_rejected_before_any_access(user, trip):
    with pytest.raises(ValueError):
        cosmos_debug.read_trip(object(), user, trip)


def test_cli_uses_only_explicit_cli_identity(monkeypatch, capsys):
    calls = []

    class Credential:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class Client:
        def __init__(self, endpoint, credential):
            assert isinstance(credential, Credential)
            calls.append(endpoint)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get_database_client(self, name):
            calls.append(name)
            return SimpleNamespace(
                get_container_client=lambda name: SimpleNamespace(
                    read_item=lambda **kwargs: {"id": kwargs["item"]}
                )
            )

    monkeypatch.setenv("COSMOS_KEY", "must-not-be-used")
    monkeypatch.setenv("COSMOS_CONNECTION_STRING", "must-not-be-used")
    monkeypatch.setenv("COSMOS_USE_MANAGED_IDENTITY", "1")
    monkeypatch.setattr(cosmos_debug, "AzureCliCredential", Credential)
    monkeypatch.setattr(cosmos_debug, "CosmosClient", Client)
    assert (
        cosmos_debug.main(
            [
                "--endpoint",
                "https://account.documents.azure.com",
                "--database",
                "tripplanner-prod",
                "--tenant-id",
                "tenant",
                "--user-id",
                "user",
                "--trip-id",
                "trip",
            ]
        )
        == 0
    )
    assert calls == [
        {"tenant_id": "tenant"},
        "https://account.documents.azure.com",
        "tripplanner-prod",
    ]
    assert '"trip"' in capsys.readouterr().out


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://localhost:8081",
        "https://attacker.example",
        "https://account.documents.azure.com@attacker.example",
    ],
)
def test_invalid_endpoint_rejected(endpoint):
    with pytest.raises(SystemExit) as exc:
        cosmos_debug.main(
            [
                "--endpoint",
                endpoint,
                "--database",
                "db",
                "--tenant-id",
                "tenant",
                "--user-id",
                "user",
                "--trip-id",
                "trip",
            ]
        )
    assert exc.value.code == 2


def test_auth_failure_does_not_leak_sdk_details_or_fallback(monkeypatch, capsys):
    def fail(**kwargs):
        raise RuntimeError("sensitive credential diagnostics")

    monkeypatch.setattr(cosmos_debug, "AzureCliCredential", fail)
    assert (
        cosmos_debug.main(
            [
                "--endpoint",
                "https://account.documents.azure.com",
                "--database",
                "db",
                "--tenant-id",
                "tenant",
                "--user-id",
                "user",
                "--trip-id",
                "trip",
            ]
        )
        == 1
    )
    output = capsys.readouterr()
    assert output.out == ""
    assert "RuntimeError" in output.err
    assert "sensitive credential diagnostics" not in output.err
