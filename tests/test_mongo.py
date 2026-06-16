# tests/test_mongo.py
from __future__ import annotations

from unittest.mock import MagicMock, patch

import mcp_server.mongo as mongo_module


def _make_mock_collection() -> MagicMock:
    col = MagicMock()
    col.insert_one.return_value.inserted_id = "507f1f77bcf86cd799439011"  # pragma: allowlist secret
    return col


def test_insert_run_returns_inserted_id():
    mock_col = _make_mock_collection()
    with patch.object(mongo_module, "get_collection", return_value=mock_col):
        result = mongo_module.insert_run({"foo": "bar"})
    assert result == "507f1f77bcf86cd799439011"  # pragma: allowlist secret


def test_insert_run_injects_created_at():
    mock_col = _make_mock_collection()
    with patch.object(mongo_module, "get_collection", return_value=mock_col):
        mongo_module.insert_run({"run_metadata": {"ok": True}})
    doc = mock_col.insert_one.call_args[0][0]
    assert "_created_at" in doc
    assert "T" in doc["_created_at"]  # ISO-8601 format contains T


def test_insert_run_does_not_mutate_input():
    mock_col = _make_mock_collection()
    original = {"foo": "bar"}
    with patch.object(mongo_module, "get_collection", return_value=mock_col):
        mongo_module.insert_run(original)
    assert "_created_at" not in original  # input dict must not be mutated


def test_get_latest_run_returns_none_when_empty():
    mock_col = MagicMock()
    mock_col.find_one.return_value = None
    with patch.object(mongo_module, "get_collection", return_value=mock_col):
        result = mongo_module.get_latest_run()
    assert result is None


def test_get_latest_run_sorts_by_created_at_descending():
    mock_col = MagicMock()
    mock_col.find_one.return_value = None
    with patch.object(mongo_module, "get_collection", return_value=mock_col):
        mongo_module.get_latest_run()
    mock_col.find_one.assert_called_once_with(sort=[("_created_at", -1)])


def test_get_latest_run_converts_object_id_to_string():
    from bson import ObjectId

    oid = ObjectId("507f1f77bcf86cd799439011")  # pragma: allowlist secret
    mock_col = MagicMock()
    mock_col.find_one.return_value = {
        "_id": oid,
        "foo": "bar",
        "_created_at": "2026-05-28T00:00:00+00:00",
    }
    with patch.object(mongo_module, "get_collection", return_value=mock_col):
        result = mongo_module.get_latest_run()
    assert result is not None
    assert result["_id"] == "507f1f77bcf86cd799439011"
    assert result["foo"] == "bar"


def test_ping_issues_admin_ping_command():
    mock_client = MagicMock()
    with patch.object(mongo_module, "_get_client", return_value=mock_client):
        mongo_module.ping()
    mock_client.admin.command.assert_called_once_with("ping")


def test_ping_propagates_failure():
    import pytest

    mock_client = MagicMock()
    mock_client.admin.command.side_effect = RuntimeError("no server")
    with (
        patch.object(mongo_module, "_get_client", return_value=mock_client),
        pytest.raises(RuntimeError),
    ):
        mongo_module.ping()


def test_update_run_sets_patch_and_returns_matched():
    from bson import ObjectId

    mock_col = MagicMock()
    mock_col.update_one.return_value.matched_count = 1
    with patch.object(mongo_module, "get_collection", return_value=mock_col):
        matched = mongo_module.update_run(
            "507f1f77bcf86cd799439011",  # pragma: allowlist secret
            {"discord_sent_status": "success"},
        )
    assert matched is True
    call = mock_col.update_one.call_args
    assert call.args[0] == {"_id": ObjectId("507f1f77bcf86cd799439011")}  # pragma: allowlist secret
    set_doc = call.args[1]["$set"]
    assert set_doc["discord_sent_status"] == "success"
    assert "_updated_at" in set_doc


def test_update_run_returns_false_when_no_match():
    mock_col = MagicMock()
    mock_col.update_one.return_value.matched_count = 0
    with patch.object(mongo_module, "get_collection", return_value=mock_col):
        matched = mongo_module.update_run(
            "507f1f77bcf86cd799439011",  # pragma: allowlist secret
            {"x": 1},
        )
    assert matched is False


def test_update_run_does_not_mutate_input():
    mock_col = MagicMock()
    mock_col.update_one.return_value.matched_count = 1
    original = {"channel_id": "123"}
    with patch.object(mongo_module, "get_collection", return_value=mock_col):
        mongo_module.update_run(
            "507f1f77bcf86cd799439011",  # pragma: allowlist secret
            original,
        )
    assert "_updated_at" not in original  # input patch must stay untouched


def test_close_closes_and_resets_client():
    from unittest.mock import MagicMock, patch

    mock_client = MagicMock()
    with patch.object(mongo_module, "_client", mock_client):
        mongo_module.close()
        mock_client.close.assert_called_once()
    assert mongo_module._client is None


def test_close_is_idempotent_when_no_client():
    from unittest.mock import patch

    with patch.object(mongo_module, "_client", None):
        mongo_module.close()  # must not raise
    assert mongo_module._client is None
