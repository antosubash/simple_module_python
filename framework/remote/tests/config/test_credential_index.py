import json

import keyring.errors
from simple_module_remote.config.credentials import CredentialStore, StoredCredential

CLI = "smdev"
ORIGIN = "https://app.example"


def test_failed_keyring_delete_keeps_the_index_entry(keyring_store):
    store = CredentialStore(CLI, backend=keyring_store)
    store.put("dev/acme", StoredCredential("tok", ORIGIN))

    def refuse(service, username):
        raise keyring.errors.PasswordDeleteError("denied")

    keyring_store.delete_password = refuse
    assert store.delete("dev/acme") is False
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
