import contextlib
import json
import threading

import keyring.errors
import pytest
from simple_module_remote.config.credentials import (
    CredentialError,
    CredentialStore,
    StoredCredential,
)

CLI = "smdev"
ORIGIN = "https://app.example"


def test_failed_keyring_delete_keeps_the_index_entry(keyring_store):
    store = CredentialStore(CLI, backend=keyring_store)
    store.put("dev/acme", StoredCredential("tok", ORIGIN))

    def refuse(service, username):
        raise keyring.errors.PasswordDeleteError("denied")

    keyring_store.delete_password = refuse
    with pytest.raises(CredentialError, match="refused to delete"):
        store.delete("dev/acme")
    assert "dev/acme" in store._index()  # still tracked: a later remove can retry


def test_index_update_merges_a_concurrent_writer(keyring_store):
    store = CredentialStore(CLI, backend=keyring_store)
    store.put("dev", StoredCredential("tok", ORIGIN))
    # Another process adds a key between our read and write.
    keyring_store.set_password(CLI, "~index", json.dumps(["dev", "dev/other"]))
    store.put("dev/acme", StoredCredential("tok", ORIGIN))
    assert set(store._index()) == {"dev", "dev/other", "dev/acme"}


def test_delete_env_also_finds_unindexed_legacy_tenant_keys(keyring_store):
    store = CredentialStore(CLI, backend=keyring_store)
    keyring_store.set_password(  # written before the index existed
        CLI, "dev/acme", '{"token": "tok", "origin": "https://app.example"}'
    )
    assert store.delete_env("dev", ["acme"]) == ["dev/acme"]
    assert keyring_store.creds == {}


def test_env_remove_prints_the_incomplete_removal_note_for_a_keyring(make_cli, keyring_store):
    from click.testing import CliRunner

    cli, runner = make_cli(), CliRunner()
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000"])
    result = runner.invoke(cli, ["env", "remove", "dev"])
    assert "keyring cannot be listed" in result.output


def test_a_second_store_waits_for_the_first_to_finish(keyring_store):
    """Two stores (standing in for two processes) on one backend are serialised."""
    a = CredentialStore(CLI, backend=keyring_store)
    b = CredentialStore(CLI, backend=keyring_store)
    real_set = keyring_store.set_password
    state: dict = {}

    def racing_set(service, username, password):
        if username == "dev/a" and "thread" not in state:
            state["thread"] = threading.Thread(
                target=lambda: b.put("dev/b", StoredCredential("tok", ORIGIN))
            )
            state["thread"].start()
            state["thread"].join(timeout=0.3)
            state["blocked"] = state["thread"].is_alive()  # B must be waiting on A's lock
        real_set(service, username, password)

    keyring_store.set_password = racing_set
    a.put("dev/a", StoredCredential("tok", ORIGIN))
    state["thread"].join(timeout=5)
    assert state["blocked"]
    assert set(a._index()) == {"dev/a", "dev/b"}


def test_index_is_written_before_the_credential(keyring_store):
    store = CredentialStore(CLI, backend=keyring_store)

    def failing_set(service, username, password):
        if username != "~index":
            raise keyring.errors.KeyringError("boom")
        keyring_store.data[(service, username)] = password

    keyring_store.set_password = failing_set
    with contextlib.suppress(Exception):
        store.put("dev/acme", StoredCredential("tok", ORIGIN))
    assert "dev/acme" in store._index() and "dev/acme" not in {k[1] for k in keyring_store.creds}


def test_env_remove_keeps_the_env_when_a_keyring_delete_fails(make_cli, keyring_store):
    from click.testing import CliRunner

    cli, runner = make_cli(), CliRunner()
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000"])
    runner.invoke(cli, ["--env", "dev", "login", "--token-stdin"], input="tok\n")

    def refuse(service, username):
        raise keyring.errors.PasswordDeleteError("denied")

    keyring_store.delete_password = refuse
    result = runner.invoke(cli, ["env", "remove", "dev"])
    assert result.exit_code == 1 and "could not delete the stored login(s): dev" in result.output
    assert "dev" in runner.invoke(cli, ["env", "list"]).output  # kept: a retry is possible
